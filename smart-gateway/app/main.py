from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from .admin_ui import ADMIN_HTML

APP_NAME = "ai-smart-gateway"
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", "/app/config"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "health_state.json"
REQUEST_LOG_FILE = DATA_DIR / "request_logs.jsonl"
PROVIDERS_FILE = CONFIG_DIR / "providers.yaml"
PROVIDERS_BACKUP_DIR = DATA_DIR / "config_backups"
SYNC_NEWAPI_SCRIPT = Path(os.getenv("SYNC_NEWAPI_SCRIPT", "/workspace/scripts/sync-newapi-router.py"))

MASTER_API_KEY = os.getenv("MASTER_API_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PROBE_INTERVAL_SECONDS = int(os.getenv("PROBE_INTERVAL_SECONDS", "60"))
PROBE_TIMEOUT_SECONDS = float(os.getenv("PROBE_TIMEOUT_SECONDS", "12"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))
MAX_RETRIES_PER_REQUEST = int(os.getenv("MAX_RETRIES_PER_REQUEST", "8"))
MIN_HEALTHY_PROVIDERS = int(os.getenv("MIN_HEALTHY_PROVIDERS", "1"))
ENABLE_RESPONSES_PROBE = os.getenv("ENABLE_RESPONSES_PROBE", "true").lower() == "true"
PROBE_ON_STARTUP = os.getenv("PROBE_ON_STARTUP", "true").lower() == "true"
MODELS_REFRESH_SECONDS = int(os.getenv("MODELS_REFRESH_SECONDS", "3600"))
PROBE_MAX_PER_CYCLE = int(os.getenv("PROBE_MAX_PER_CYCLE", "12"))
PROBE_SUCCESS_TTL_SECONDS = int(os.getenv("PROBE_SUCCESS_TTL_SECONDS", "21600"))
PROBE_UNSUPPORTED_TTL_SECONDS = int(os.getenv("PROBE_UNSUPPORTED_TTL_SECONDS", "86400"))
PROBE_AUTH_TTL_SECONDS = int(os.getenv("PROBE_AUTH_TTL_SECONDS", "3600"))
PROBE_QUOTA_TTL_SECONDS = int(os.getenv("PROBE_QUOTA_TTL_SECONDS", "3600"))
PROBE_RATE_LIMIT_TTL_SECONDS = int(os.getenv("PROBE_RATE_LIMIT_TTL_SECONDS", "1800"))
PROBE_SERVER_ERROR_TTL_SECONDS = int(os.getenv("PROBE_SERVER_ERROR_TTL_SECONDS", "900"))
PROBE_EXCEPTION_TTL_SECONDS = int(os.getenv("PROBE_EXCEPTION_TTL_SECONDS", "900"))
PROBE_UNKNOWN_ERROR_TTL_SECONDS = int(os.getenv("PROBE_UNKNOWN_ERROR_TTL_SECONDS", "1800"))
ROUTE_EXPLORATION_RATE = max(0.0, min(1.0, float(os.getenv("ROUTE_EXPLORATION_RATE", "0.15"))))
ROUTE_EXPLORATION_MAX_CANDIDATES = max(0, int(os.getenv("ROUTE_EXPLORATION_MAX_CANDIDATES", "1")))
ALLOW_GATEWAY_PROVIDER_WRITE = os.getenv("ALLOW_GATEWAY_PROVIDER_WRITE", "false").lower() == "true"
DECLARED_ROUTE_SOURCES = {"declared", "upstream_models+declared", "model_map", "canonical_alias_from_declared"}
SHADOW_ROUTE_SOURCES = {"upstream_models", *DECLARED_ROUTE_SOURCES}

CONFIG_LOCK = asyncio.Lock()
STATE_LOCK = asyncio.Lock()
REQUEST_LOG_LOCK = asyncio.Lock()
NEWAPI_DB = Path(os.getenv("NEWAPI_DB", "/newapi-data/one-api.db"))

CONFIG: dict[str, Any] = {}
PROVIDERS: list[dict[str, Any]] = []
HEALTH: dict[str, dict[str, dict[str, Any]]] = {"chat": {}, "responses": {}}
MODEL_CACHE: dict[str, dict[str, Any]] = {}
LAST_PROBE_AT: float | None = None

app = FastAPI(title=APP_NAME)


def now() -> float:
    return time.time()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def redact_text(value: Any, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text.replace("\n", "\\n")[:limit]


def extract_usage(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("usage"), dict):
        usage = data["usage"]
        return {
            "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    return {}


async def append_request_log(entry: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(now()),
        **entry,
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    async with REQUEST_LOG_LOCK:
        with REQUEST_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_recent_request_logs(limit: int = 200) -> list[dict[str, Any]]:
    if not REQUEST_LOG_FILE.exists():
        return []
    limit = max(1, min(limit, 1000))
    lines = REQUEST_LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(rows))


def slug(value: str) -> str:
    text = re.sub(r"^https?://", "", value.strip().lower())
    text = re.sub(r"[^a-z0-9_.-]+", "_", text)
    return text.strip("._-") or "provider"


_env_pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _env_pattern.sub(lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def normalize_base_url(base_url: str, exact: bool = False) -> str:
    base_url = base_url.strip().rstrip("/")
    if exact:
        return base_url
    if re.search(r"/v\d+$", base_url):
        return base_url
    return f"{base_url}/v1"


def normalize_base_urls(provider: dict[str, Any]) -> list[str]:
    exact = bool(provider.get("base_url_exact", False))
    values = [str(provider.get("base_url") or "")]
    values.extend(str(item) for item in (provider.get("base_urls") or []) if str(item))
    normalized = [normalize_base_url(value, exact) for value in values if value.strip()]
    return list(dict.fromkeys(normalized))


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    return authorization.split(" ", 1)[1].strip()


def auth_ok(authorization: str | None) -> bool:
    return bool(MASTER_API_KEY and bearer_token(authorization) == MASTER_API_KEY)


def admin_ok(authorization: str | None, x_admin_token: str | None) -> bool:
    token = bearer_token(authorization) or (x_admin_token or "").strip()
    return bool(ADMIN_TOKEN and token == ADMIN_TOKEN)


def require_admin(authorization: str | None, x_admin_token: str | None) -> JSONResponse | None:
    if not admin_ok(authorization, x_admin_token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


def model_allowed(model: str) -> bool:
    includes = CONFIG.get("model_include") or ["*"]
    excludes = CONFIG.get("model_exclude") or []
    return any(fnmatch.fnmatch(model, pat) for pat in includes) and not any(
        fnmatch.fnmatch(model, pat) for pat in excludes
    )


def canonical_for_actual(actual_model: str) -> str:
    canonical_models = CONFIG.get("canonical_models") or {}
    for local, aliases in canonical_models.items():
        if actual_model == local or actual_model in (aliases or []):
            return local
    return actual_model


def model_version_key(model: str) -> tuple[int, ...]:
    numbers = [int(value) for value in re.findall(r"\d+", model)]
    return tuple(numbers)


def provider_model_filter(provider: dict[str, Any], models: list[str]) -> list[str]:
    rules = provider.get("model_filters") or []
    if not isinstance(rules, list) or not rules:
        return models
    selected: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        include = [str(pattern) for pattern in (rule.get("include") or []) if str(pattern)]
        exclude = [str(pattern) for pattern in (rule.get("exclude") or []) if str(pattern)]
        limit = int(rule.get("limit") or 0)
        matched = [
            model
            for model in models
            if (not include or any(fnmatch.fnmatch(model, pattern) for pattern in include))
            and not any(fnmatch.fnmatch(model, pattern) for pattern in exclude)
        ]
        matched.sort(key=lambda model: (model_version_key(model), model), reverse=True)
        if limit > 0:
            matched = matched[:limit]
        selected.extend(matched)
    if not selected:
        return []
    return sorted(dict.fromkeys(selected))


def build_probe_targets(provider: dict[str, Any], fetched_models: list[str]) -> list[dict[str, str]]:
    targets: dict[tuple[str, str], dict[str, str]] = {}
    declared = provider.get("declared_models") or []
    filtered_models = provider_model_filter(provider, [model for model in fetched_models if isinstance(model, str) and model])
    fetched_set = {model for model in filtered_models if isinstance(model, str) and model}
    declared_set = {model for model in declared if isinstance(model, str) and model}

    for local, actual in (provider.get("model_map") or {}).items():
        if local and actual and model_allowed(local):
            targets[(local, actual)] = {"local_model": local, "actual_model": actual, "source": "model_map"}

    for actual in sorted(fetched_set | declared_set):
        local = canonical_for_actual(actual)
        if model_allowed(local):
            if actual in fetched_set and actual in declared_set:
                source = "upstream_models+declared"
            elif actual in fetched_set:
                source = "upstream_models"
            else:
                source = "declared"
            targets.setdefault((local, actual), {"local_model": local, "actual_model": actual, "source": source})

    for local, aliases in (CONFIG.get("canonical_models") or {}).items():
        if model_allowed(local) and local in declared:
            for actual in aliases or [local]:
                targets.setdefault(
                    (local, actual),
                    {"local_model": local, "actual_model": actual, "source": "canonical_alias_from_declared"},
                )

    return list(targets.values())


def provider_signature(provider: dict[str, Any]) -> str:
    payload = {
        "base_url": provider.get("base_url"),
        "base_urls": provider.get("base_urls") or [],
        "api_key": provider.get("api_key"),
        "headers": provider.get("headers") or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def health_item_key(kind: str, provider_id: str, local_model: str, actual_model: str) -> str:
    return f"{kind}:{provider_id}:{local_model}:{actual_model}"


def health_matrix_key(provider_id: str, actual_model: str) -> str:
    return f"{provider_id}::{actual_model}"


def response_stream_event(
    event_type: str,
    request_id: str,
    model: str | None,
    status: str,
    error_type: str | None = None,
    message: str | None = None,
) -> bytes:
    response: dict[str, Any] = {
        "id": request_id,
        "object": "response",
        "created_at": int(now()),
        "status": status,
        "model": model or "",
    }
    payload: dict[str, Any] = {"type": event_type, "response": response}
    if error_type or message:
        payload["error"] = {"type": error_type or "api_error", "message": message or error_type or "stream failed"}
        response["error"] = payload["error"]
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n".encode("utf-8")


def response_completed_event(request_id: str, model: str | None) -> bytes:
    return response_stream_event("response.completed", request_id, model, "completed")


def response_failed_event(request_id: str, model: str | None, error_type: str, message: str) -> bytes:
    return response_stream_event("response.failed", request_id, model, "failed", error_type, message)


def probe_cooldown_seconds(reason: str | None, healthy: bool) -> int:
    if healthy or reason == "ok":
        return PROBE_SUCCESS_TTL_SECONDS
    reason = reason or ""
    if reason in {"not_found", "model_unsupported"}:
        return PROBE_UNSUPPORTED_TTL_SECONDS
    if reason == "auth_or_forbidden":
        return PROBE_AUTH_TTL_SECONDS
    if reason == "quota":
        return PROBE_QUOTA_TTL_SECONDS
    if reason == "rate_limited":
        return PROBE_RATE_LIMIT_TTL_SECONDS
    if reason in {"server_unavailable", "empty_stream"}:
        return PROBE_SERVER_ERROR_TTL_SECONDS
    if reason.startswith("exception:"):
        return PROBE_EXCEPTION_TTL_SECONDS
    return PROBE_UNKNOWN_ERROR_TTL_SECONDS


def preserve_probe_state(new_item: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return new_item
    preserved = deepcopy(previous)
    next_probe_at = preserved.get("next_probe_at")
    if not next_probe_at:
        next_probe_at = int(now()) + probe_cooldown_seconds(preserved.get("reason"), bool(preserved.get("healthy")))
    preserved.update(
        {
            "provider_name": new_item["provider_name"],
            "base_url": new_item["base_url"],
            "local_model": new_item["local_model"],
            "actual_model": new_item["actual_model"],
            "source": new_item.get("source"),
            "kind": new_item["kind"],
            "request_format": new_item["request_format"],
            "probe_path": new_item["probe_path"],
            "priority": new_item["priority"],
            "weight": new_item["weight"],
            "route_group": new_item.get("route_group", "primary"),
            "cost_tier": new_item.get("cost_tier", "free"),
            "fallback_only": bool(new_item.get("fallback_only", False)),
            "provider_signature": new_item["provider_signature"],
            "next_probe_at": next_probe_at,
            "skipped": True,
            "skip_reason": "cooldown",
        }
    )
    return preserved


async def save_state() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {"updated_at": now(), "health": HEALTH, "model_cache": MODEL_CACHE, "last_probe_at": LAST_PROBE_AT}
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def load_state() -> None:
    global HEALTH, MODEL_CACHE, LAST_PROBE_AT
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            HEALTH = data.get("health") or HEALTH
            MODEL_CACHE = data.get("model_cache") or {}
            LAST_PROBE_AT = data.get("last_probe_at")
    except Exception:
        HEALTH = {"chat": {}, "responses": {}}
        MODEL_CACHE = {}
        LAST_PROBE_AT = None


async def reload_config() -> None:
    global CONFIG, PROVIDERS
    async with CONFIG_LOCK:
        CONFIG = expand_env(load_yaml(CONFIG_DIR / "gateway.yaml"))
        raw = expand_env(load_yaml(PROVIDERS_FILE)).get("providers") or []
        providers = []
        for item in raw:
            if not item.get("enabled", True):
                continue
            if not item.get("base_url") or not item.get("api_key"):
                continue
            provider = deepcopy(item)
            base_urls = normalize_base_urls(provider)
            if not base_urls:
                continue
            provider["base_urls"] = base_urls
            provider["base_url"] = base_urls[0]
            provider["priority"] = int(provider.get("priority", 0))
            provider["weight"] = max(1, int(provider.get("weight", 1)))
            provider["timeout_seconds"] = float(provider.get("timeout_seconds", REQUEST_TIMEOUT_SECONDS))
            provider["headers"] = provider.get("headers") or {}
            provider["route_group"] = str(provider.get("route_group") or "primary")
            provider["cost_tier"] = str(provider.get("cost_tier") or "free")
            provider["fallback_only"] = bool(provider.get("fallback_only", False))
            providers.append(provider)
        PROVIDERS = providers


def redact_provider(provider: dict[str, Any], expanded: dict[str, Any] | None = None) -> dict[str, Any]:
    item = deepcopy(provider)
    expanded_key = (expanded or {}).get("api_key") or item.get("api_key") or ""
    item["api_key_set"] = bool(expanded_key)
    item["api_key_preview"] = preview_secret(str(expanded_key))
    if isinstance(item.get("api_key"), str) and item["api_key"].startswith("${"):
        item["api_key_env"] = item["api_key"][2:-1]
    item["api_key"] = ""
    return item


def split_tags(value: str | None) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\s]+", value or "") if item.strip()]


def normalize_route_tag_value(route_group: str, cost_tier: str, fallback_only: bool) -> str:
    tags: list[str] = ["gateway-source"]
    if route_group:
        tags.append(f"gw:{route_group}")
    if cost_tier:
        tags.append(f"gw:{cost_tier}")
    if fallback_only:
        tags.append("gw:fallback-only")
    return ",".join(dict.fromkeys(tags))


def parse_route_tags(tag_value: str | None) -> dict[str, Any]:
    route_group = "primary"
    cost_tier = "free"
    fallback_only = False
    for tag in split_tags(tag_value):
        if not tag.startswith("gw:"):
            continue
        value = tag.removeprefix("gw:")
        if value in {"primary", "opportunistic", "backup", "paid_fallback", "other"}:
            route_group = value
            if value == "paid_fallback":
                fallback_only = True
                cost_tier = "paid"
        elif value in {"free", "metered", "paid", "unknown"}:
            cost_tier = value
        elif value == "fallback-only":
            fallback_only = True
        elif value == "not-fallback-only":
            fallback_only = False
    return {"route_group": route_group, "cost_tier": cost_tier, "fallback_only": fallback_only}


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "启用", "是"}


def with_channel_fields(provider: dict[str, Any], channel_row: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(provider)
    if not channel_row:
        return item
    item["new_api_channel"] = channel_row
    item["new_api_channel_id"] = channel_row.get("id")
    item["base_url"] = str(channel_row.get("base_url") or item.get("base_url") or "")
    item["enabled"] = int(channel_row.get("status") if channel_row.get("status") is not None else 1) == 1
    item["priority"] = int(channel_row.get("priority") or 0)
    item["weight"] = int(channel_row.get("weight") or 0)
    tag_policy = parse_route_tags(channel_row.get("tag"))
    item["route_group"] = tag_policy["route_group"]
    item["cost_tier"] = tag_policy["cost_tier"]
    item["fallback_only"] = tag_policy["fallback_only"]
    item["tag"] = channel_row.get("tag") or ""
    item["channel_models"] = [m.strip() for m in str(channel_row.get("models") or "").split(",") if m.strip()]
    item["channel_remark"] = channel_row.get("remark") or ""
    return item


def load_newapi_channel_rows() -> list[dict[str, Any]]:
    if not NEWAPI_DB.exists():
        return []
    con = sqlite3.connect(NEWAPI_DB)
    con.row_factory = sqlite3.Row
    try:
        table = con.execute("select name from sqlite_master where type = 'table' and name = 'channels'").fetchone()
        if not table:
            return []
        rows = con.execute(
            """
            select id, name, status, priority, weight, base_url, models, tag, "group", remark, key
            from channels
            where coalesce(name, '') != ? and coalesce(base_url, '') != ?
            order by priority desc, weight desc, id asc
            """,
            ("Smart Gateway Router", "http://smart-gateway:8000"),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item.pop("key", None)
            result.append(item)
        return result
    finally:
        con.close()


def update_newapi_source_policy(updates: list[dict[str, Any]]) -> int:
    if not NEWAPI_DB.exists():
        raise ValueError(f"New API database not found: {NEWAPI_DB}")
    allowed_routes = {"primary", "opportunistic", "backup", "paid_fallback", "other"}
    allowed_costs = {"free", "metered", "paid", "unknown"}
    con = sqlite3.connect(NEWAPI_DB)
    try:
        changed = 0
        for update in updates:
            channel_id = int(update.get("id") or update.get("new_api_channel_id") or 0)
            if channel_id <= 0:
                raise ValueError("channel id is required")
            existing = con.execute(
                'select id, name, tag, base_url from channels where id = ?',
                (channel_id,),
            ).fetchone()
            if not existing:
                raise ValueError(f"channel not found: {channel_id}")
            route_group = str(update.get("route_group") or "primary").strip()
            cost_tier = str(update.get("cost_tier") or "free").strip()
            if route_group not in allowed_routes:
                raise ValueError(f"unsupported route_group: {route_group}")
            if cost_tier not in allowed_costs:
                raise ValueError(f"unsupported cost_tier: {cost_tier}")
            fallback_only = parse_bool(update.get("fallback_only"), False) or route_group == "paid_fallback"
            status = 1 if parse_bool(update.get("enabled"), True) else 0
            weight = max(1, min(10000, int(update.get("weight") or 100)))
            priority = int(update.get("priority") if update.get("priority") is not None else 0)
            base_url = str(update.get("base_url") or existing[3] or "").strip().rstrip("/")
            if base_url and not base_url.startswith(("http://", "https://")):
                raise ValueError(f"invalid base_url for channel {channel_id}")
            models_value = update.get("models")
            if isinstance(models_value, list):
                models = ",".join(dict.fromkeys(str(item).strip() for item in models_value if str(item).strip()))
            else:
                models = ",".join(
                    dict.fromkeys(item.strip() for item in str(models_value or "").replace("\n", ",").split(",") if item.strip())
                )
            tag = normalize_route_tag_value(route_group, cost_tier, fallback_only)
            con.execute(
                """
                update channels
                set status = ?, weight = ?, priority = ?, base_url = ?, models = ?, tag = ?, "group" = 'default'
                where id = ?
                """,
                (status, weight, priority, base_url, models, tag, channel_id),
            )
            changed += 1
        con.commit()
        return changed
    finally:
        con.close()


def preview_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def provider_runtime_summary() -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for kind in ("chat", "responses"):
        for model_items in (HEALTH.get(kind) or {}).values():
            for item in model_items.values():
                provider_id = item.get("provider_id")
                if not provider_id:
                    continue
                row = summary.setdefault(provider_id, {"healthy": 0, "unhealthy": 0, "latencies": []})
                if item.get("healthy"):
                    row["healthy"] += 1
                    if item.get("latency_ms") is not None:
                        row["latencies"].append(item.get("latency_ms"))
                else:
                    row["unhealthy"] += 1
    for row in summary.values():
        latencies = row.pop("latencies", [])
        row["avg_latency_ms"] = int(sum(latencies) / len(latencies)) if latencies else None
    return summary


def build_models_summary() -> list[dict[str, Any]]:
    models = []
    all_models = set((HEALTH.get("chat") or {}).keys()) | set((HEALTH.get("responses") or {}).keys())
    for model in sorted(all_models):
        chat_items = (HEALTH.get("chat", {}).get(model) or {}).values()
        response_items = (HEALTH.get("responses", {}).get(model) or {}).values()
        chat_ok = sum(1 for item in chat_items if item.get("healthy"))
        responses_ok = sum(1 for item in response_items if item.get("healthy"))
        if chat_ok >= MIN_HEALTHY_PROVIDERS or responses_ok >= MIN_HEALTHY_PROVIDERS:
            models.append({"id": model, "chat_ok": chat_ok, "responses_ok": responses_ok})
    return models


def public_base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def validate_provider_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    provider_id = str(item.get("id") or "").strip()
    base_url = str(item.get("base_url") or "").strip()
    api_key = str(item.get("api_key") or "").strip()
    if not provider_id:
        raise ValueError(f"provider[{index}].id is required")
    if not re.match(r"^[A-Za-z0-9_.-]+$", provider_id):
        raise ValueError(f"provider[{index}].id contains unsupported characters")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"provider[{index}].base_url must start with http:// or https://")
    normalized = {
        "id": provider_id,
        "name": str(item.get("name") or provider_id).strip(),
        "enabled": bool(item.get("enabled", True)),
        "base_url": base_url.rstrip("/"),
        "base_url_exact": bool(item.get("base_url_exact", False)),
        "api_key": api_key,
        "priority": int(item.get("priority", 0)),
        "weight": max(1, int(item.get("weight", 100))),
        "timeout_seconds": float(item.get("timeout_seconds", 60)),
        "route_group": str(item.get("route_group") or "primary").strip(),
        "cost_tier": str(item.get("cost_tier") or "free").strip(),
        "fallback_only": bool(item.get("fallback_only", False)),
        "declared_models": [
            str(model).strip()
            for model in (item.get("declared_models") or [])
            if str(model).strip()
        ],
        "model_filters": item.get("model_filters") if isinstance(item.get("model_filters"), list) else [],
        "models_from_declared_only": bool(item.get("models_from_declared_only", False)),
        "headers": item.get("headers") if isinstance(item.get("headers"), dict) else {},
    }
    return normalized


def backup_config_file(path: Path) -> str | None:
    if not path.exists():
        return None
    PROVIDERS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime())
    backup = PROVIDERS_BACKUP_DIR / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    return str(backup)


def provider_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    headers.update({str(k): str(v) for k, v in (provider.get("headers") or {}).items()})
    return headers


def upstream_url(provider: dict[str, Any], path: str) -> str:
    return provider["base_url"].rstrip("/") + "/" + path.lstrip("/")


def upstream_urls(provider: dict[str, Any], path: str) -> list[str]:
    bases = provider.get("base_urls") or [provider.get("base_url")]
    return [str(base).rstrip("/") + "/" + path.lstrip("/") for base in bases if str(base or "").strip()]


def extract_models_from_response(data: Any) -> list[str]:
    models: list[str] = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        for item in data["data"]:
            if isinstance(item, dict) and item.get("id"):
                models.append(str(item["id"]))
            elif isinstance(item, str):
                models.append(item)
    return sorted(set(models))


def classify_error(status_code: int, text: str) -> str:
    sample = (text or "").lower()
    if "quota" in sample or "balance" in sample or "insufficient" in sample or "额度" in sample or "余额" in sample:
        return "quota"
    unsupported = ("not support", "unsupported", "不支持", "model not found", "model_not_found", "模型不存在")
    if any(word in sample for word in unsupported):
        return "model_unsupported"
    invalid_request = ("invalid codex request", "invalid_responses_request", "invalid request", "invalid_request")
    if status_code == 400 and any(word in sample for word in invalid_request):
        return "invalid_request"
    if status_code in (401, 403):
        return "auth_or_forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 429 or "rate limit" in sample or "too many" in sample or "限流" in sample:
        return "rate_limited"
    if status_code in (500, 502, 503, 504):
        return "server_unavailable"
    if "<html" in sample or "<!doctype html" in sample or "cloudflare" in sample:
        return "html_or_cloudflare"
    return f"http_{status_code}"


def response_has_error_json(data: Any) -> bool:
    return isinstance(data, dict) and bool(data.get("error"))


async def fetch_models(provider: dict[str, Any]) -> list[str]:
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(PROBE_TIMEOUT_SECONDS), follow_redirects=True) as client:
        for url in upstream_urls(provider, "/models"):
            try:
                response = await client.get(url, headers=provider_headers(provider))
                if response.status_code >= 400:
                    raise RuntimeError(f"models_http_{response.status_code}:{response.text[:200]}")
                return extract_models_from_response(response.json())
            except Exception as exc:
                last_error = exc
                continue
    raise RuntimeError(str(last_error or "models_fetch_failed"))


async def get_models_for_provider(provider: dict[str, Any], force: bool = False) -> list[str]:
    provider_id = provider["id"]
    signature = provider_signature(provider)
    cached = MODEL_CACHE.get(provider_id) or {}
    if (
        not force
        and cached.get("signature") == signature
        and cached.get("models") is not None
        and float(cached.get("next_refresh_at") or 0) > now()
    ):
        return [str(model) for model in cached.get("models") or []]
    try:
        models = await fetch_models(provider)
        MODEL_CACHE[provider_id] = {
            "signature": signature,
            "models": models,
            "fetched_at": int(now()),
            "next_refresh_at": int(now()) + MODELS_REFRESH_SECONDS,
            "reason": "ok",
        }
        return models
    except Exception as exc:
        previous_models = [str(model) for model in cached.get("models") or []]
        MODEL_CACHE[provider_id] = {
            "signature": signature,
            "models": previous_models,
            "fetched_at": cached.get("fetched_at"),
            "next_refresh_at": int(now()) + PROBE_EXCEPTION_TTL_SECONDS,
            "reason": f"exception:{type(exc).__name__}",
        }
        return previous_models


async def probe_one(provider: dict[str, Any], local_model: str, actual_model: str, kind: str) -> dict[str, Any]:
    probe_cfg = (CONFIG.get("probe") or {}).get(kind) or {}
    if not probe_cfg.get("enabled", True):
        return {"healthy": False, "reason": "probe_disabled"}
    if kind == "responses" and not ENABLE_RESPONSES_PROBE:
        return {"healthy": False, "reason": "responses_probe_disabled"}

    body = deepcopy(probe_cfg.get("body") or {})
    body["model"] = actual_model
    start = now()
    last_result: dict[str, Any] | None = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(PROBE_TIMEOUT_SECONDS), follow_redirects=True) as client:
            for url in upstream_urls(provider, probe_cfg.get("path") or f"/{kind}"):
                response = await client.post(
                    url,
                    headers=provider_headers(provider),
                    json=body,
                )
                latency_ms = int((now() - start) * 1000)
                text = response.text[:2000]
                if response.status_code < 200 or response.status_code >= 300:
                    last_result = {
                        "healthy": False,
                        "reason": classify_error(response.status_code, text),
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "sample": text[:300],
                        "endpoint_url": url,
                    }
                    continue
                data = response.json()
                if response_has_error_json(data):
                    sample = json.dumps(data, ensure_ascii=False)[:1000]
                    last_result = {
                        "healthy": False,
                        "reason": classify_error(response.status_code, sample),
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "sample": sample[:300],
                        "endpoint_url": url,
                    }
                    continue
                return {
                    "healthy": True,
                    "reason": "ok",
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "endpoint_url": url,
                }
            if last_result:
                return last_result
            return {"healthy": False, "reason": "no_endpoint", "latency_ms": int((now() - start) * 1000)}
    except Exception as exc:
        return {
            "healthy": False,
            "reason": f"exception:{type(exc).__name__}",
            "latency_ms": int((now() - start) * 1000),
            "sample": str(exc)[:300],
        }


async def probe_all(force: bool = False) -> None:
    global LAST_PROBE_AT
    await reload_config()
    old_health = deepcopy(HEALTH)
    new_health: dict[str, dict[str, dict[str, Any]]] = {"chat": {}, "responses": {}}
    probes_run = 0
    probe_limit = max(1, PROBE_MAX_PER_CYCLE)
    candidates: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        fetched = [] if provider.get("models_from_declared_only") else await get_models_for_provider(provider, force=force)
        signature = provider_signature(provider)
        for target in build_probe_targets(provider, fetched):
            local_model = target["local_model"]
            actual_model = target["actual_model"]
            if not model_allowed(local_model):
                continue
            for kind in ("chat", "responses"):
                if kind == "responses" and not ENABLE_RESPONSES_PROBE:
                    continue
                probe_cfg = (CONFIG.get("probe") or {}).get(kind) or {}
                item = {
                    "provider_id": provider["id"],
                    "provider_name": provider.get("name") or provider["id"],
                    "base_url": provider["base_url"],
                    "local_model": local_model,
                    "actual_model": actual_model,
                    "source": target.get("source"),
                    "kind": kind,
                    "request_format": "openai-compatible",
                    "probe_path": probe_cfg.get("path") or f"/{kind}",
                    "priority": provider["priority"],
                    "weight": provider["weight"],
                    "route_group": provider.get("route_group", "primary"),
                    "cost_tier": provider.get("cost_tier", "free"),
                    "fallback_only": bool(provider.get("fallback_only", False)),
                    "provider_signature": signature,
                }
                matrix_key = health_matrix_key(provider["id"], actual_model)
                previous = (old_health.get(kind, {}).get(local_model) or {}).get(matrix_key)
                if previous is None:
                    previous = (old_health.get(kind, {}).get(local_model) or {}).get(provider["id"])
                if previous is not None and previous.get("healthy") is None and not previous.get("checked_at"):
                    previous = None
                previous_signature = previous.get("provider_signature") if previous else None
                due = force or not previous or previous_signature != signature or float(previous.get("next_probe_at") or 0) <= now()
                candidates.append(
                    {
                        "provider": provider,
                        "item": item,
                        "kind": kind,
                        "local_model": local_model,
                        "actual_model": actual_model,
                        "matrix_key": matrix_key,
                        "previous": previous,
                        "due": due,
                    }
                )

    candidates.sort(
        key=lambda candidate: (
            0 if candidate["previous"] is None or not candidate["previous"].get("checked_at") else 1,
            0 if candidate["due"] else 1,
            -int(candidate["item"].get("priority", 0)),
            -int(candidate["item"].get("weight", 0)),
            candidate["item"].get("provider_name") or "",
            candidate["local_model"],
            candidate["kind"],
        )
    )

    for candidate in candidates:
        provider = candidate["provider"]
        item = candidate["item"]
        kind = candidate["kind"]
        local_model = candidate["local_model"]
        actual_model = candidate["actual_model"]
        matrix_key = candidate["matrix_key"]
        previous = candidate["previous"]
        due = candidate["due"]
        if due and probes_run < probe_limit:
            result = await probe_one(provider, local_model, actual_model, kind)
            probes_run += 1
            item.update(
                {
                    "healthy": bool(result.get("healthy")),
                    "reason": result.get("reason"),
                    "status_code": result.get("status_code"),
                    "latency_ms": result.get("latency_ms"),
                    "checked_at": int(now()),
                    "next_probe_at": int(now()) + probe_cooldown_seconds(result.get("reason"), bool(result.get("healthy"))),
                    "sample": result.get("sample", ""),
                    "skipped": False,
                    "skip_reason": "",
                }
            )
        else:
            if previous is None:
                item.update(
                    {
                        "healthy": False,
                        "reason": "probe_budget_exhausted" if due else "pending_probe",
                        "status_code": None,
                        "latency_ms": None,
                        "checked_at": None,
                        "next_probe_at": int(now()) + PROBE_INTERVAL_SECONDS,
                        "sample": "",
                        "skipped": True,
                        "skip_reason": "probe_budget",
                    }
                )
            else:
                item = preserve_probe_state(item, previous)
        by_model = new_health.setdefault(kind, {}).setdefault(local_model, {})
        current = by_model.get(matrix_key)
        if current is None:
            by_model[matrix_key] = item
        elif item.get("healthy") and not current.get("healthy"):
            by_model[matrix_key] = item
        elif item.get("healthy") == current.get("healthy"):
            if (item.get("latency_ms") or 999999) < (current.get("latency_ms") or 999999):
                by_model[matrix_key] = item
    async with STATE_LOCK:
        HEALTH.clear()
        HEALTH.update(new_health)
        LAST_PROBE_AT = now()
        await save_state()


async def probe_loop() -> None:
    while True:
        try:
            await probe_all()
        except Exception as exc:
            print(f"[probe_loop] {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(PROBE_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_state()
    await reload_config()
    if PROBE_ON_STARTUP:
        asyncio.create_task(probe_loop())


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "app": APP_NAME, "providers": len(PROVIDERS), "last_probe_at": LAST_PROBE_AT}


@app.get("/admin")
async def admin_root_redirect():
    return RedirectResponse("/gateway-admin/")


@app.get("/admin/", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(ADMIN_HTML)


@app.get("/gateway-admin")
async def gateway_admin_root_redirect():
    return RedirectResponse("/gateway-admin/")


@app.get("/gateway-admin/", response_class=HTMLResponse)
async def gateway_admin_page():
    return HTMLResponse(ADMIN_HTML)


@app.get("/admin/api/overview")
@app.get("/gateway-admin/api/overview")
async def admin_overview(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    base = public_base_url(request)
    async with STATE_LOCK:
        models = build_models_summary()
        chat_healthy = sum(
            1
            for model_items in (HEALTH.get("chat") or {}).values()
            for item in model_items.values()
            if item.get("healthy")
        )
        responses_healthy = sum(
            1
            for model_items in (HEALTH.get("responses") or {}).values()
            for item in model_items.values()
            if item.get("healthy")
        )
        return {
            "app": APP_NAME,
            "base_url": base,
            "legacy_base_url": f"{base}/v1",
            "new_api_admin_url": f"{base}/",
            "admin_url": f"{base}/gateway-admin/",
            "router_channel_name": "Smart Gateway Router",
            "source_tag": "gateway-source",
            "router_groups": os.getenv("NEW_API_ROUTER_GROUPS", "default,vip"),
            "last_probe_at": LAST_PROBE_AT,
            "provider_count": len(PROVIDERS),
            "chat_healthy": chat_healthy,
            "responses_healthy": responses_healthy,
            "models": models,
            "health": HEALTH,
        }


@app.get("/admin/api/providers")
@app.get("/gateway-admin/api/providers")
async def admin_providers(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    raw = (load_yaml(PROVIDERS_FILE).get("providers") or [])
    expanded = expand_env({"providers": raw}).get("providers") or []
    source_warning = None
    try:
        channel_rows = {int(row["id"]): row for row in load_newapi_channel_rows()}
    except sqlite3.Error as exc:
        channel_rows = {}
        source_warning = f"New API database unavailable: {exc}"
    runtime = provider_runtime_summary()
    providers = []
    for index, item in enumerate(raw):
        expanded_item = expanded[index] if index < len(expanded) and isinstance(expanded[index], dict) else {}
        provider = redact_provider(item, expanded_item)
        provider["runtime"] = runtime.get(provider.get("id"), {"healthy": 0, "unhealthy": 0, "avg_latency_ms": None})
        channel_id = provider.get("new_api_channel_id")
        channel_row = channel_rows.get(int(channel_id)) if channel_id is not None else None
        if channel_row:
            channel_data = {
                "id": channel_row["id"],
                "name": channel_row["name"],
                "status": channel_row["status"],
                "priority": channel_row["priority"],
                "weight": channel_row["weight"],
                "base_url": channel_row["base_url"],
                "models": channel_row["models"],
                "tag": channel_row["tag"] or "",
                "group": channel_row["group"],
                "remark": channel_row["remark"] or "",
            }
            provider = with_channel_fields(provider, channel_data)
            provider["editable_policy"] = {
                "id": channel_data["id"],
                "enabled": provider["enabled"],
                "route_group": provider["route_group"],
                "cost_tier": provider["cost_tier"],
                "fallback_only": provider["fallback_only"],
                "priority": provider["priority"],
                "weight": provider["weight"],
                "base_url": provider["base_url"],
                "base_urls": provider.get("base_urls") or [provider["base_url"]],
                "models": channel_data["models"] or "",
                "tag": provider["tag"],
            }
        providers.append(provider)
    response = {"providers": providers}
    if source_warning:
        response["source_warning"] = source_warning
    return response


@app.post("/admin/api/source-policy")
@app.post("/gateway-admin/api/source-policy")
async def admin_save_source_policy(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    try:
        body = await request.json()
        updates = body.get("providers")
        if not isinstance(updates, list):
            raise ValueError("providers must be a list")
        changed = update_newapi_source_policy(updates)
        result = await asyncio.to_thread(
            subprocess.run,
            [
                str(SYNC_NEWAPI_SCRIPT),
                "--router-groups",
                os.getenv("NEW_API_ROUTER_GROUPS", "default,vip"),
                "--auto-adopt-default-channels",
                "--force-reload",
                "--no-backup",
            ],
            cwd=str(SYNC_NEWAPI_SCRIPT.parent.parent),
            text=True,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            return JSONResponse(
                {"ok": False, "changed": changed, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]},
                status_code=500,
            )
        await reload_config()
        return {"ok": True, "changed": changed, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.post("/admin/api/providers")
@app.post("/gateway-admin/api/providers")
async def admin_save_providers(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    if not ALLOW_GATEWAY_PROVIDER_WRITE:
        return JSONResponse(
            {
                "error": (
                    "provider writes are disabled; manage upstream channels in New API channels "
                    "with tag 'gateway-source' and sync the source pool"
                )
            },
            status_code=403,
        )
    try:
        body = await request.json()
        incoming = body.get("providers")
        if not isinstance(incoming, list):
            raise ValueError("providers must be a list")
        providers = [validate_provider_item(item, index) for index, item in enumerate(incoming)]
        ids = [item["id"] for item in providers]
        if len(ids) != len(set(ids)):
            raise ValueError("provider id must be unique")
        backup = backup_config_file(PROVIDERS_FILE)
        write_yaml(PROVIDERS_FILE, {"providers": providers})
        await reload_config()
        asyncio.create_task(probe_all(force=False))
        return {"ok": True, "backup": backup, "providers": len(providers), "message": "saved and incremental probe started"}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/admin/reload")
@app.post("/gateway-admin/reload")
async def admin_reload(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    force: bool = False,
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    await reload_config()
    asyncio.create_task(probe_all(force=force))
    mode = "full probe" if force else "incremental probe"
    return {"ok": True, "message": f"reload started: {mode}"}


@app.post("/admin/sync-newapi")
@app.post("/gateway-admin/sync-newapi")
async def admin_sync_newapi(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    if not SYNC_NEWAPI_SCRIPT.exists():
        return JSONResponse({"error": f"sync script not found: {SYNC_NEWAPI_SCRIPT}"}, status_code=500)
    result = await asyncio.to_thread(
        subprocess.run,
        [
            str(SYNC_NEWAPI_SCRIPT),
            "--router-groups",
            os.getenv("NEW_API_ROUTER_GROUPS", "default,vip"),
            "--auto-adopt-default-channels",
            "--force-reload",
            "--no-backup",
        ],
        cwd=str(SYNC_NEWAPI_SCRIPT.parent.parent),
        text=True,
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        return JSONResponse(
            {"ok": False, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]},
            status_code=500,
        )
    await reload_config()
    return {"ok": True, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


@app.get("/admin/matrix")
@app.get("/gateway-admin/matrix")
async def admin_matrix(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    async with STATE_LOCK:
        return {
            "last_probe_at": LAST_PROBE_AT,
            "providers": [
                {
                    "id": provider["id"],
                    "name": provider.get("name"),
                    "base_url": provider["base_url"],
                    "priority": provider["priority"],
                    "weight": provider["weight"],
                    "route_group": provider.get("route_group", "primary"),
                    "cost_tier": provider.get("cost_tier", "free"),
                    "fallback_only": bool(provider.get("fallback_only", False)),
                }
                for provider in PROVIDERS
            ],
            "health": HEALTH,
        }


@app.get("/admin/api/request-logs")
@app.get("/gateway-admin/api/request-logs")
async def admin_request_logs(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    limit: int = 200,
):
    unauthorized = require_admin(authorization, x_admin_token)
    if unauthorized:
        return unauthorized
    return {"logs": read_recent_request_logs(limit)}


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(default=None)):
    if not auth_ok(authorization):
        return JSONResponse({"error": {"message": "Unauthorized", "type": "auth_error"}}, status_code=401)
    async with STATE_LOCK:
        models = []
        all_models = set((HEALTH.get("chat") or {}).keys()) | set((HEALTH.get("responses") or {}).keys())
        for model in sorted(all_models):
            chat_ok = sum(1 for item in (HEALTH.get("chat", {}).get(model) or {}).values() if item.get("healthy"))
            resp_ok = sum(1 for item in (HEALTH.get("responses", {}).get(model) or {}).values() if item.get("healthy"))
            if chat_ok >= MIN_HEALTHY_PROVIDERS or resp_ok >= MIN_HEALTHY_PROVIDERS:
                models.append({"id": model, "object": "model", "created": 0, "owned_by": APP_NAME})
    return {"object": "list", "data": models}


@app.get("/v1")
async def v1_index(authorization: str | None = Header(default=None)):
    return await list_models(authorization)


def get_provider_by_id(provider_id: str) -> dict[str, Any] | None:
    return next((provider for provider in PROVIDERS if provider["id"] == provider_id), None)


def provider_matches_controls(item: dict[str, Any], controls: dict[str, Any]) -> bool:
    provider_id = controls.get("provider_id")
    route_group = controls.get("route_group")
    allow_paid = controls.get("allow_paid", True)
    if provider_id and item.get("provider_id") != provider_id:
        return False
    if route_group and item.get("route_group") != route_group:
        return False
    if not allow_paid and (item.get("cost_tier") == "paid" or item.get("route_group") == "paid_fallback"):
        return False
    return True


def request_route_controls(request: Request) -> dict[str, Any]:
    headers = getattr(request, "headers", {}) or {}
    provider_id = (headers.get("x-gateway-provider") or "").strip()
    route_group = (headers.get("x-gateway-route-group") or "").strip()
    allow_paid_raw = (headers.get("x-gateway-allow-paid") or "").strip().lower()
    allow_paid = allow_paid_raw not in {"0", "false", "no", "off"}
    controls: dict[str, Any] = {"allow_paid": allow_paid}
    if provider_id:
        controls["provider_id"] = provider_id
    if route_group:
        controls["route_group"] = route_group
    return controls


def sorted_route_bucket(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        item["_score"] = max(1, int(item.get("weight") or 1)) * (1000 / max(1, int(item.get("latency_ms") or 1000)))
    items.sort(key=lambda item: (-int(item.get("priority", 0)), -item.get("_score", 0), item.get("latency_ms") or 999999))
    return items


def route_bucket_name(item: dict[str, Any]) -> str:
    if item.get("route_group") == "paid_fallback" or item.get("fallback_only") or item.get("cost_tier") == "paid":
        return "paid_fallback"
    if item.get("_explore"):
        return "explore"
    if item.get("_shadow"):
        return "shadow"
    return str(item.get("route_group") or "primary")


def shadow_candidate_allowed(item: dict[str, Any], controls: dict[str, Any]) -> bool:
    if controls.get("provider_id") and controls.get("provider_id") == item.get("provider_id"):
        return True
    reason = str(item.get("reason") or "")
    if reason == "runtime_failure:invalid_request":
        return True
    if reason.startswith("runtime_failure:") and float(item.get("next_probe_at") or 0) > now():
        return False
    return True


def shadow_route_source_allowed(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or "")
    if source == "upstream_models":
        return True
    if source not in DECLARED_ROUTE_SOURCES:
        return False
    reason = str(item.get("reason") or "")
    if reason in {"pending_probe", "probe_budget_exhausted"}:
        return True
    if reason in {"invalid_request", "runtime_failure:invalid_request"} and item.get("kind") == "responses":
        return True
    return not item.get("checked_at")


def should_mark_runtime_failure(reason: str) -> bool:
    return reason != "invalid_request"


def should_mark_provider_all_endpoints_failed(kind: str, endpoint_reasons: list[str]) -> bool:
    if not endpoint_reasons:
        return True
    if kind == "responses" and all(reason == "invalid_request" for reason in endpoint_reasons):
        return False
    return any(should_mark_runtime_failure(reason) for reason in endpoint_reasons)


def exploration_enabled(controls: dict[str, Any]) -> bool:
    if ROUTE_EXPLORATION_MAX_CANDIDATES <= 0 or ROUTE_EXPLORATION_RATE <= 0:
        return False
    if controls.get("provider_id") or controls.get("route_group"):
        return False
    return random.random() < ROUTE_EXPLORATION_RATE


def exploration_candidate_allowed(item: dict[str, Any]) -> bool:
    if item.get("fallback_only") or item.get("cost_tier") == "paid" or item.get("route_group") == "paid_fallback":
        return False
    return item.get("route_group", "primary") in {"opportunistic", "primary", "backup"}


def retryable_probe_candidate_allowed(item: dict[str, Any], kind: str, controls: dict[str, Any]) -> bool:
    if item.get("healthy"):
        return False
    if kind != "responses":
        return False
    reason = str(item.get("reason") or "")
    if reason not in {"invalid_request", "runtime_failure:invalid_request"}:
        return False
    if item.get("fallback_only") or item.get("cost_tier") == "paid" or item.get("route_group") == "paid_fallback":
        return False
    return provider_matches_controls(item, controls)


def healthy_candidate_buckets(model: str, kind: str, controls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    controls = controls or {}
    all_items = [deepcopy(item) for item in (HEALTH.get(kind, {}).get(model) or {}).values()]
    all_items = [item for item in all_items if provider_matches_controls(item, controls)]
    healthy = [item for item in all_items if item.get("healthy")]
    primary = sorted_route_bucket(
        [item for item in healthy if item.get("route_group", "primary") == "primary" and not item.get("fallback_only")]
    )
    backup = sorted_route_bucket(
        [item for item in healthy if item.get("route_group") == "backup" and not item.get("fallback_only")]
    )
    paid = sorted_route_bucket(
        [
            item
            for item in healthy
            if item.get("route_group") == "paid_fallback" or item.get("fallback_only") or item.get("cost_tier") == "paid"
        ]
    )
    other = sorted_route_bucket(
        [
            item
            for item in healthy
            if item.get("route_group", "primary") not in {"primary", "backup", "paid_fallback"}
            and not item.get("fallback_only")
            and item.get("cost_tier") != "paid"
        ]
    )
    retryable_probe = sorted_route_bucket(
        [item for item in all_items if retryable_probe_candidate_allowed(item, kind, controls)]
    )
    for item in retryable_probe:
        item["_probe_retry"] = True
        item["_shadow"] = True
    retryable_keys = {(item.get("provider_id"), item.get("actual_model")) for item in retryable_probe}
    shadow = [
        item
        for item in all_items
        if not item.get("healthy") and shadow_route_source_allowed(item) and item.get("provider_id")
        and shadow_candidate_allowed(item, controls)
        and (item.get("provider_id"), item.get("actual_model")) not in retryable_keys
    ]
    shadow.sort(key=lambda item: (-int(item.get("priority", 0)), item.get("checked_at") or 0))
    explore: list[dict[str, Any]] = []
    if exploration_enabled(controls):
        explore = sorted_route_bucket([item for item in shadow if exploration_candidate_allowed(item)])
        explore = explore[:ROUTE_EXPLORATION_MAX_CANDIDATES]
        explore_keys = {(item.get("provider_id"), item.get("actual_model")) for item in explore}
        shadow = [
            item
            for item in shadow
            if (item.get("provider_id"), item.get("actual_model")) not in explore_keys
        ]
        for item in explore:
            item["_explore"] = True
            item["_shadow"] = True
    for item in shadow:
        item["_shadow"] = True
    buckets = [
        {"name": "explore", "items": explore},
        {"name": "primary", "items": primary},
        {"name": "backup", "items": backup},
        {"name": "other", "items": other},
        {"name": "probe_retry", "items": retryable_probe},
        {"name": "shadow", "items": shadow},
        {"name": "paid_fallback", "items": paid},
    ]
    return [bucket for bucket in buckets if bucket["items"]]


def healthy_candidates(model: str, kind: str, controls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for bucket in healthy_candidate_buckets(model, kind, controls):
        for item in bucket["items"]:
            item["_route_bucket"] = bucket["name"]
            candidates.append(item)
    return candidates


def select_route_candidate(buckets: list[dict[str, Any]]) -> tuple[dict[str, Any], str] | None:
    for bucket in buckets:
        items = bucket["items"]
        if items:
            return pick_weighted(items), bucket["name"]
    return None


def pick_weighted(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(max(1, int(item.get("weight") or 1)) for item in candidates)
    cursor = 0
    needle = random.randint(1, total)
    for item in candidates:
        cursor += max(1, int(item.get("weight") or 1))
        if needle <= cursor:
            return item
    return candidates[0]


async def mark_runtime_failure(kind: str, model: str, provider_id: str, reason: str) -> None:
    async with STATE_LOCK:
        matched = [
            item
            for item in (HEALTH.get(kind, {}).get(model) or {}).values()
            if item.get("provider_id") == provider_id
        ]
        for item in matched:
            item["healthy"] = False
            item["reason"] = f"runtime_failure:{reason}"
            item["checked_at"] = int(now())
            item["next_probe_at"] = int(now()) + probe_cooldown_seconds(reason, False)
        if matched:
            await save_state()


async def mark_runtime_success(kind: str, model: str, provider_id: str, latency_ms: int) -> None:
    async with STATE_LOCK:
        matched = [
            item
            for item in (HEALTH.get(kind, {}).get(model) or {}).values()
            if item.get("provider_id") == provider_id
        ]
        for item in matched:
            item["healthy"] = True
            item["reason"] = "ok"
            item["latency_ms"] = latency_ms
            item["checked_at"] = int(now())
            item["next_probe_at"] = int(now()) + PROBE_SUCCESS_TTL_SECONDS
        if matched:
            await save_state()


def log_route_fields(chosen: dict[str, Any], route_bucket: str | None = None) -> dict[str, Any]:
    return {
        "route_bucket": route_bucket or chosen.get("_route_bucket") or route_bucket_name(chosen),
        "route_group": chosen.get("route_group", "primary"),
        "cost_tier": chosen.get("cost_tier", "free"),
        "fallback_only": bool(chosen.get("fallback_only", False)),
        "shadow": bool(chosen.get("_shadow", False)),
    }


async def relay_non_stream(
    path: str,
    body: dict[str, Any],
    kind: str,
    controls: dict[str, Any] | None = None,
) -> JSONResponse:
    controls = controls or {}
    request_id = f"gw_{uuid.uuid4().hex[:16]}"
    model = body.get("model")
    if not model:
        return JSONResponse({"error": {"message": "Missing model", "type": "invalid_request_error"}}, status_code=400)
    buckets = healthy_candidate_buckets(model, kind, controls)
    total_candidates = sum(len(bucket["items"]) for bucket in buckets)
    if not total_candidates:
        await append_request_log(
            {
                "request_id": request_id,
                "kind": kind,
                "stream": bool(body.get("stream", False)),
                "requested_model": model,
                "success": False,
                "error_type": "no_healthy_upstream",
                "route_controls": controls,
            }
        )
        return JSONResponse(
            {"error": {"message": f"No healthy upstream for model={model}, kind={kind}", "type": "no_healthy_upstream"}},
            status_code=503,
        )
    tried = []
    last_error: dict[str, Any] | None = None
    attempts = min(MAX_RETRIES_PER_REQUEST, total_candidates)
    for _ in range(attempts):
        selected = select_route_candidate(buckets)
        if not selected:
            break
        chosen, route_bucket = selected
        for bucket in buckets:
            bucket["items"] = [item for item in bucket["items"] if item["provider_id"] != chosen["provider_id"]]
        provider = get_provider_by_id(chosen["provider_id"])
        if not provider:
            continue
        req_body = deepcopy(body)
        req_body["model"] = chosen["actual_model"]
        route_fields = log_route_fields(chosen, route_bucket)
        tried.append({"provider_id": chosen["provider_id"], "actual_model": chosen["actual_model"], **route_fields})
        start = now()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(provider.get("timeout_seconds") or REQUEST_TIMEOUT_SECONDS),
                follow_redirects=True,
            ) as client:
                response = None
                endpoint_url = ""
                for candidate_url in upstream_urls(provider, path):
                    endpoint_url = candidate_url
                    response = await client.post(candidate_url, headers=provider_headers(provider), json=req_body)
                    if 200 <= response.status_code < 300:
                        break
                if response is None:
                    raise RuntimeError("no endpoint url")
            latency_ms = int((now() - start) * 1000)
            text = response.text
            try:
                data = response.json()
            except Exception:
                data = None
            if 200 <= response.status_code < 300 and not response_has_error_json(data):
                await mark_runtime_success(kind, model, chosen["provider_id"], latency_ms)
                await append_request_log(
                    {
                        "request_id": request_id,
                        "kind": kind,
                        "stream": bool(body.get("stream", False)),
                        "requested_model": model,
                        "actual_model": chosen["actual_model"],
                        "provider_id": chosen["provider_id"],
                        "path": path,
                        "endpoint_url": endpoint_url,
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "success": True,
                        "usage": extract_usage(data),
                        "route_controls": controls,
                        **route_fields,
                    }
                )
                if data is not None:
                    return JSONResponse(data, status_code=response.status_code)
                return JSONResponse({"raw": text}, status_code=response.status_code)
            reason = classify_error(response.status_code, text[:1000])
            if should_mark_runtime_failure(reason):
                await mark_runtime_failure(kind, model, chosen["provider_id"], reason)
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": bool(body.get("stream", False)),
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": path,
                    "endpoint_url": endpoint_url,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "success": False,
                    "error_type": reason,
                    "error_sample": redact_text(text, 500),
                    "usage": extract_usage(data),
                    "route_controls": controls,
                    **route_fields,
                }
            )
            last_error = {"status_code": response.status_code, "reason": reason, "body": text[:500], "tried": tried}
        except Exception as exc:
            reason = f"exception:{type(exc).__name__}"
            await mark_runtime_failure(kind, model, chosen["provider_id"], reason)
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": bool(body.get("stream", False)),
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": path,
                    "success": False,
                    "error_type": reason,
                    "error_sample": redact_text(str(exc), 500),
                    "route_controls": controls,
                    **route_fields,
                }
            )
            last_error = {"status_code": 599, "reason": reason, "body": str(exc)[:500], "tried": tried}
    return JSONResponse(
        {
            "error": {
                "message": f"All healthy upstreams failed for model={model}, kind={kind}",
                "type": "all_upstreams_failed",
                "details": last_error,
            }
        },
        status_code=503,
    )


async def relay_stream(
    path: str,
    body: dict[str, Any],
    kind: str,
    controls: dict[str, Any] | None = None,
):
    controls = controls or {}
    request_id = f"gw_{uuid.uuid4().hex[:16]}"
    model = body.get("model")
    if not model:
        await append_request_log(
            {
                "request_id": request_id,
                "kind": kind,
                "stream": True,
                "success": False,
                "error_type": "missing_model",
                "route_controls": controls,
            }
        )
        if kind == "responses":
            yield response_failed_event(request_id, model, "invalid_request_error", "Missing model")
        else:
            yield b'data: {"error":{"message":"Missing model","type":"invalid_request_error"}}\n\n'
        yield b"data: [DONE]\n\n"
        return

    buckets = healthy_candidate_buckets(model, kind, controls)
    total_candidates = sum(len(bucket["items"]) for bucket in buckets)
    if not total_candidates:
        await append_request_log(
            {
                "request_id": request_id,
                "kind": kind,
                "stream": True,
                "requested_model": model,
                "success": False,
                "error_type": "no_healthy_upstream",
                "route_controls": controls,
            }
        )
        if kind == "responses":
            yield response_failed_event(request_id, model, "no_healthy_upstream", "No healthy upstream")
        else:
            yield b'data: {"error":{"message":"No healthy upstream","type":"no_healthy_upstream"}}\n\n'
        yield b"data: [DONE]\n\n"
        return

    attempts = min(MAX_RETRIES_PER_REQUEST, total_candidates)
    for _ in range(attempts):
        selected = select_route_candidate(buckets)
        if not selected:
            break
        chosen, route_bucket = selected
        for bucket in buckets:
            bucket["items"] = [item for item in bucket["items"] if item["provider_id"] != chosen["provider_id"]]
        provider = get_provider_by_id(chosen["provider_id"])
        if not provider:
            continue

        req_body = deepcopy(body)
        req_body["model"] = chosen["actual_model"]
        route_fields = log_route_fields(chosen, route_bucket)
        start = now()
        stream_started = False
        done_sent = False
        response_completed = False
        endpoint_reasons: list[str] = []

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(provider.get("timeout_seconds") or REQUEST_TIMEOUT_SECONDS),
                follow_redirects=True,
            ) as client:
                for endpoint_url in upstream_urls(provider, path):
                    async with client.stream("POST", endpoint_url, headers=provider_headers(provider), json=req_body) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            raw = await response.aread()
                            reason = classify_error(response.status_code, raw.decode("utf-8", "ignore")[:1000])
                            endpoint_reasons.append(reason)
                            await append_request_log(
                                {
                                    "request_id": request_id,
                                    "kind": kind,
                                    "stream": True,
                                    "requested_model": model,
                                    "actual_model": chosen["actual_model"],
                                    "provider_id": chosen["provider_id"],
                                    "path": path,
                                    "endpoint_url": endpoint_url,
                                    "status_code": response.status_code,
                                    "latency_ms": int((now() - start) * 1000),
                                    "success": False,
                                    "error_type": reason,
                                    "error_sample": redact_text(raw.decode("utf-8", "ignore"), 500),
                                    "route_controls": controls,
                                    **route_fields,
                                }
                            )
                            continue

                        first = None
                        raw_chunks = response.aiter_raw()
                        async for chunk in raw_chunks:
                            if chunk:
                                first = chunk
                                break
                        if not first:
                            await append_request_log(
                                {
                                    "request_id": request_id,
                                    "kind": kind,
                                    "stream": True,
                                    "requested_model": model,
                                    "actual_model": chosen["actual_model"],
                                    "provider_id": chosen["provider_id"],
                                    "path": path,
                                    "endpoint_url": endpoint_url,
                                    "status_code": response.status_code,
                                    "latency_ms": int((now() - start) * 1000),
                                    "success": False,
                                    "error_type": "empty_stream",
                                    "route_controls": controls,
                                    **route_fields,
                                }
                            )
                            endpoint_reasons.append("empty_stream")
                            continue

                        latency_ms = int((now() - start) * 1000)
                        await mark_runtime_success(kind, model, chosen["provider_id"], latency_ms)
                        await append_request_log(
                            {
                                "request_id": request_id,
                                "kind": kind,
                                "stream": True,
                                "requested_model": model,
                                "actual_model": chosen["actual_model"],
                                "provider_id": chosen["provider_id"],
                                "path": path,
                                "endpoint_url": endpoint_url,
                                "status_code": response.status_code,
                                "latency_ms": latency_ms,
                                "success": True,
                                "route_controls": controls,
                                **route_fields,
                            }
                        )
                        stream_started = True
                        done_sent = b"[DONE]" in first
                        response_completed = b"response.completed" in first
                        yield first
                        async for chunk in raw_chunks:
                            if chunk:
                                if b"[DONE]" in chunk:
                                    done_sent = True
                                if b"response.completed" in chunk:
                                    response_completed = True
                                yield chunk
                        if kind == "responses" and not response_completed:
                            yield response_completed_event(request_id, model)
                        if not done_sent:
                            yield b"data: [DONE]\n\n"
                        return

                if should_mark_provider_all_endpoints_failed(kind, endpoint_reasons):
                    await mark_runtime_failure(kind, model, chosen["provider_id"], "all_endpoints_failed")
        except Exception as exc:
            if stream_started:
                if kind == "responses" and not response_completed:
                    yield response_failed_event(
                        request_id,
                        model,
                        f"exception:{type(exc).__name__}",
                        "Upstream stream closed before completion",
                    )
                if not done_sent:
                    yield b"data: [DONE]\n\n"
                return
            await mark_runtime_failure(kind, model, chosen["provider_id"], f"exception:{type(exc).__name__}")
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": True,
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": path,
                    "success": False,
                    "error_type": f"exception:{type(exc).__name__}",
                    "error_sample": redact_text(str(exc), 500),
                    "route_controls": controls,
                    **route_fields,
                }
            )

    await append_request_log(
        {
            "request_id": request_id,
            "kind": kind,
            "stream": True,
            "requested_model": model,
            "success": False,
            "error_type": "all_upstreams_failed",
            "route_controls": controls,
        }
    )
    if kind == "responses":
        yield response_failed_event(request_id, model, "all_upstreams_failed", "All upstreams failed before stream started")
    else:
        yield b'data: {"error":{"message":"All upstreams failed before stream started","type":"all_upstreams_failed"}}\n\n'
    yield b"data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    if not auth_ok(authorization):
        return JSONResponse({"error": {"message": "Unauthorized", "type": "auth_error"}}, status_code=401)
    body = await request.json()
    controls = request_route_controls(request)
    if body.get("stream", False):
        return StreamingResponse(relay_stream("/chat/completions", body, "chat", controls), media_type="text/event-stream")
    return await relay_non_stream("/chat/completions", body, "chat", controls)


@app.post("/v1")
async def v1_chat_alias(request: Request, authorization: str | None = Header(default=None)):
    return await chat_completions(request, authorization)


@app.post("/v1/responses")
async def responses(request: Request, authorization: str | None = Header(default=None)):
    if not auth_ok(authorization):
        return JSONResponse({"error": {"message": "Unauthorized", "type": "auth_error"}}, status_code=401)
    body = await request.json()
    controls = request_route_controls(request)
    if body.get("stream", False):
        return StreamingResponse(relay_stream("/responses", body, "responses", controls), media_type="text/event-stream")
    return await relay_non_stream("/responses", body, "responses", controls)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def fallback(path: str):
    return JSONResponse({"error": {"message": f"Unsupported path: /{path}", "type": "unsupported_path"}}, status_code=404)
