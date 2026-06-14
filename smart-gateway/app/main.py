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
PROBE_CONCURRENCY = max(1, int(os.getenv("PROBE_CONCURRENCY", "6")))
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
PROBE_LOW_SIGNAL_TTL_SECONDS = int(os.getenv("PROBE_LOW_SIGNAL_TTL_SECONDS", "900"))
PROBE_CONTENT_QUALITY_CHECK = os.getenv("PROBE_CONTENT_QUALITY_CHECK", "true").lower() == "true"
PROBE_MIN_QUALITY_SCORE = int(os.getenv("PROBE_MIN_QUALITY_SCORE", "80"))
HEALTH_FRESH_TTL_SECONDS = int(os.getenv("HEALTH_FRESH_TTL_SECONDS", "300"))
RESPONSES_INVALID_REQUEST_CONFIRMATIONS = max(1, int(os.getenv("RESPONSES_INVALID_REQUEST_CONFIRMATIONS", "3")))
RESPONSES_INVALID_REQUEST_RETRY_SECONDS = int(os.getenv("RESPONSES_INVALID_REQUEST_RETRY_SECONDS", "60"))
RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS = int(os.getenv("RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS", "1800"))
RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS = max(1, int(os.getenv("RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS", "2")))
ADAPTIVE_FORMAT_ROUTING = os.getenv("ADAPTIVE_FORMAT_ROUTING", "true").lower() == "true"
ADAPTER_LATENCY_PENALTY_MS = int(os.getenv("ADAPTER_LATENCY_PENALTY_MS", "250"))
ADAPTER_SYNTHESIZE_USAGE = os.getenv("ADAPTER_SYNTHESIZE_USAGE", "true").lower() == "true"
ROUTE_EXPLORATION_RATE = max(0.0, min(1.0, float(os.getenv("ROUTE_EXPLORATION_RATE", "0.15"))))
ROUTE_EXPLORATION_MAX_CANDIDATES = max(0, int(os.getenv("ROUTE_EXPLORATION_MAX_CANDIDATES", "1")))
ALLOW_GATEWAY_PROVIDER_WRITE = os.getenv("ALLOW_GATEWAY_PROVIDER_WRITE", "false").lower() == "true"
DECLARED_ROUTE_SOURCES = {"declared", "upstream_models+declared", "model_map", "canonical_alias_from_declared"}
SHADOW_ROUTE_SOURCES = {"upstream_models", *DECLARED_ROUTE_SOURCES}
PROBE_STRATEGY_VERSION = "multi-profile-v1"

CONFIG_LOCK = asyncio.Lock()
STATE_LOCK = asyncio.Lock()
REQUEST_LOG_LOCK = asyncio.Lock()
PROBE_RUN_LOCK = asyncio.Lock()
NEWAPI_DB = Path(os.getenv("NEWAPI_DB", "/newapi-data/one-api.db"))

CONFIG: dict[str, Any] = {}
PROVIDERS: list[dict[str, Any]] = []
HEALTH: dict[str, dict[str, dict[str, Any]]] = {"chat": {}, "responses": {}}
MODEL_CACHE: dict[str, dict[str, Any]] = {}
LAST_PROBE_AT: float | None = None
RESPONSES_COMPAT_DEFAULTS: dict[str, dict[str, Any]] = {}

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


def token_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return max(0, int(stripped))
    return None


def normalize_usage_for_responses(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = token_int(usage.get("input_tokens"))
    if input_tokens is None:
        input_tokens = token_int(usage.get("prompt_tokens")) or 0
    output_tokens = token_int(usage.get("output_tokens"))
    if output_tokens is None:
        output_tokens = token_int(usage.get("completion_tokens")) or 0
    total_tokens = token_int(usage.get("total_tokens"))
    if total_tokens is None or total_tokens < input_tokens + output_tokens:
        total_tokens = input_tokens + output_tokens
    if total_tokens <= 0:
        return None
    normalized = dict(usage)
    normalized["input_tokens"] = input_tokens
    normalized["output_tokens"] = output_tokens
    normalized["total_tokens"] = total_tokens
    # Some OpenAI-compatible gateways still parse chat-style keys even on
    # Responses payloads; keeping both prevents downstream zero-token logs.
    normalized.setdefault("prompt_tokens", input_tokens)
    normalized.setdefault("completion_tokens", output_tokens)
    return normalized


_DATA_URL_RE = re.compile(r"data:[^,\s]+;base64,[A-Za-z0-9+/=\s]+")


def usage_estimate_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        text = str(value)
    return _DATA_URL_RE.sub("data:attachment;base64,[omitted]", text)


def approximate_token_count(value: Any) -> int:
    text = usage_estimate_text(value)
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    non_cjk = max(0, len(text) - cjk)
    return max(1, cjk + ((non_cjk + 3) // 4))


def synthesize_responses_usage(request_body: Any, output_value: Any) -> dict[str, Any] | None:
    if not ADAPTER_SYNTHESIZE_USAGE:
        return None
    input_tokens = approximate_token_count(request_body)
    output_tokens = approximate_token_count(output_value)
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    output_tokens = max(1, output_tokens)
    total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "estimated": True,
    }


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
        "chat_request_format": provider.get("chat_request_format") or "",
        "probe_strategy_version": PROBE_STRATEGY_VERSION,
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
    usage: dict[str, Any] | None = None,
    output: list[dict[str, Any]] | None = None,
    output_text: str | None = None,
) -> bytes:
    response: dict[str, Any] = {
        "id": request_id,
        "object": "response",
        "created_at": int(now()),
        "status": status,
        "model": model or "",
    }
    if usage:
        response["usage"] = usage
    if output is not None:
        response["output"] = output
        response["output_text"] = output_text if output_text is not None else ""
    payload: dict[str, Any] = {"type": event_type, "response": response}
    if error_type or message:
        payload["error"] = {"type": error_type or "api_error", "message": message or error_type or "stream failed"}
        response["error"] = payload["error"]
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n".encode("utf-8")


def response_completed_event(
    request_id: str,
    model: str | None,
    usage: dict[str, Any] | None = None,
    output: list[dict[str, Any]] | None = None,
    output_text: str | None = None,
) -> bytes:
    return response_stream_event(
        "response.completed",
        request_id,
        model,
        "completed",
        usage=usage,
        output=output,
        output_text=output_text,
    )


def response_failed_event(request_id: str, model: str | None, error_type: str, message: str) -> bytes:
    return response_stream_event("response.failed", request_id, model, "failed", error_type, message)


def probe_cooldown_seconds(reason: str | None, healthy: bool) -> int:
    if healthy or reason == "ok":
        return PROBE_SUCCESS_TTL_SECONDS
    reason = reason or ""
    if responses_request_shape_reason(reason):
        return RESPONSES_INVALID_REQUEST_RETRY_SECONDS
    if responses_real_shape_invalid_reason(reason):
        return RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS
    if reason in {"not_found", "model_unsupported"}:
        return PROBE_UNSUPPORTED_TTL_SECONDS
    if reason in {"auth_or_forbidden", "client_restricted", "provider_config_error"}:
        return PROBE_AUTH_TTL_SECONDS
    if reason == "quota":
        return PROBE_QUOTA_TTL_SECONDS
    if reason == "rate_limited":
        return PROBE_RATE_LIMIT_TTL_SECONDS
    if reason in {"server_unavailable", "empty_stream"}:
        return PROBE_SERVER_ERROR_TTL_SECONDS
    if reason in {"empty_response", "low_signal_response"}:
        return PROBE_LOW_SIGNAL_TTL_SECONDS
    if reason.startswith("exception:"):
        return PROBE_EXCEPTION_TTL_SECONDS
    return PROBE_UNKNOWN_ERROR_TTL_SECONDS


def responses_request_shape_reason(reason: str | None) -> bool:
    return reason in {
        "invalid_request",
        "responses_request_shape_unverified",
        "runtime_failure:invalid_request",
        "runtime_failure:responses_request_shape_unverified",
    }


def responses_real_shape_invalid_reason(reason: str | None) -> bool:
    return reason in {"real_shape_invalid", "runtime_failure:real_shape_invalid"}


def request_shape_fingerprint(body: dict[str, Any], headers: dict[str, str] | None = None) -> str:
    shape = request_shape(body, headers)
    text = json.dumps(shape, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def preserve_probe_state(new_item: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return new_item
    preserved = deepcopy(previous)
    next_probe_at = preserved.get("next_probe_at")
    if not next_probe_at:
        next_probe_at = int(now()) + probe_cooldown_seconds(preserved.get("reason"), bool(preserved.get("healthy")))
    reason = str(preserved.get("reason") or "")
    if responses_request_shape_reason(reason) or responses_real_shape_invalid_reason(reason):
        checked_at = int(preserved.get("checked_at") or now())
        capped_next_probe_at = checked_at + probe_cooldown_seconds(reason, False)
        next_probe_at = min(int(next_probe_at), capped_next_probe_at)
    preserved.update(
        {
            "provider_name": new_item["provider_name"],
            "base_url": new_item["base_url"],
            "local_model": new_item["local_model"],
            "actual_model": new_item["actual_model"],
            "source": new_item.get("source"),
            "kind": new_item["kind"],
            "request_format": preserved.get("request_format") or new_item["request_format"],
            "client_profile": preserved.get("client_profile") or new_item.get("client_profile") or "default",
            "probe_path": preserved.get("probe_path") or new_item["probe_path"],
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


def runtime_failure_cooling_down(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    reason = str(item.get("reason") or "")
    if responses_request_shape_reason(reason):
        return False
    if responses_real_shape_invalid_reason(reason):
        return float(item.get("next_probe_at") or 0) > now()
    return False


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


def normalize_route_tag_value(route_group: str, fallback_only: bool) -> str:
    tags: list[str] = ["gateway-source"]
    if route_group:
        tags.append(f"gw:{route_group}")
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
            if value == "paid":
                route_group = "paid_fallback"
                fallback_only = True
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
            if route_group not in allowed_routes:
                raise ValueError(f"unsupported route_group: {route_group}")
            fallback_only = route_group == "paid_fallback" or parse_bool(update.get("fallback_only"), False)
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
            tag = normalize_route_tag_value(route_group, fallback_only)
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
                row = summary.setdefault(provider_id, {"healthy": 0, "unhealthy": 0, "unverified": 0, "latencies": []})
                if item.get("healthy"):
                    row["healthy"] += 1
                    if item.get("latency_ms") is not None:
                        row["latencies"].append(item.get("latency_ms"))
                elif kind == "responses" and responses_request_shape_reason(str(item.get("reason") or "")):
                    row["unverified"] += 1
                else:
                    row["unhealthy"] += 1
    for row in summary.values():
        latencies = row.pop("latencies", [])
        row["avg_latency_ms"] = int(sum(latencies) / len(latencies)) if latencies else None
    return summary


def build_models_summary() -> list[dict[str, Any]]:
    models = []
    all_models = set((HEALTH.get("chat") or {}).keys()) | set((HEALTH.get("responses") or {}).keys())
    for model in sorted(all_models, key=model_sort_rank):
        chat_items = (HEALTH.get("chat", {}).get(model) or {}).values()
        response_items = (HEALTH.get("responses", {}).get(model) or {}).values()
        chat_ok = sum(1 for item in chat_items if item.get("healthy"))
        responses_ok = sum(1 for item in response_items if item.get("healthy"))
        if chat_ok >= MIN_HEALTHY_PROVIDERS or responses_ok >= MIN_HEALTHY_PROVIDERS:
            models.append({"id": model, "chat_ok": chat_ok, "responses_ok": responses_ok})
    return models


def health_policy_summary() -> dict[str, Any]:
    probe = CONFIG.get("probe") or {}
    chat_probe = probe.get("chat") or {}
    responses_probe = probe.get("responses") or {}
    return {
        "probe_interval_seconds": PROBE_INTERVAL_SECONDS,
        "probe_timeout_seconds": PROBE_TIMEOUT_SECONDS,
        "probe_concurrency": PROBE_CONCURRENCY,
        "probe_max_per_cycle": PROBE_MAX_PER_CYCLE,
        "probe_on_startup": PROBE_ON_STARTUP,
        "models_refresh_seconds": MODELS_REFRESH_SECONDS,
        "enable_responses_probe": ENABLE_RESPONSES_PROBE,
        "min_healthy_providers": MIN_HEALTHY_PROVIDERS,
        "health_fresh_ttl_seconds": HEALTH_FRESH_TTL_SECONDS,
        "probe_content_quality_check": PROBE_CONTENT_QUALITY_CHECK,
        "probe_min_quality_score": PROBE_MIN_QUALITY_SCORE,
        "probe_strategy_version": PROBE_STRATEGY_VERSION,
        "runtime_transient_failure_confirmations": RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS,
        "probe_chat_profiles": ["openai/default", "openai/codex", "anthropic/default", "anthropic/claude-cli", "anthropic/claude-code"],
        "probe_responses_profiles": ["openai/default", "openai/codex", "codex/diagnostic"],
        "adaptive_format_routing": ADAPTIVE_FORMAT_ROUTING,
        "adapter_latency_penalty_ms": ADAPTER_LATENCY_PENALTY_MS,
        "chat_path": chat_probe.get("path") or "/chat/completions",
        "responses_path": responses_probe.get("path") or "/responses",
        "responses_invalid_request_confirmations": RESPONSES_INVALID_REQUEST_CONFIRMATIONS,
        "cooldowns": {
            "success": PROBE_SUCCESS_TTL_SECONDS,
            "model_unsupported": PROBE_UNSUPPORTED_TTL_SECONDS,
            "auth_or_forbidden": PROBE_AUTH_TTL_SECONDS,
            "provider_config_error": PROBE_AUTH_TTL_SECONDS,
            "quota": PROBE_QUOTA_TTL_SECONDS,
            "rate_limited": PROBE_RATE_LIMIT_TTL_SECONDS,
            "server_unavailable": PROBE_SERVER_ERROR_TTL_SECONDS,
            "low_signal_response": PROBE_LOW_SIGNAL_TTL_SECONDS,
            "exception": PROBE_EXCEPTION_TTL_SECONDS,
            "responses_shape_retry": RESPONSES_INVALID_REQUEST_RETRY_SECONDS,
            "responses_real_shape_invalid": RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS,
            "unknown": PROBE_UNKNOWN_ERROR_TTL_SECONDS,
        },
    }


def health_freshness_fields(item: dict[str, Any], current_time: float | None = None) -> dict[str, Any]:
    current_time = now() if current_time is None else current_time
    checked_at = item.get("checked_at")
    next_probe_at = item.get("next_probe_at")
    checked = float(checked_at or 0)
    age = int(max(0, current_time - checked)) if checked else None
    reason = str(item.get("reason") or item.get("skip_reason") or "")
    healthy = bool(item.get("healthy"))
    if not checked:
        status = "unknown"
    elif healthy and age is not None and age <= HEALTH_FRESH_TTL_SECONDS:
        status = "fresh_ok"
    elif healthy:
        status = "stale_ok"
    elif reason in {"pending_probe", "probe_budget_exhausted"}:
        status = "probing"
    elif next_probe_at and float(next_probe_at or 0) > current_time:
        status = "cooldown"
    else:
        status = "stale_fail"
    return {
        "health_age_seconds": age,
        "health_fresh": status == "fresh_ok",
        "health_freshness": status,
        "health_fresh_ttl_seconds": HEALTH_FRESH_TTL_SECONDS,
    }


def health_with_freshness() -> dict[str, Any]:
    current_time = now()
    data = deepcopy(HEALTH)
    for kind_group in data.values():
        for model_group in (kind_group or {}).values():
            for item in (model_group or {}).values():
                if isinstance(item, dict):
                    item.update(health_freshness_fields(item, current_time))
    return data


def model_sort_rank(model: str) -> tuple[int, tuple[int, ...], str]:
    model_id = str(model or "").lower()
    version_rank = tuple(-value for value in model_version_key(model_id))
    if model_id.startswith("gpt") or "/gpt" in model_id:
        return (0, version_rank, model_id)
    if model_id.startswith("claude") or "/claude" in model_id:
        return (1, version_rank, model_id)
    if model_id.startswith("gemini") or "/gemini" in model_id:
        return (2, version_rank, model_id)
    if model_id.startswith("deepseek") or "/deepseek" in model_id:
        return (3, version_rank, model_id)
    if model_id.startswith("glm") or "/glm" in model_id:
        return (4, version_rank, model_id)
    return (9, version_rank, model_id)


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
        "chat_request_format": str(item.get("chat_request_format") or "openai").strip(),
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


PASSTHROUGH_REQUEST_HEADERS = {
    "openai-beta",
    "openai-organization",
    "openai-project",
    "originator",
    "session_id",
    "session-id",
    "thread-id",
    "x-client-request-id",
    "x-codex-beta-features",
    "x-codex-turn-metadata",
    "x-codex-window-id",
    "x-stainless-arch",
    "x-stainless-lang",
    "x-stainless-os",
    "x-stainless-package-version",
    "x-stainless-retry-count",
    "x-stainless-runtime",
    "x-stainless-runtime-version",
    "x-request-id",
    "user-agent",
}


def set_header(headers: dict[str, str], key: str, value: str) -> None:
    for existing in list(headers.keys()):
        if existing.lower() == key.lower():
            headers.pop(existing, None)
    headers[key] = value


def provider_headers(
    provider: dict[str, Any],
    incoming_headers: dict[str, str] | None = None,
    kind: str | None = None,
    extra_headers: dict[str, str] | None = None,
    extra_headers_override: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    for key, value in (incoming_headers or {}).items():
        if key.lower() in PASSTHROUGH_REQUEST_HEADERS and value:
            set_header(headers, key, value)
    if kind == "responses" and not any(key.lower() == "openai-beta" for key in headers):
        set_header(headers, "OpenAI-Beta", "responses=v1")
    if extra_headers_override:
        for key, value in (provider.get("headers") or {}).items():
            set_header(headers, str(key), str(value))
        for key, value in (extra_headers or {}).items():
            if value:
                set_header(headers, str(key), str(value))
    else:
        for key, value in (extra_headers or {}).items():
            if value:
                set_header(headers, str(key), str(value))
        for key, value in (provider.get("headers") or {}).items():
            set_header(headers, str(key), str(value))
    set_header(headers, "Authorization", f"Bearer {provider['api_key']}")
    return headers


def chat_request_format(item: dict[str, Any] | None) -> str:
    value = str((item or {}).get("chat_request_format") or (item or {}).get("request_format") or "openai").strip().lower()
    if value in {"anthropic", "anthropic-chat", "claude", "claude-code"}:
        return "anthropic"
    return "openai"


def request_format_label(provider: dict[str, Any], kind: str) -> str:
    if kind == "chat" and chat_request_format(provider) == "anthropic":
        return "anthropic-chat"
    if kind == "responses":
        return "openai-responses"
    return "openai-compatible"


def anthropic_chat_default_headers() -> dict[str, str]:
    return {
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14",
    }


def normalize_client_profile(profile: Any) -> str:
    value = str(profile or "default").strip().lower().replace("_", "-")
    aliases = {
        "": "default",
        "none": "default",
        "provider": "default",
        "configured": "default",
        "claudecode": "claude-code",
        "claude-code-cli": "claude-code",
        "claudecli": "claude-cli",
        "codex-cli": "codex",
        "codex-exec": "codex",
    }
    return aliases.get(value, value)


def client_profile_headers(profile: Any, request_id: str | None = None, stream: bool = False) -> dict[str, str]:
    normalized = normalize_client_profile(profile)
    if normalized == "codex":
        return codex_compat_adapter_headers(request_id or f"gw_probe_{uuid.uuid4().hex[:12]}", stream)
    if normalized == "claude-cli":
        return {"User-Agent": "claude-cli/2.1.133", **anthropic_chat_default_headers()}
    if normalized == "claude-code":
        return {"User-Agent": "Claude-Code/1.0.0", **anthropic_chat_default_headers()}
    if normalized == "anthropic":
        return anthropic_chat_default_headers()
    return {}


def client_profile_overrides_provider_headers(profile: Any) -> bool:
    return normalize_client_profile(profile) not in {"default", "anthropic"}


def request_shape(body: dict[str, Any], incoming_headers: dict[str, str] | None = None) -> dict[str, Any]:
    headers = incoming_headers or {}
    input_value = body.get("input")
    messages_value = body.get("messages")
    tools_value = body.get("tools")
    input_roles: list[str] = []
    input_content_types: list[str] = []
    message_roles: list[str] = []
    message_content_types: list[str] = []
    tool_types: list[str] = []
    tool_key_sets: list[str] = []
    if isinstance(input_value, list):
        for item in input_value[:20]:
            if isinstance(item, dict):
                role = item.get("role")
                if isinstance(role, str) and role not in input_roles:
                    input_roles.append(role)
                content = item.get("content")
                content_items = content if isinstance(content, list) else [content]
                for content_item in content_items[:20]:
                    if isinstance(content_item, dict):
                        content_type = content_item.get("type")
                        if isinstance(content_type, str) and content_type not in input_content_types:
                            input_content_types.append(content_type)
    if isinstance(messages_value, list):
        for item in messages_value[:20]:
            if isinstance(item, dict):
                role = item.get("role")
                if isinstance(role, str) and role not in message_roles:
                    message_roles.append(role)
                content = item.get("content")
                content_items = content if isinstance(content, list) else [content]
                for content_item in content_items[:20]:
                    if isinstance(content_item, dict):
                        content_type = content_item.get("type")
                    elif isinstance(content_item, str):
                        content_type = "text"
                    elif content_item is None:
                        content_type = "null"
                    else:
                        content_type = type(content_item).__name__
                    if content_type and content_type not in message_content_types:
                        message_content_types.append(str(content_type))
    if isinstance(tools_value, list):
        for tool in tools_value[:20]:
            if not isinstance(tool, dict):
                continue
            tool_type = str(tool.get("type") or "")
            if tool_type and tool_type not in tool_types:
                tool_types.append(tool_type)
            key_set = ",".join(sorted(str(key) for key in tool.keys()))
            if key_set and key_set not in tool_key_sets:
                tool_key_sets.append(key_set)
    return {
        "body_keys": sorted(str(key) for key in body.keys()),
        "input_type": type(input_value).__name__ if "input" in body else "",
        "input_count": len(input_value) if isinstance(input_value, list) else None,
        "input_roles": input_roles,
        "input_content_types": input_content_types,
        "messages_count": len(messages_value) if isinstance(messages_value, list) else None,
        "message_roles": message_roles,
        "message_content_types": message_content_types,
        "has_image_content": any(content_type in {"image_url", "input_image"} for content_type in message_content_types + input_content_types),
        "tools_count": len(tools_value) if isinstance(tools_value, list) else None,
        "tool_types": tool_types,
        "tool_key_sets": tool_key_sets[:6],
        "has_prompt_cache_key": "prompt_cache_key" in body,
        "has_reasoning": "reasoning" in body,
        "has_text": "text" in body,
        "store": body.get("store"),
        "stream": body.get("stream"),
        "max_output_tokens": body.get("max_output_tokens"),
        "metadata_keys": sorted(str(key) for key in (body.get("metadata") or {}).keys()) if isinstance(body.get("metadata"), dict) else [],
        "incoming_header_keys": sorted(
            key.lower()
            for key in headers
            if key.lower() in PASSTHROUGH_REQUEST_HEADERS or key.lower().startswith("x-gateway-")
        ),
    }


def codex_shape_diagnostic_body(model: str, effort: str = "high") -> dict[str, Any]:
    return {
        "model": model,
        "instructions": (
            "You are Codex, a coding agent. This is a gateway diagnostic request. "
            "Do not use tools. Reply exactly: OK"
        ),
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "<permissions instructions>\n"
                            "Filesystem sandboxing is read-only for this diagnostic. "
                            "Do not request tool execution.\n"
                            "</permissions instructions>"
                        ),
                    }
                ],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Do not use tools. Reply exactly: OK"}],
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "exec_command",
                "description": "Diagnostic placeholder tool. Do not call it.",
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                    "additionalProperties": False,
                },
            }
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": {"effort": effort},
        "store": False,
        "stream": True,
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": f"gateway-diagnostic-{model}",
        "text": {"verbosity": "low"},
        "client_metadata": {
            "x-codex-window-id": "gateway-diagnostic:0",
            "x-codex-installation-id": "gateway-diagnostic",
        },
    }


def codex_shape_diagnostic_headers() -> dict[str, str]:
    metadata = {
        "session_id": "gateway-diagnostic",
        "thread_id": "gateway-diagnostic",
        "thread_source": "gateway-admin",
        "turn_id": f"gw_diag_{uuid.uuid4().hex[:12]}",
        "sandbox": "seccomp",
        "request_kind": "turn",
        "window_id": "gateway-diagnostic:0",
    }
    return {
        "accept": "text/event-stream",
        "originator": "codex_exec",
        "user-agent": "codex_exec/0.139.0 (gateway-diagnostic)",
        "x-codex-beta-features": "terminal_resize_reflow",
        "x-codex-turn-metadata": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        "x-codex-window-id": "gateway-diagnostic:0",
        "x-client-request-id": "gateway-diagnostic",
        "session-id": "gateway-diagnostic",
        "thread-id": "gateway-diagnostic",
    }


def codex_compat_adapter_headers(request_id: str, stream: bool) -> dict[str, str]:
    metadata = {
        "session_id": request_id,
        "thread_id": request_id,
        "thread_source": "gateway-chat-adapter",
        "turn_id": request_id,
        "sandbox": "seccomp",
        "request_kind": "turn",
        "window_id": f"gateway-chat-adapter:{request_id[-8:]}",
    }
    return {
        "Accept": "text/event-stream" if stream else "application/json",
        "originator": "codex_exec",
        "user-agent": "codex_exec/0.139.0 (gateway-chat-adapter)",
        "x-codex-beta-features": "terminal_resize_reflow",
        "x-codex-turn-metadata": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        "x-codex-window-id": metadata["window_id"],
        "x-client-request-id": request_id,
        "session-id": request_id,
        "thread-id": request_id,
    }


def event_stream_probe_has_error(text: str) -> bool:
    sample = (text or "").lower()
    return (
        "response.failed" in sample
        or "invalid codex request" in sample
        or bool(re.search(r'"type"\s*:\s*"error"', sample))
        or bool(re.search(r'"error"\s*:\s*\{', sample))
    )


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
    client_restricted = (
        "client_restricted",
        "client restricted",
        "unsupported client",
        "only support codex",
        "only supports codex",
        "only support claude",
        "only supports claude",
        "仅支持 codex",
        "仅支持 claude",
        "客户端受限",
    )
    if any(word in sample for word in client_restricted):
        return "client_restricted"
    unsupported = (
        "not support",
        "unsupported",
        "不支持",
        "model not found",
        "model_not_found",
        "no available channel",
        "模型不存在",
    )
    if any(word in sample for word in unsupported):
        return "model_unsupported"
    provider_config_error = (
        "price not configured",
        "model price not configured",
        "价格未配置",
        "模型价格未配置",
    )
    if any(word in sample for word in provider_config_error):
        return "provider_config_error"
    if status_code == 400 and "invalid_value" in sample and "input" in sample:
        return "client_invalid_input"
    if status_code == 400 and "missing" in sample and ("tools.function" in sample or "tool.function" in sample):
        return "client_invalid_input"
    invalid_request = (
        "invalid codex request",
        "invalid_responses_request",
        "invalid request",
        "invalid_request",
        "missing `partial` parameter",
    )
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


LOW_SIGNAL_RESPONSE_TEXTS = {
    "1",
    "done",
    "hello",
    "hi",
    "no",
    "ok",
    "okay",
    "ping",
    "pong",
    "success",
    "true",
    "yes",
    "不",
    "可以",
    "否",
    "嗯",
    "好",
    "好的",
    "是",
    "收到",
    "明白",
}


def normalize_signal_text(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"[\s`*_#>\"'“”‘’.,!?;:，。！？；：、（）()\[\]{}<>-]+", "", lowered)


def is_low_signal_response_text(text: str) -> bool:
    normalized = normalize_signal_text(text)
    if not normalized:
        return True
    if normalized in LOW_SIGNAL_RESPONSE_TEXTS:
        return True
    return len(normalized) <= 2


def score_response_text(text: str) -> int:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return 0
    score = min(len(cleaned), 240)
    normalized = normalize_signal_text(cleaned)
    if len(normalized) >= 8 or len(cleaned.split()) >= 3:
        score += 20
    if re.search(r"[\u4e00-\u9fff]", cleaned):
        score += 20
    if re.search(r"[，。！？,.!?;:]", cleaned):
        score += 10
    if not is_low_signal_response_text(cleaned):
        score += 120
    return score


TOOL_LOOP_TEXT_PATTERNS = (
    "tool invocation",
    "tool invocations",
    "tool invocation errors",
    "properly formatted tool",
    "correct tool format",
    "correct tool names",
    "wrong format",
    "xml invocation format",
    "available tools directly",
    "repeated errors",
)


def tool_loop_text_detected(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in TOOL_LOOP_TEXT_PATTERNS)


def iter_text_fragments(value: Any) -> list[str]:
    fragments: list[str] = []
    stack = [value]
    while stack and len(" ".join(fragments)) < 20000:
        current = stack.pop()
        if isinstance(current, str):
            fragments.append(current)
        elif isinstance(current, list):
            stack.extend(reversed(current))
        elif isinstance(current, dict):
            for key in ("text", "content", "input_text", "output_text"):
                if key in current:
                    stack.append(current[key])
            if "summary" in current:
                stack.append(current["summary"])
    return fragments


def request_has_tools(body: dict[str, Any]) -> bool:
    tools = body.get("tools")
    return isinstance(tools, list) and bool(tools)


def request_has_tool_loop_history(body: dict[str, Any]) -> bool:
    if not request_has_tools(body):
        return False
    text = " ".join(iter_text_fragments(body.get("input") if "input" in body else body.get("messages")))
    return tool_loop_text_detected(text)


def probe_response_text(data: Any, kind: str) -> str:
    if kind == "chat":
        return extract_chat_response_text(data)
    if kind == "responses":
        return extract_responses_output_text(data)
    return ""


def probe_content_quality_result(data: Any, kind: str) -> dict[str, Any]:
    if not PROBE_CONTENT_QUALITY_CHECK:
        return {"healthy": True, "quality_checked": False}
    text = probe_response_text(data, kind)
    score = score_response_text(text)
    sample = redact_text(text, 300)
    if score < PROBE_MIN_QUALITY_SCORE:
        reason = "empty_response" if not str(text or "").strip() else "low_signal_response"
        return {
            "healthy": False,
            "reason": reason,
            "quality_checked": True,
            "quality_score": score,
            "sample": sample,
        }
    return {
        "healthy": True,
        "quality_checked": True,
        "quality_score": score,
        "sample": sample,
    }


def upstream_path_for_kind(kind: str) -> str:
    return "/responses" if kind == "responses" else "/chat/completions"


def apply_responses_provider_defaults(body: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    key = provider_compat_key(target)
    configured = target.get("responses_defaults") or target.get("response_defaults") or {}
    learned = RESPONSES_COMPAT_DEFAULTS.get(key) or {}
    partial_default = configured.get("partial") if isinstance(configured, dict) else None
    if partial_default is None:
        partial_default = learned.get("partial")
    if partial_default == "stream_bool" and "partial" not in body:
        body["partial"] = bool(body.get("stream", False))
    elif isinstance(partial_default, bool) and "partial" not in body:
        body["partial"] = partial_default
    return body


def provider_compat_key(target: dict[str, Any]) -> str:
    return str(target.get("provider_id") or target.get("id") or target.get("base_url") or "")


def missing_partial_parameter(status_code: int, text: str) -> bool:
    sample = (text or "").lower()
    return status_code == 400 and "partial" in sample and (
        "missing" in sample or "required" in sample or "missingparameter" in sample
    )


def learn_responses_partial_default(target: dict[str, Any]) -> None:
    key = provider_compat_key(target)
    if key:
        RESPONSES_COMPAT_DEFAULTS.setdefault(key, {})["partial"] = "stream_bool"


def can_retry_with_partial(kind: str, status_code: int, text: str, body: dict[str, Any]) -> bool:
    return kind == "responses" and "partial" not in body and missing_partial_parameter(status_code, text)


def safe_text_from_content(content: Any) -> str | None:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                return None
            part_type = str(part.get("type") or "")
            if part_type in {"text", "input_text", "output_text"}:
                parts.append(str(part.get("text") or ""))
            else:
                return None
        return "\n".join(text for text in parts if text)
    return None


def safe_instruction_text(content: Any) -> str | None:
    text = safe_text_from_content(content)
    if text is not None:
        return text
    if isinstance(content, dict):
        if "content" in content:
            return safe_instruction_text(content.get("content"))
        if "text" in content:
            return str(content.get("text") or "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            item_text = safe_instruction_text(item)
            if item_text is None:
                return None
            if item_text:
                parts.append(item_text)
        return "\n".join(parts)
    return None


def merge_chat_response_instructions(instructions: str, body: dict[str, Any]) -> str:
    parts = [instructions] if instructions else []
    if "system" in body:
        system_text = safe_instruction_text(body.get("system"))
        if system_text is None:
            system_text = json.dumps(body.get("system"), ensure_ascii=False, separators=(",", ":"))
        if system_text:
            parts.insert(0, system_text)
    return "\n\n".join(parts)


def anthropic_image_source_url(source: Any) -> str:
    if isinstance(source, str):
        return source.strip()
    if not isinstance(source, dict):
        return ""
    source_type = str(source.get("type") or "")
    if source.get("url"):
        return str(source.get("url") or "").strip()
    if source_type == "base64":
        media_type = str(source.get("media_type") or "image/png")
        data = str(source.get("data") or "").strip()
        if data:
            return f"data:{media_type};base64,{data}"
    return ""


def tool_output_text(content: Any) -> str | None:
    text = safe_text_from_content(content)
    if text is not None:
        return text
    if isinstance(content, dict):
        content_type = str(content.get("type") or "")
        if content_type == "tool_result":
            return tool_output_text(content.get("content"))
        if content_type in {"text", "input_text", "output_text"}:
            return str(content.get("text") or "")
        if "content" in content:
            return tool_output_text(content.get("content"))
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            item_text = tool_output_text(item)
            if item_text is None:
                return None
            if item_text:
                parts.append(item_text)
        return "\n".join(parts)
    return None


def append_responses_message(inputs: list[dict[str, Any]], role: str, content_parts: list[dict[str, Any]]) -> None:
    if content_parts or role == "user":
        inputs.append(
            {
                "type": "message",
                "role": role,
                "content": content_parts or [{"type": "input_text", "text": ""}],
            }
        )


def codex_responses_content_from_chat_content(content: Any, role: str) -> list[dict[str, Any]] | None:
    text_type = "input_text" if role == "user" else "output_text"
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": text_type, "text": content}] if content or role == "user" else []
    if not isinstance(content, list):
        return None
    converted: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            if part or role == "user":
                converted.append({"type": text_type, "text": part})
            continue
        if not isinstance(part, dict):
            return None
        part_type = str(part.get("type") or "")
        if part_type in {"text", "input_text", "output_text"}:
            text = str(part.get("text") or "")
            if text or role == "user":
                converted.append({"type": text_type, "text": text})
            continue
        if part_type in {"thinking", "redacted_thinking"}:
            continue
        if part_type == "image_url":
            if role != "user":
                return None
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url") or "").strip()
                detail = image_url.get("detail")
            elif isinstance(image_url, str):
                url = image_url.strip()
                detail = part.get("detail")
            else:
                url = str(part.get("url") or "").strip()
                detail = part.get("detail")
            if not url:
                return None
            item: dict[str, Any] = {"type": "input_image", "image_url": url}
            if detail:
                item["detail"] = str(detail)
            converted.append(item)
            continue
        if part_type == "image":
            if role != "user":
                return None
            url = anthropic_image_source_url(part.get("source"))
            if not url:
                return None
            item = {"type": "input_image", "image_url": url}
            if part.get("detail"):
                item["detail"] = str(part.get("detail"))
            converted.append(item)
            continue
        if part_type == "input_image":
            if role != "user":
                return None
            item: dict[str, Any] = {"type": "input_image"}
            image_url = part.get("image_url") or part.get("url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if image_url:
                item["image_url"] = str(image_url)
            file_id = part.get("file_id")
            if file_id:
                item["file_id"] = str(file_id)
            detail = part.get("detail")
            if detail:
                item["detail"] = str(detail)
            if "image_url" not in item and "file_id" not in item:
                return None
            converted.append(item)
            continue
        if part_type in {"tool_use", "tool_result"}:
            return None
        return None
    return converted


def chat_content_from_responses_content(content: Any, role: str) -> str | list[dict[str, Any]] | None:
    if content is None:
        return "" if role != "user" else []
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            parts.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            return None
        part_type = str(part.get("type") or "")
        if part_type in {"text", "input_text", "output_text"}:
            parts.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        if part_type in {"image_url", "input_image", "image"}:
            if role != "user":
                return None
            image_part = chat_image_url_part(part)
            if image_part is None:
                return None
            parts.append(image_part)
            continue
        return None
    if not parts:
        return "" if role != "user" else []
    if all(part.get("type") == "text" for part in parts):
        return "\n".join(str(part.get("text") or "") for part in parts)
    return parts


def append_chat_message_from_responses_message(messages: list[dict[str, Any]], item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "user")
    if role == "developer":
        role = "system"
    if role not in {"system", "user", "assistant"}:
        return False
    content = chat_content_from_responses_content(item.get("content"), role)
    if content is None:
        return False
    messages.append({"role": role, "content": content})
    return True


def chat_messages_from_responses_input(input_value: Any) -> list[dict[str, Any]] | None:
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if not isinstance(input_value, list):
        return None
    messages: list[dict[str, Any]] = []
    for item in input_value:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "")
        if item_type in {"function_call", "tool_call"}:
            name = str(item.get("name") or "").strip()
            if not name:
                return None
            arguments = item.get("arguments")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:16]}"),
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            )
            continue
        if item_type in {"function_call_output", "tool_result"}:
            call_id = str(item.get("call_id") or item.get("tool_call_id") or item.get("tool_use_id") or "").strip()
            output = tool_output_text(item.get("output") if "output" in item else item.get("content"))
            if not call_id or output is None:
                return None
            messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
            continue
        if item_type in {"", "message"}:
            if not append_chat_message_from_responses_message(messages, item):
                return None
            continue
        return None
    return messages


def responses_input_from_chat_messages(messages: Any) -> tuple[str, list[dict[str, Any]]] | None:
    return codex_responses_input_from_chat_messages(messages)


def codex_responses_input_from_chat_messages(messages: Any) -> tuple[str, list[dict[str, Any]]] | None:
    if not isinstance(messages, list) or not messages:
        return None
    instructions: list[str] = []
    inputs: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "user")
        if role in {"system", "developer"}:
            content = safe_text_from_content(item.get("content"))
            if content is None:
                return None
            if content:
                instructions.append(content)
            continue
        if role in {"user", "assistant"}:
            raw_content = item.get("content")
            content_items = raw_content if isinstance(raw_content, list) else [raw_content]
            content_parts: list[dict[str, Any]] = []
            structural_content_seen = False
            for content_item in content_items:
                if isinstance(content_item, dict):
                    content_type = str(content_item.get("type") or "")
                    if content_type == "tool_use":
                        if role != "assistant":
                            return None
                        structural_content_seen = True
                        if content_parts:
                            append_responses_message(inputs, role, content_parts)
                        content_parts = []
                        name = str(content_item.get("name") or "").strip()
                        if not name:
                            return None
                        arguments = content_item.get("input")
                        if not isinstance(arguments, str):
                            arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
                        inputs.append(
                            {
                                "type": "function_call",
                                "call_id": str(content_item.get("id") or f"call_{uuid.uuid4().hex[:16]}"),
                                "name": name,
                                "arguments": arguments,
                            }
                        )
                        continue
                    if content_type == "tool_result":
                        if role != "user":
                            return None
                        structural_content_seen = True
                        if content_parts:
                            append_responses_message(inputs, role, content_parts)
                        content_parts = []
                        call_id = str(content_item.get("tool_use_id") or content_item.get("tool_call_id") or content_item.get("id") or "").strip()
                        output = tool_output_text(content_item.get("content"))
                        if not call_id or output is None:
                            return None
                        inputs.append({"type": "function_call_output", "call_id": call_id, "output": output})
                        continue
                part_content = None if content_item is None else [content_item]
                converted_parts = codex_responses_content_from_chat_content(part_content, role)
                if converted_parts is None:
                    return None
                content_parts.extend(converted_parts)
            if content_parts or (role == "user" and not structural_content_seen):
                append_responses_message(inputs, role, content_parts)
            tool_calls = item.get("tool_calls")
            if tool_calls is not None:
                if role != "assistant" or not isinstance(tool_calls, list):
                    return None
                for call in tool_calls:
                    if not isinstance(call, dict) or str(call.get("type") or "function") != "function":
                        return None
                    function = call.get("function") if isinstance(call.get("function"), dict) else {}
                    name = str(function.get("name") or "").strip()
                    if not name:
                        return None
                    arguments = function.get("arguments")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
                    inputs.append(
                        {
                            "type": "function_call",
                            "call_id": str(call.get("id") or f"call_{uuid.uuid4().hex[:16]}"),
                            "name": name,
                            "arguments": arguments,
                        }
                    )
            continue
        if role == "tool":
            content = safe_text_from_content(item.get("content"))
            if content is None:
                return None
            call_id = str(item.get("tool_call_id") or item.get("call_id") or "").strip()
            if not call_id:
                return None
            inputs.append({"type": "function_call_output", "call_id": call_id, "output": content})
            continue
        return None
    if not inputs:
        return None
    return "\n\n".join(instructions), inputs


def openai_chat_tools_passthrough_compatible(tools: Any) -> bool:
    if tools is None:
        return True
    if not isinstance(tools, list):
        return False
    for tool in tools:
        if not isinstance(tool, dict):
            return False
        if str(tool.get("type") or "function") != "function":
            return False
        function = tool.get("function")
        if not isinstance(function, dict) or not str(function.get("name") or "").strip():
            return False
    return True


def openai_chat_messages_passthrough_compatible(messages: Any) -> bool:
    if not isinstance(messages, list) or not messages:
        return False
    for item in messages:
        if not isinstance(item, dict):
            return False
        role = str(item.get("role") or "user")
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            return False
        content = item.get("content")
        if content is None:
            if role != "assistant":
                return False
            continue
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            return False
        for part in content:
            if isinstance(part, str):
                continue
            if not isinstance(part, dict):
                return False
            part_type = str(part.get("type") or "")
            if part_type not in {"text", "image_url"}:
                return False
            if part_type == "image_url" and role != "user":
                return False
    return True


def function_tool_from_schema(tool: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
    name = str(schema.get("name") or "").strip()
    if not name:
        return None
    parameters = schema.get("parameters")
    if not isinstance(parameters, dict):
        parameters = schema.get("input_schema")
    item: dict[str, Any] = {
        "type": "function",
        "name": name,
        "description": str(schema.get("description") or ""),
        "parameters": parameters if isinstance(parameters, dict) else {"type": "object", "properties": {}},
    }
    strict = schema.get("strict")
    if strict is None:
        strict = tool.get("strict")
    if strict is not None:
        item["strict"] = bool(strict)
    return item


def responses_tools_from_chat_tools(tools: Any) -> list[dict[str, Any]] | None:
    if tools is None:
        return []
    if not isinstance(tools, list):
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            return None
        tool_type = str(tool.get("type") or "")
        if isinstance(tool.get("function"), dict):
            item = function_tool_from_schema(tool, tool["function"])
        elif tool.get("name") and (tool_type in {"", "function"} or "parameters" in tool or "input_schema" in tool):
            item = function_tool_from_schema(tool, tool)
        elif tool_type and tool_type != "function" and "function" not in tool:
            item = deepcopy(tool)
        else:
            item = None
        if item is None:
            return None
        converted.append(item)
    return converted


def responses_tool_choice_from_chat_tool_choice(tool_choice: Any) -> Any:
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    if isinstance(tool_choice, dict):
        choice_type = str(tool_choice.get("type") or "")
        if choice_type in {"auto", "none", "required"}:
            return choice_type
        if choice_type == "any":
            return "required"
        function = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
        name = str(function.get("name") or tool_choice.get("name") or "").strip()
        if name and choice_type in {"", "function", "tool"}:
            return {"type": "function", "name": name}
    return None


def chat_tools_from_any_tools(tools: Any) -> list[dict[str, Any]] | None:
    response_tools = responses_tools_from_chat_tools(tools)
    if response_tools is None:
        return None
    converted: list[dict[str, Any]] = []
    for tool in response_tools:
        if not isinstance(tool, dict) or str(tool.get("type") or "") != "function":
            return None
        name = str(tool.get("name") or "").strip()
        if not name:
            return None
        function: dict[str, Any] = {
            "name": name,
            "description": str(tool.get("description") or ""),
            "parameters": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {"type": "object", "properties": {}},
        }
        if "strict" in tool:
            function["strict"] = bool(tool.get("strict"))
        converted.append({"type": "function", "function": function})
    return converted


def chat_tool_choice_from_any_tool_choice(tool_choice: Any) -> Any:
    choice = responses_tool_choice_from_chat_tool_choice(tool_choice)
    if choice is None:
        return None
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "function", "function": {"name": choice.get("name")}}
    return choice


def anthropic_tools_from_any_tools(tools: Any) -> list[dict[str, Any]] | None:
    response_tools = responses_tools_from_chat_tools(tools)
    if response_tools is None:
        return None
    converted: list[dict[str, Any]] = []
    for tool in response_tools:
        if not isinstance(tool, dict) or str(tool.get("type") or "") != "function":
            return None
        name = str(tool.get("name") or "").strip()
        if not name:
            return None
        converted.append(
            {
                "name": name,
                "description": str(tool.get("description") or ""),
                "input_schema": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {"type": "object", "properties": {}},
            }
        )
    return converted


def anthropic_tool_choice_from_any_tool_choice(tool_choice: Any) -> Any:
    choice = responses_tool_choice_from_chat_tool_choice(tool_choice)
    if choice is None:
        return None
    if isinstance(choice, str):
        if choice == "required":
            return {"type": "any"}
        return {"type": choice}
    if isinstance(choice, dict) and choice.get("type") == "function":
        name = str(choice.get("name") or "").strip()
        if name:
            return {"type": "tool", "name": name}
    return None


def chat_image_url_part(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = str(part.get("type") or "")
    if part_type == "image_url":
        image_url = part.get("image_url")
        item: dict[str, Any] = {"type": "image_url"}
        if isinstance(image_url, dict):
            item["image_url"] = deepcopy(image_url)
        elif isinstance(image_url, str):
            item["image_url"] = {"url": image_url}
        else:
            url = str(part.get("url") or "").strip()
            if not url:
                return None
            item["image_url"] = {"url": url}
        if part.get("detail") and isinstance(item.get("image_url"), dict):
            item["image_url"]["detail"] = str(part.get("detail"))
        return item
    if part_type in {"input_image", "image"}:
        url = ""
        if part_type == "image":
            url = anthropic_image_source_url(part.get("source"))
        else:
            image_url = part.get("image_url") or part.get("url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            url = str(image_url or "").strip()
        if not url:
            return None
        item = {"type": "image_url", "image_url": {"url": url}}
        if part.get("detail"):
            item["image_url"]["detail"] = str(part.get("detail"))
        return item
    return None


def anthropic_image_part_from_chat_image(part: dict[str, Any]) -> dict[str, Any] | None:
    image_part = chat_image_url_part(part)
    if image_part is None:
        return None
    image_url = image_part.get("image_url") if isinstance(image_part.get("image_url"), dict) else {}
    url = str(image_url.get("url") or "").strip()
    if not url:
        return None
    source: dict[str, Any]
    if url.startswith("data:") and ";base64," in url:
        header, data = url.split(";base64,", 1)
        media_type = header.removeprefix("data:") or "image/png"
        source = {"type": "base64", "media_type": media_type, "data": data}
    else:
        source = {"type": "url", "url": url}
    item = {"type": "image", "source": source}
    if isinstance(image_url, dict) and image_url.get("detail"):
        item["detail"] = str(image_url.get("detail"))
    return item


def anthropic_content_from_chat_content(content: Any) -> list[dict[str, Any]] | None:
    if content is None:
        return []
    items = content if isinstance(content, list) else [content]
    parts: list[dict[str, Any]] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            parts.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            return None
        content_type = str(item.get("type") or "")
        if content_type in {"text", "input_text", "output_text"}:
            parts.append({"type": "text", "text": str(item.get("text") or "")})
            continue
        if content_type in {"image_url", "input_image", "image"}:
            image_part = anthropic_image_part_from_chat_image(item)
            if image_part is None:
                return None
            parts.append(image_part)
            continue
        if content_type == "tool_result":
            call_id = str(item.get("tool_use_id") or item.get("tool_call_id") or item.get("id") or "").strip()
            output = tool_output_text(item.get("content"))
            if not call_id or output is None:
                return None
            parts.append({"type": "tool_result", "tool_use_id": call_id, "content": output})
            continue
        return None
    return parts


def anthropic_chat_body_from_openai_chat_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    messages = chat_messages_from_mixed_chat_messages(body.get("messages"), body)
    if messages is None:
        raise ValueError("chat body cannot be safely normalized for anthropic chat upstream")
    tools = anthropic_tools_from_any_tools(body.get("tools"))
    if tools is None:
        raise ValueError("chat tools cannot be safely normalized for anthropic chat upstream")
    req_body: dict[str, Any] = {"model": chosen["actual_model"], "messages": []}
    system_parts: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        if role == "system":
            text = safe_instruction_text(message.get("content"))
            if text is None:
                raise ValueError("chat system content cannot be safely normalized for anthropic chat upstream")
            if text:
                system_parts.append({"type": "text", "text": text})
            continue
        if role == "tool":
            call_id = str(message.get("tool_call_id") or message.get("call_id") or "").strip()
            output = tool_output_text(message.get("content"))
            if not call_id or output is None:
                raise ValueError("chat tool result cannot be safely normalized for anthropic chat upstream")
            req_body["messages"].append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": output}]})
            continue
        if role not in {"user", "assistant"}:
            raise ValueError("chat role cannot be safely normalized for anthropic chat upstream")
        content_parts = anthropic_content_from_chat_content(message.get("content"))
        if content_parts is None:
            raise ValueError("chat content cannot be safely normalized for anthropic chat upstream")
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    raise ValueError("chat tool call cannot be safely normalized for anthropic chat upstream")
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = str(function.get("name") or "").strip()
                if not name:
                    raise ValueError("chat tool call name is required for anthropic chat upstream")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments) if arguments else {}
                    except Exception:
                        arguments = {"arguments": arguments}
                if not isinstance(arguments, dict):
                    arguments = {"value": arguments}
                content_parts.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or f"call_{uuid.uuid4().hex[:16]}"),
                        "name": name,
                        "input": arguments,
                    }
                )
        req_body["messages"].append({"role": role, "content": content_parts or [{"type": "text", "text": ""}]})
    if system_parts:
        req_body["system"] = system_parts
    if "max_tokens" in body:
        req_body["max_tokens"] = body.get("max_tokens")
    elif "max_output_tokens" in body:
        req_body["max_tokens"] = body.get("max_output_tokens")
    if tools:
        req_body["tools"] = tools
        tool_choice = anthropic_tool_choice_from_any_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            req_body["tool_choice"] = tool_choice
    for key in ("temperature", "top_p", "stream", "stop", "metadata"):
        if key in body:
            req_body[key] = body[key]
    return req_body


def append_chat_user_message(messages: list[dict[str, Any]], content_parts: list[dict[str, Any]]) -> None:
    if not content_parts:
        return
    if any(part.get("type") == "image_url" for part in content_parts):
        messages.append({"role": "user", "content": content_parts})
        return
    text = "\n".join(str(part.get("text") or "") for part in content_parts if part.get("type") == "text")
    messages.append({"role": "user", "content": text})


def chat_messages_from_mixed_chat_messages(messages_value: Any, body: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(messages_value, list):
        return None
    messages: list[dict[str, Any]] = []
    if "system" in body:
        system_text = safe_instruction_text(body.get("system"))
        if system_text is None:
            system_text = json.dumps(body.get("system"), ensure_ascii=False, separators=(",", ":"))
        if system_text:
            messages.append({"role": "system", "content": system_text})
    for item in messages_value:
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "user")
        if role in {"system", "developer"}:
            content = safe_instruction_text(item.get("content"))
            if content is None:
                return None
            if content:
                messages.append({"role": "system", "content": content})
            continue
        if role == "tool":
            content = tool_output_text(item.get("content"))
            call_id = str(item.get("tool_call_id") or item.get("call_id") or "").strip()
            if content is None or not call_id:
                return None
            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
            continue
        if role == "user":
            raw_content = item.get("content")
            content_items = raw_content if isinstance(raw_content, list) else [raw_content]
            content_parts: list[dict[str, Any]] = []
            for content_item in content_items:
                if content_item is None:
                    continue
                if isinstance(content_item, str):
                    content_parts.append({"type": "text", "text": content_item})
                    continue
                if not isinstance(content_item, dict):
                    return None
                content_type = str(content_item.get("type") or "")
                if content_type in {"text", "input_text", "output_text"}:
                    content_parts.append({"type": "text", "text": str(content_item.get("text") or "")})
                    continue
                if content_type in {"image_url", "input_image", "image"}:
                    image_part = chat_image_url_part(content_item)
                    if image_part is None:
                        return None
                    content_parts.append(image_part)
                    continue
                if content_type == "tool_result":
                    append_chat_user_message(messages, content_parts)
                    content_parts = []
                    call_id = str(content_item.get("tool_use_id") or content_item.get("tool_call_id") or content_item.get("id") or "").strip()
                    output = tool_output_text(content_item.get("content"))
                    if not call_id or output is None:
                        return None
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                    continue
                if content_type in {"thinking", "redacted_thinking"}:
                    continue
                return None
            append_chat_user_message(messages, content_parts)
            if raw_content is None:
                messages.append({"role": "user", "content": ""})
            continue
        if role == "assistant":
            raw_content = item.get("content")
            content_items = raw_content if isinstance(raw_content, list) else [raw_content]
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for content_item in content_items:
                if content_item is None:
                    continue
                if isinstance(content_item, str):
                    text_parts.append(content_item)
                    continue
                if not isinstance(content_item, dict):
                    return None
                content_type = str(content_item.get("type") or "")
                if content_type in {"text", "input_text", "output_text"}:
                    text_parts.append(str(content_item.get("text") or ""))
                    continue
                if content_type in {"thinking", "redacted_thinking"}:
                    continue
                if content_type == "tool_use":
                    name = str(content_item.get("name") or "").strip()
                    if not name:
                        return None
                    arguments = content_item.get("input")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
                    tool_calls.append(
                        {
                            "id": str(content_item.get("id") or f"call_{uuid.uuid4().hex[:16]}"),
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    )
                    continue
                return None
            existing_tool_calls = item.get("tool_calls")
            if existing_tool_calls is not None:
                if not isinstance(existing_tool_calls, list):
                    return None
                tool_calls.extend(deepcopy(existing_tool_calls))
            content = "\n".join(text for text in text_parts if text)
            if content or tool_calls or raw_content is None:
                message: dict[str, Any] = {"role": "assistant", "content": content if content else None}
                if tool_calls:
                    message["tool_calls"] = tool_calls
                messages.append(message)
            continue
        return None
    return messages


RESPONSES_TO_CHAT_UNSAFE_FIELDS = {
    "reasoning",
    "include",
    "prompt_cache_key",
    "previous_response_id",
    "text",
    "truncation",
    "client_metadata",
}
CHAT_TO_RESPONSES_UNSAFE_FIELDS = {
    "functions",
    "function_call",
    "response_format",
}
CHAT_TO_CODEX_RESPONSES_UNSAFE_FIELDS = {
    "functions",
    "function_call",
    "response_format",
}


def responses_body_can_use_chat_adapter(body: dict[str, Any]) -> bool:
    if any(field in body for field in RESPONSES_TO_CHAT_UNSAFE_FIELDS):
        return False
    if chat_tools_from_any_tools(body.get("tools")) is None:
        return False
    if "tool_choice" in body and chat_tool_choice_from_any_tool_choice(body.get("tool_choice")) is None:
        return False
    if "parallel_tool_calls" in body and not isinstance(body.get("parallel_tool_calls"), bool):
        return False
    return chat_messages_from_responses_input(body.get("input")) is not None


def chat_body_can_use_native_chat_upstream(body: dict[str, Any]) -> bool:
    try:
        chat_body_to_chat_upstream_body(body, {"actual_model": str(body.get("model") or "")})
        return True
    except ValueError:
        return False


def chat_body_can_use_responses_adapter(body: dict[str, Any]) -> bool:
    if any(field in body for field in CHAT_TO_RESPONSES_UNSAFE_FIELDS):
        return False
    if responses_tools_from_chat_tools(body.get("tools")) is None:
        return False
    if "tool_choice" in body and responses_tool_choice_from_chat_tool_choice(body.get("tool_choice")) is None:
        return False
    if "parallel_tool_calls" in body and not isinstance(body.get("parallel_tool_calls"), bool):
        return False
    return responses_input_from_chat_messages(body.get("messages")) is not None


def chat_body_can_use_codex_compat_responses_adapter(body: dict[str, Any]) -> bool:
    if any(field in body for field in CHAT_TO_CODEX_RESPONSES_UNSAFE_FIELDS):
        return False
    if responses_tools_from_chat_tools(body.get("tools")) is None:
        return False
    if "tool_choice" in body and responses_tool_choice_from_chat_tool_choice(body.get("tool_choice")) is None:
        return False
    if "parallel_tool_calls" in body and not isinstance(body.get("parallel_tool_calls"), bool):
        return False
    return codex_responses_input_from_chat_messages(body.get("messages")) is not None


def adapter_name(client_kind: str, upstream_kind: str) -> str:
    return "native" if client_kind == upstream_kind else f"{upstream_kind}_to_{client_kind}"


def responses_body_to_chat_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    messages = chat_messages_from_responses_input(body.get("input"))
    if messages is None:
        raise ValueError("responses body cannot be safely adapted to chat")
    tools = chat_tools_from_any_tools(body.get("tools"))
    if tools is None:
        raise ValueError("responses tools cannot be safely adapted to chat")
    instructions = body.get("instructions")
    if instructions:
        messages = [{"role": "system", "content": str(instructions)}, *messages]
    req_body: dict[str, Any] = {"model": chosen["actual_model"], "messages": messages}
    if "max_output_tokens" in body:
        req_body["max_tokens"] = body.get("max_output_tokens")
    if tools:
        req_body["tools"] = tools
        tool_choice = chat_tool_choice_from_any_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            req_body["tool_choice"] = tool_choice
        if "parallel_tool_calls" in body:
            req_body["parallel_tool_calls"] = bool(body.get("parallel_tool_calls"))
    for key in ("temperature", "top_p", "stream", "stream_options", "stop", "user", "metadata"):
        if key in body:
            req_body[key] = body[key]
    return req_body


def chat_body_to_chat_upstream_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    messages = chat_messages_from_mixed_chat_messages(body.get("messages"), body)
    if messages is None:
        raise ValueError("chat body cannot be safely normalized for chat upstream")
    tools = chat_tools_from_any_tools(body.get("tools"))
    if tools is None:
        raise ValueError("chat tools cannot be safely normalized for chat upstream")
    req_body: dict[str, Any] = {"model": chosen["actual_model"], "messages": messages}
    if "max_tokens" in body:
        req_body["max_tokens"] = body.get("max_tokens")
    if tools:
        req_body["tools"] = tools
        tool_choice = chat_tool_choice_from_any_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            req_body["tool_choice"] = tool_choice
        if "parallel_tool_calls" in body:
            req_body["parallel_tool_calls"] = bool(body.get("parallel_tool_calls"))
    for key in (
        "temperature",
        "top_p",
        "stream",
        "stream_options",
        "stop",
        "user",
        "metadata",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "logprobs",
        "top_logprobs",
        "n",
        "reasoning_effort",
    ):
        if key in body:
            req_body[key] = body[key]
    return req_body


def chat_body_to_responses_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    converted = responses_input_from_chat_messages(body.get("messages"))
    if converted is None:
        raise ValueError("chat body cannot be safely adapted to responses")
    tools = responses_tools_from_chat_tools(body.get("tools"))
    if tools is None:
        raise ValueError("chat tools cannot be safely adapted to responses")
    instructions, input_value = converted
    req_body: dict[str, Any] = {
        "model": chosen["actual_model"],
        "input": input_value,
        "instructions": merge_chat_response_instructions(instructions, body),
        "store": False,
    }
    if "max_tokens" in body:
        req_body["max_output_tokens"] = body.get("max_tokens")
    if tools:
        req_body["tools"] = tools
        tool_choice = responses_tool_choice_from_chat_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            req_body["tool_choice"] = tool_choice
        if "parallel_tool_calls" in body:
            req_body["parallel_tool_calls"] = bool(body.get("parallel_tool_calls"))
    for key in ("temperature", "top_p", "stream", "stop", "user", "metadata"):
        if key in body:
            req_body[key] = body[key]
    return req_body


def chat_body_to_codex_compat_responses_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    converted = codex_responses_input_from_chat_messages(body.get("messages"))
    if converted is None:
        raise ValueError("chat body cannot be safely adapted to codex-compatible responses")
    tools = responses_tools_from_chat_tools(body.get("tools"))
    if tools is None:
        raise ValueError("chat tools cannot be safely adapted to codex-compatible responses")
    instructions, input_value = converted
    effort = "low"
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("effort"):
        effort = str(reasoning["effort"])
    elif body.get("reasoning_effort"):
        effort = str(body["reasoning_effort"])
    req_body = codex_shape_diagnostic_body(chosen["actual_model"], effort=effort)
    for key in ("tools", "tool_choice", "parallel_tool_calls"):
        req_body.pop(key, None)
    req_body["instructions"] = merge_chat_response_instructions(instructions, body)
    req_body["input"] = input_value
    req_body["store"] = False
    req_body["stream"] = bool(body.get("stream", False))
    req_body["prompt_cache_key"] = f"gateway-chat-adapter-{chosen['actual_model']}"
    req_body["client_metadata"] = {
        "x-codex-window-id": f"gateway-chat-adapter:{chosen['actual_model']}",
        "x-codex-installation-id": "gateway-chat-adapter",
    }
    if "max_tokens" in body:
        req_body["max_output_tokens"] = body.get("max_tokens")
    if tools:
        req_body["tools"] = tools
        tool_choice = responses_tool_choice_from_chat_tool_choice(body.get("tool_choice"))
        if tool_choice is not None:
            req_body["tool_choice"] = tool_choice
        if "parallel_tool_calls" in body:
            req_body["parallel_tool_calls"] = bool(body.get("parallel_tool_calls"))
    for key in ("temperature", "top_p", "stop", "user", "metadata"):
        if key in body:
            req_body[key] = body[key]
    return req_body


def prepare_upstream_body(body: dict[str, Any], chosen: dict[str, Any], client_kind: str) -> dict[str, Any]:
    upstream_kind = chosen.get("_upstream_kind") or client_kind
    if upstream_kind == client_kind:
        if upstream_kind == "responses":
            req_body = normalize_responses_upstream_body(body, chosen)
        elif upstream_kind == "chat":
            req_body = chat_body_to_chat_upstream_body(body, chosen)
        else:
            req_body = deepcopy(body)
        req_body["model"] = chosen["actual_model"]
        if upstream_kind == "chat" and chat_request_format(chosen) == "anthropic":
            req_body = anthropic_chat_body_from_openai_chat_body(req_body, chosen)
        return req_body
    if client_kind == "responses" and upstream_kind == "chat":
        req_body = responses_body_to_chat_body(body, chosen)
        if chat_request_format(chosen) == "anthropic":
            req_body = anthropic_chat_body_from_openai_chat_body(req_body, chosen)
        return req_body
    if client_kind == "chat" and upstream_kind == "responses":
        if chosen.get("_codex_compat_adapter"):
            return normalize_responses_upstream_body(chat_body_to_codex_compat_responses_body(body, chosen), chosen)
        return normalize_responses_upstream_body(chat_body_to_responses_body(body, chosen), chosen)
    raise ValueError(f"unsupported format adapter: {upstream_kind} -> {client_kind}")


def upstream_request_headers(
    provider: dict[str, Any],
    incoming_headers: dict[str, str] | None,
    upstream_kind: str,
    chosen: dict[str, Any],
    request_id: str,
    stream: bool,
) -> dict[str, str]:
    extra_headers: dict[str, str] = {}
    if upstream_kind == "chat" and chat_request_format(chosen) == "anthropic":
        extra_headers.update(anthropic_chat_default_headers())
    profile = normalize_client_profile(chosen.get("client_profile") or chosen.get("probe_client_profile"))
    extra_headers.update(client_profile_headers(profile, request_id, stream))
    if chosen.get("_codex_compat_adapter"):
        extra_headers.update(codex_compat_adapter_headers(request_id, stream))
    return provider_headers(
        provider,
        incoming_headers,
        upstream_kind,
        extra_headers,
        extra_headers_override=client_profile_overrides_provider_headers(profile) or bool(chosen.get("_codex_compat_adapter")),
    )


def can_retry_with_codex_compat_adapter(
    client_kind: str,
    upstream_kind: str,
    status_code: int,
    text: str,
    chosen: dict[str, Any],
) -> bool:
    return (
        client_kind == "chat"
        and upstream_kind == "responses"
        and not chosen.get("_codex_compat_adapter")
        and classify_error(status_code, text) == "invalid_request"
    )


def enable_codex_compat_adapter(chosen: dict[str, Any]) -> None:
    chosen["_codex_compat_adapter"] = True
    chosen["_format_adapter"] = "codex_responses_to_chat"


def extract_chat_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = safe_text_from_content(content)
            return text or ""
    text = safe_text_from_content(first.get("text")) if isinstance(first, dict) else ""
    return text or ""


def extract_responses_output_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                        parts.append(str(part.get("text") or ""))
            elif isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def convert_chat_response_to_responses(
    data: Any,
    request_id: str,
    model: str | None,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = extract_chat_response_text(data)
    response_id = data.get("id") if isinstance(data, dict) and data.get("id") else request_id
    usage = normalize_usage_for_responses(data.get("usage")) if isinstance(data, dict) else None
    output: list[dict[str, Any]] = []
    tool_usage_parts: list[Any] = []
    if text:
        output.append(
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        )
    if isinstance(data, dict):
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) and isinstance(first.get("message"), dict) else {}
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            arguments = function.get("arguments")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
            tool_usage_parts.append({"name": name, "arguments": arguments})
            call_id = str(call.get("id") or f"call_{uuid.uuid4().hex[:16]}")
            output.append(
                {
                    "type": "function_call",
                    "id": call_id,
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments,
                }
            )
    if not output:
        output.append(
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "", "annotations": []}],
            }
        )
    response: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(now()),
        "status": "completed",
        "model": model or "",
        "output": output,
        "output_text": text,
    }
    if not usage and request_body is not None:
        usage = synthesize_responses_usage(request_body, {"text": text, "tool_calls": tool_usage_parts})
    if usage:
        response["usage"] = usage
    return response


def extract_responses_function_calls(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("output"), list):
        return []
    calls: list[dict[str, Any]] = []
    for item in data["output"]:
        if not isinstance(item, dict) or str(item.get("type") or "") != "function_call":
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:16]}")
        arguments = item.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":"))
        calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return calls


def chat_response_has_tool_call(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    for choice in data.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        if isinstance(message.get("tool_calls"), list) and message["tool_calls"]:
            return True
    return False


def response_data_has_tool_call(data: Any, kind: str) -> bool:
    if kind == "responses":
        return bool(extract_responses_function_calls(data))
    if kind == "chat":
        return chat_response_has_tool_call(data)
    return False


def convert_responses_response_to_chat(data: Any, request_id: str, model: str | None) -> dict[str, Any]:
    text = extract_responses_output_text(data)
    tool_calls = extract_responses_function_calls(data)
    usage = data.get("usage") if isinstance(data, dict) and isinstance(data.get("usage"), dict) else None
    message: dict[str, Any] = {"role": "assistant", "content": text}
    finish_reason = "stop"
    if tool_calls:
        message["tool_calls"] = tool_calls
        if not text:
            message["content"] = None
        finish_reason = "tool_calls"
    response: dict[str, Any] = {
        "id": data.get("id") if isinstance(data, dict) and data.get("id") else request_id,
        "object": "chat.completion",
        "created": int(now()),
        "model": model or "",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        response["usage"] = usage
    return response


def convert_upstream_response_for_client(
    data: Any,
    chosen: dict[str, Any],
    client_kind: str,
    request_id: str,
    model: str | None,
    request_body: dict[str, Any] | None = None,
) -> Any:
    upstream_kind = chosen.get("_upstream_kind") or client_kind
    if upstream_kind == client_kind:
        return data
    if client_kind == "responses" and upstream_kind == "chat":
        return convert_chat_response_to_responses(data, request_id, model, request_body)
    if client_kind == "chat" and upstream_kind == "responses":
        return convert_responses_response_to_chat(data, request_id, model)
    return data


def iter_sse_data_payloads(text: str) -> list[str]:
    payloads: list[str] = []
    for event in re.split(r"\r?\n\r?\n", text):
        lines = []
        for line in event.splitlines():
            if line.startswith("data:"):
                lines.append(line[5:].strip())
        if lines:
            payloads.append("\n".join(lines))
    return payloads


def pop_complete_sse_events(buffer: bytes) -> tuple[bytes, bytes]:
    events = bytearray()
    remaining = buffer
    while remaining:
        lf_index = remaining.find(b"\n\n")
        crlf_index = remaining.find(b"\r\n\r\n")
        candidates = [(idx, sep_len) for idx, sep_len in ((lf_index, 2), (crlf_index, 4)) if idx >= 0]
        if not candidates:
            break
        idx, sep_len = min(candidates, key=lambda item: item[0])
        end = idx + sep_len
        events.extend(remaining[:end])
        remaining = remaining[end:]
    return bytes(events), remaining


def raw_response_sse_event(event_type: str, data: dict[str, Any]) -> bytes:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


def chat_to_responses_usage(state: dict[str, Any]) -> dict[str, Any] | None:
    usage = normalize_usage_for_responses(state.get("responses_usage"))
    if usage:
        return usage
    output_value = {
        "text": "".join(state.get("response_output_parts") or []),
        "tool_arguments": "".join(state.get("response_tool_argument_parts") or []),
    }
    usage = synthesize_responses_usage(state.get("request_body"), output_value)
    if usage:
        state["responses_usage"] = usage
    return usage


def responses_message_output_item(text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def chat_to_responses_final_output(state: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    text = "".join(state.get("response_output_parts") or [])
    output: list[dict[str, Any]] = []
    if text:
        output.append(responses_message_output_item(text))
    tool_calls = state.get("response_tool_calls")
    if isinstance(tool_calls, dict):
        for call in tool_calls.values():
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or "").strip()
            if not name:
                continue
            call_id = str(call.get("call_id") or call.get("id") or f"call_{uuid.uuid4().hex[:16]}")
            output.append(
                {
                    "type": "function_call",
                    "id": call_id,
                    "call_id": call_id,
                    "name": name,
                    "arguments": "".join(call.get("arguments_parts") or []),
                }
            )
    if not output:
        output.append(responses_message_output_item(""))
    return output, text


def chat_to_responses_completed_event(request_id: str, model: str | None, state: dict[str, Any]) -> bytes:
    if state.get("response_completed_sent"):
        return b""
    state["response_completed_sent"] = True
    output, output_text = chat_to_responses_final_output(state)
    return response_completed_event(request_id, model, chat_to_responses_usage(state), output, output_text)


def chat_stream_tool_call_state(state: dict[str, Any], index: int, call_id: str, name: str) -> dict[str, Any]:
    tool_calls = state.setdefault("response_tool_calls", {})
    key = f"tool_index_{index}"
    record = tool_calls.setdefault(key, {"id": call_id, "call_id": call_id, "name": "", "arguments_parts": []})
    if call_id:
        record["id"] = call_id
        record["call_id"] = call_id
    if name:
        record["name"] = name
    return record


def chat_stream_chunk_to_responses(
    chunk: bytes,
    request_id: str,
    model: str | None,
    state: dict[str, Any] | None = None,
) -> bytes:
    state = state if state is not None else {}
    out = bytearray()
    for payload in iter_sse_data_payloads(chunk.decode("utf-8", "ignore")):
        if payload == "[DONE]":
            out.extend(chat_to_responses_completed_event(request_id, model, state))
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        usage = normalize_usage_for_responses(data.get("usage"))
        if usage:
            state["responses_usage"] = usage
        for choice in data.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta_obj = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            delta = delta_obj.get("content")
            if delta:
                state.setdefault("response_output_parts", []).append(str(delta))
                event_data = {"type": "response.output_text.delta", "delta": delta}
                out.extend(raw_response_sse_event("response.output_text.delta", event_data))
            for call in delta_obj.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                index = int(call.get("index") or 0)
                key = f"tool_index_{index}"
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                if call.get("id"):
                    state[f"chat_tool_call_id_{index}"] = str(call.get("id"))
                call_id = str(state.setdefault(f"chat_tool_call_id_{index}", f"call_{uuid.uuid4().hex[:16]}"))
                name = str(function.get("name") or "")
                arguments = str(function.get("arguments") or "")
                tool_state = chat_stream_tool_call_state(state, index, call_id, name)
                added = state.setdefault("chat_tool_call_added", set())
                if key not in added and (call.get("id") or name):
                    added.add(key)
                    item = {"type": "function_call", "id": call_id, "call_id": call_id, "name": name, "arguments": ""}
                    out.extend(
                        raw_response_sse_event(
                            "response.output_item.added",
                            {"type": "response.output_item.added", "output_index": index, "item": item},
                        )
                    )
                if arguments:
                    tool_state.setdefault("arguments_parts", []).append(arguments)
                    state.setdefault("response_tool_argument_parts", []).append(arguments)
                    out.extend(
                        raw_response_sse_event(
                            "response.function_call_arguments.delta",
                            {"type": "response.function_call_arguments.delta", "call_id": call_id, "output_index": index, "delta": arguments},
                        )
                    )
            if choice.get("finish_reason") == "tool_calls":
                tool_calls = state.get("response_tool_calls") if isinstance(state.get("response_tool_calls"), dict) else {}
                for key, call in tool_calls.items():
                    if not isinstance(call, dict):
                        continue
                    index = int(str(key).rsplit("_", 1)[-1])
                    call_id = str(call.get("call_id") or call.get("id") or f"call_{uuid.uuid4().hex[:16]}")
                    out.extend(
                        raw_response_sse_event(
                            "response.output_item.done",
                            {
                                "type": "response.output_item.done",
                                "output_index": index,
                                "item": {
                                    "type": "function_call",
                                    "id": call_id,
                                    "call_id": call_id,
                                    "name": str(call.get("name") or ""),
                                    "arguments": "".join(call.get("arguments_parts") or []),
                                },
                            },
                        )
                    )
    return bytes(out)


def chat_completion_stream_chunk(
    request_id: str,
    model: str | None,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> bytes:
    chunk: dict[str, Any] = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(now()),
        "model": model or "",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage:
        chunk["usage"] = usage
    return f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


def response_stream_tool_call_key(data: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    item = item or {}
    for value in (
        data.get("item_id"),
        data.get("call_id"),
        item.get("id"),
        item.get("call_id"),
    ):
        if value:
            return str(value)
    output_index = data.get("output_index")
    if output_index is not None:
        return f"output:{output_index}"
    return f"tool:{uuid.uuid4().hex[:16]}"


def response_stream_tool_call_index(state: dict[str, Any], key: str) -> int:
    indexes = state.setdefault("tool_call_indexes", {})
    if key not in indexes:
        indexes[key] = len(indexes)
    return int(indexes[key])


def response_stream_usage(data: dict[str, Any]) -> dict[str, Any] | None:
    usage = data.get("usage")
    if isinstance(usage, dict):
        return usage
    response = data.get("response")
    if isinstance(response, dict) and isinstance(response.get("usage"), dict):
        return response["usage"]
    return None


def responses_stream_chunk_to_chat(
    chunk: bytes,
    request_id: str,
    model: str | None,
    state: dict[str, Any] | None = None,
) -> bytes:
    state = state if state is not None else {}
    out = bytearray()
    for payload in iter_sse_data_payloads(chunk.decode("utf-8", "ignore")):
        if payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        event_type = str(data.get("type") or "")
        delta = None
        if event_type in {"response.output_text.delta", "response.output_text.annotation.added"}:
            delta = data.get("delta")
            if not delta:
                delta = data.get("text") or data.get("content")
        elif not event_type and data.get("delta"):
            delta = data.get("delta")
        if delta:
            out.extend(chat_completion_stream_chunk(request_id, model, {"content": delta}))
            continue
        if event_type in {"response.output_item.added", "response.output_item.done"}:
            item = data.get("item") if isinstance(data.get("item"), dict) else {}
            if str(item.get("type") or "") != "function_call":
                continue
            key = response_stream_tool_call_key(data, item)
            index = response_stream_tool_call_index(state, key)
            added_seen = state.setdefault("tool_call_added_seen", set())
            delta_seen = state.setdefault("tool_call_argument_delta_seen", set())
            call_id = str(item.get("call_id") or item.get("id") or key)
            name = str(item.get("name") or "").strip()
            arguments = item.get("arguments")
            if not isinstance(arguments, str):
                arguments = ""
            if event_type == "response.output_item.added":
                added_seen.add(key)
            elif key in delta_seen and key in added_seen:
                continue
            elif key in added_seen and not arguments:
                continue
            tool_call: dict[str, Any] = {
                "index": index,
                "type": "function",
                "function": {},
            }
            if call_id:
                tool_call["id"] = call_id
            if name:
                tool_call["function"]["name"] = name
            if arguments:
                tool_call["function"]["arguments"] = arguments
            state["tool_calls_seen"] = True
            out.extend(chat_completion_stream_chunk(request_id, model, {"tool_calls": [tool_call]}))
            continue
        if event_type in {"response.function_call_arguments.delta", "response.function_call_arguments.done"}:
            key = response_stream_tool_call_key(data)
            index = response_stream_tool_call_index(state, key)
            delta_seen = state.setdefault("tool_call_argument_delta_seen", set())
            if event_type == "response.function_call_arguments.done" and key in delta_seen:
                continue
            argument_value = data.get("delta") if event_type.endswith(".delta") else data.get("arguments")
            argument_delta = str(argument_value or "")
            if not argument_delta:
                continue
            if event_type.endswith(".delta"):
                delta_seen.add(key)
            state["tool_calls_seen"] = True
            out.extend(
                chat_completion_stream_chunk(
                    request_id,
                    model,
                    {"tool_calls": [{"index": index, "function": {"arguments": argument_delta}}]},
                )
            )
            continue
        if event_type in {"response.completed", "response.failed", "response.incomplete"}:
            finish_reason = "tool_calls" if state.get("tool_calls_seen") else "stop"
            out.extend(chat_completion_stream_chunk(request_id, model, {}, finish_reason, response_stream_usage(data)))
            continue
    return bytes(out)


class StreamFormatAdapter:
    def __init__(
        self,
        chosen: dict[str, Any],
        client_kind: str,
        request_id: str,
        model: str | None,
        request_body: dict[str, Any] | None = None,
    ):
        self.chosen = chosen
        self.client_kind = client_kind
        self.request_id = request_id
        self.model = model
        self.buffer = b""
        self.observe_buffer = b""
        self.state: dict[str, Any] = {"request_body": request_body}

    def feed(self, chunk: bytes) -> bytes:
        upstream_kind = self.chosen.get("_upstream_kind") or self.client_kind
        if upstream_kind == self.client_kind:
            self.observe_native_chunk(chunk)
            return chunk
        self.buffer += chunk
        complete, self.buffer = pop_complete_sse_events(self.buffer)
        if not complete:
            return b""
        return convert_stream_chunk_for_client(complete, self.chosen, self.client_kind, self.request_id, self.model, self.state)

    def flush(self) -> bytes:
        upstream_kind = self.chosen.get("_upstream_kind") or self.client_kind
        if upstream_kind == self.client_kind:
            if self.observe_buffer.strip():
                pending = self.observe_buffer
                self.observe_buffer = b""
                if not pending.endswith((b"\n\n", b"\r\n\r\n")):
                    pending += b"\n\n"
                self.observe_native_events(pending)
            return b""
        if not self.buffer.strip():
            self.buffer = b""
            return b""
        pending = self.buffer
        self.buffer = b""
        if not pending.endswith((b"\n\n", b"\r\n\r\n")):
            pending += b"\n\n"
        return convert_stream_chunk_for_client(pending, self.chosen, self.client_kind, self.request_id, self.model, self.state)

    def completion_event(self) -> bytes:
        upstream_kind = self.chosen.get("_upstream_kind") or self.client_kind
        if self.client_kind == "responses" and upstream_kind == "chat":
            return chat_to_responses_completed_event(self.request_id, self.model, self.state)
        return response_completed_event(self.request_id, self.model)

    def observe_native_chunk(self, chunk: bytes) -> None:
        if self.client_kind != "responses":
            return
        self.observe_buffer += chunk
        complete, self.observe_buffer = pop_complete_sse_events(self.observe_buffer)
        if complete:
            self.observe_native_events(complete)

    def observe_native_events(self, chunk: bytes) -> None:
        for payload in iter_sse_data_payloads(chunk.decode("utf-8", "ignore")):
            if payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except Exception:
                continue
            event_type = str(data.get("type") or "")
            item = data.get("item") if isinstance(data.get("item"), dict) else {}
            if event_type.startswith("response.function_call") or str(item.get("type") or "") == "function_call":
                self.state["native_tool_calls_seen"] = True
            delta = None
            if event_type in {"response.output_text.delta", "response.output_text.annotation.added"}:
                delta = data.get("delta") or data.get("text") or data.get("content")
            elif event_type == "response.output_item.done":
                content = item.get("content") if isinstance(item, dict) else None
                for fragment in iter_text_fragments(content):
                    self.state.setdefault("native_response_text_parts", []).append(fragment)
            if delta:
                self.state.setdefault("native_response_text_parts", []).append(str(delta))

    def tool_call_observed(self) -> bool:
        if self.state.get("native_tool_calls_seen"):
            return True
        tool_calls = self.state.get("response_tool_calls")
        return isinstance(tool_calls, dict) and bool(tool_calls)

    def tool_loop_detected(self) -> bool:
        text = " ".join(self.state.get("native_response_text_parts") or [])
        return tool_loop_text_detected(text)


def convert_stream_chunk_for_client(
    chunk: bytes,
    chosen: dict[str, Any],
    client_kind: str,
    request_id: str,
    model: str | None,
    state: dict[str, Any] | None = None,
) -> bytes:
    upstream_kind = chosen.get("_upstream_kind") or client_kind
    if upstream_kind == client_kind:
        return chunk
    if client_kind == "responses" and upstream_kind == "chat":
        return chat_stream_chunk_to_responses(chunk, request_id, model, state)
    if client_kind == "chat" and upstream_kind == "responses":
        return responses_stream_chunk_to_chat(chunk, request_id, model, state)
    return chunk


def model_fetch_client_profiles(provider: dict[str, Any]) -> list[str]:
    configured = [normalize_client_profile(item) for item in (provider.get("model_fetch_client_profiles") or []) if str(item).strip()]
    profiles = [*configured, "default", "codex", "claude-cli", "claude-code"]
    return list(dict.fromkeys(profiles))


async def fetch_models(provider: dict[str, Any]) -> list[str]:
    last_error: Exception | None = None
    empty_success = False
    async with httpx.AsyncClient(timeout=httpx.Timeout(PROBE_TIMEOUT_SECONDS), follow_redirects=True) as client:
        for url in upstream_urls(provider, "/models"):
            for profile in model_fetch_client_profiles(provider):
                try:
                    extra_headers = client_profile_headers(profile, stream=False)
                    response = await client.get(
                        url,
                        headers=provider_headers(
                            provider,
                            kind=None,
                            extra_headers=extra_headers,
                            extra_headers_override=client_profile_overrides_provider_headers(profile),
                        ),
                    )
                    if response.status_code >= 400:
                        raise RuntimeError(f"models_http_{response.status_code}:{response.text[:200]}")
                    models = extract_models_from_response(response.json())
                    if models:
                        MODEL_CACHE.setdefault(provider["id"], {})["client_profile"] = profile
                        return models
                    empty_success = True
                except Exception as exc:
                    last_error = exc
                    continue
    if empty_success:
        return []
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


def add_probe_attempt(attempts: list[dict[str, Any]], attempt: dict[str, Any]) -> None:
    attempt["client_profile"] = normalize_client_profile(attempt.get("client_profile"))
    key = (
        str(attempt.get("path") or ""),
        str(attempt.get("request_format") or ""),
        str(attempt.get("body_format") or ""),
        str(attempt.get("client_profile") or ""),
    )
    existing = {
        (
            str(item.get("path") or ""),
            str(item.get("request_format") or ""),
            str(item.get("body_format") or ""),
            str(item.get("client_profile") or ""),
        )
        for item in attempts
    }
    if key not in existing:
        attempts.append(attempt)


def probe_attempts_for_kind(provider: dict[str, Any], kind: str, probe_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    path = probe_cfg.get("path") or f"/{kind}"
    attempts: list[dict[str, Any]] = []
    configured_chat_format = chat_request_format(provider)
    configured_profiles = [normalize_client_profile(item) for item in (provider.get("probe_client_profiles") or []) if str(item).strip()]
    if kind == "chat":
        if configured_chat_format == "anthropic":
            add_probe_attempt(
                attempts,
                {
                    "name": "chat/anthropic/configured",
                    "path": path,
                    "request_format": "anthropic-chat",
                    "body_format": "anthropic-chat",
                    "client_profile": "default",
                },
            )
        else:
            add_probe_attempt(
                attempts,
                {
                    "name": "chat/openai/default",
                    "path": path,
                    "request_format": "openai-compatible",
                    "body_format": "openai-chat",
                    "client_profile": "default",
                },
            )
        for profile in configured_profiles:
            add_probe_attempt(
                attempts,
                {
                    "name": f"chat/{configured_chat_format}/{profile}",
                    "path": path,
                    "request_format": "anthropic-chat" if configured_chat_format == "anthropic" else "openai-compatible",
                    "body_format": "anthropic-chat" if configured_chat_format == "anthropic" else "openai-chat",
                    "client_profile": profile,
                },
            )
        add_probe_attempt(
            attempts,
            {
                "name": "chat/openai/default",
                "path": path,
                "request_format": "openai-compatible",
                "body_format": "openai-chat",
                "client_profile": "default",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "chat/openai/codex",
                "path": path,
                "request_format": "openai-compatible",
                "body_format": "openai-chat",
                "client_profile": "codex",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "chat/anthropic/default",
                "path": path,
                "request_format": "anthropic-chat",
                "body_format": "anthropic-chat",
                "client_profile": "anthropic",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "chat/anthropic/claude-cli",
                "path": path,
                "request_format": "anthropic-chat",
                "body_format": "anthropic-chat",
                "client_profile": "claude-cli",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "chat/anthropic/claude-code",
                "path": path,
                "request_format": "anthropic-chat",
                "body_format": "anthropic-chat",
                "client_profile": "claude-code",
            },
        )
        return attempts
    if kind == "responses":
        for profile in configured_profiles:
            add_probe_attempt(
                attempts,
                {
                    "name": f"responses/openai/{profile}",
                    "path": path,
                    "request_format": "openai-responses",
                    "body_format": "openai-responses",
                    "client_profile": profile,
                },
            )
        add_probe_attempt(
            attempts,
            {
                "name": "responses/openai/default",
                "path": path,
                "request_format": "openai-responses",
                "body_format": "openai-responses",
                "client_profile": "default",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "responses/openai/codex",
                "path": path,
                "request_format": "openai-responses",
                "body_format": "openai-responses",
                "client_profile": "codex",
            },
        )
        add_probe_attempt(
            attempts,
            {
                "name": "responses/codex/diagnostic",
                "path": path,
                "request_format": "codex-responses",
                "body_format": "codex-responses",
                "client_profile": "codex",
            },
        )
    return attempts


def probe_body_for_attempt(
    kind: str,
    probe_cfg: dict[str, Any],
    provider: dict[str, Any],
    actual_model: str,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    body_format = str(attempt.get("body_format") or "")
    if kind == "responses" and body_format == "codex-responses":
        return apply_responses_provider_defaults(codex_shape_diagnostic_body(actual_model), provider)
    body = deepcopy(probe_cfg.get("body") or {})
    body["model"] = actual_model
    if kind == "responses":
        return apply_responses_provider_defaults(body, provider)
    if kind == "chat" and body_format == "anthropic-chat":
        return anthropic_chat_body_from_openai_chat_body(body, {"actual_model": actual_model})
    if kind == "chat":
        return chat_body_to_chat_upstream_body(body, {"actual_model": actual_model})
    return body


def probe_headers_for_attempt(provider: dict[str, Any], kind: str, attempt: dict[str, Any], stream: bool = False) -> dict[str, str]:
    extra_headers: dict[str, str] = {}
    body_format = str(attempt.get("body_format") or "")
    profile = normalize_client_profile(attempt.get("client_profile"))
    if kind == "chat" and body_format == "anthropic-chat":
        extra_headers.update(anthropic_chat_default_headers())
    extra_headers.update(client_profile_headers(profile, stream=stream))
    return provider_headers(
        provider,
        kind=kind,
        extra_headers=extra_headers,
        extra_headers_override=client_profile_overrides_provider_headers(profile),
    )


def apply_probe_attempt_metadata(result: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    result["request_format"] = attempt.get("request_format")
    result["client_profile"] = normalize_client_profile(attempt.get("client_profile"))
    result["probe_attempt"] = attempt.get("name")
    result["probe_path"] = attempt.get("path")
    result["probe_strategy_version"] = PROBE_STRATEGY_VERSION
    if result.get("request_format") == "codex-responses" and result.get("healthy"):
        result["responses_compat_mode"] = "codex"
    return result


def probe_attempt_record(attempt: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "name": attempt.get("name"),
        "request_format": attempt.get("request_format"),
        "client_profile": normalize_client_profile(attempt.get("client_profile")),
        "endpoint_url": result.get("endpoint_url"),
        "healthy": bool(result.get("healthy")),
        "reason": result.get("reason"),
        "status_code": result.get("status_code"),
        "latency_ms": result.get("latency_ms"),
    }
    sample = result.get("sample")
    if sample:
        record["sample"] = redact_text(sample, 300)
    return record


def response_probe_failure_result(
    kind: str,
    reason: str,
    status_code: int | None,
    latency_ms: int,
    sample: str,
    endpoint_url: str,
) -> dict[str, Any]:
    shape_status = ""
    shape_invalid_required = None
    if kind == "responses" and reason == "invalid_request":
        reason = "responses_request_shape_unverified"
        shape_status = "probe_unverified"
        shape_invalid_required = RESPONSES_INVALID_REQUEST_CONFIRMATIONS
    return {
        "healthy": False,
        "reason": reason,
        "shape_status": shape_status,
        "shape_invalid_required": shape_invalid_required,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "sample": sample[:300],
        "endpoint_url": endpoint_url,
    }


async def probe_standard_http_attempt(
    client: httpx.AsyncClient,
    provider: dict[str, Any],
    actual_model: str,
    kind: str,
    probe_cfg: dict[str, Any],
    attempt: dict[str, Any],
    url: str,
) -> dict[str, Any]:
    attempt_start = now()
    try:
        body = probe_body_for_attempt(kind, probe_cfg, provider, actual_model, attempt)
    except Exception as exc:
        return {
            "healthy": False,
            "reason": f"request_build:{type(exc).__name__}",
            "latency_ms": int((now() - attempt_start) * 1000),
            "sample": str(exc)[:300],
            "endpoint_url": url,
        }
    partial_retry_used = False
    while True:
        response = await client.post(url, headers=probe_headers_for_attempt(provider, kind, attempt, bool(body.get("stream", False))), json=body)
        text = response.text[:2000]
        if not partial_retry_used and can_retry_with_partial(kind, response.status_code, text[:1000], body):
            partial_retry_used = True
            learn_responses_partial_default(provider)
            body = apply_responses_provider_defaults(body, provider)
            continue
        break
    latency_ms = int((now() - attempt_start) * 1000)
    if response.status_code < 200 or response.status_code >= 300:
        return response_probe_failure_result(kind, classify_error(response.status_code, text), response.status_code, latency_ms, text, url)
    try:
        data = response.json()
    except Exception:
        return {
            "healthy": False,
            "reason": "invalid_json_response",
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "sample": text[:300],
            "endpoint_url": url,
        }
    if response_has_error_json(data):
        sample = json.dumps(data, ensure_ascii=False)[:1000]
        return response_probe_failure_result(kind, classify_error(response.status_code, sample), response.status_code, latency_ms, sample, url)
    quality = probe_content_quality_result(data, kind)
    if not quality.get("healthy"):
        return {
            "healthy": False,
            "reason": quality.get("reason"),
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "sample": quality.get("sample", ""),
            "endpoint_url": url,
            "quality_checked": quality.get("quality_checked"),
            "quality_score": quality.get("quality_score"),
        }
    return {
        "healthy": True,
        "reason": "ok",
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "endpoint_url": url,
        "sample": quality.get("sample", ""),
        "quality_checked": quality.get("quality_checked"),
        "quality_score": quality.get("quality_score"),
    }


async def probe_codex_responses_shape(
    client: httpx.AsyncClient,
    provider: dict[str, Any],
    actual_model: str,
    url: str,
    start: float,
) -> dict[str, Any]:
    headers = provider_headers(
        provider,
        kind="responses",
        extra_headers=codex_shape_diagnostic_headers(),
        extra_headers_override=True,
    )
    headers["Accept"] = "text/event-stream"
    body = apply_responses_provider_defaults(codex_shape_diagnostic_body(actual_model), provider)
    response = None
    first = b""
    for _ in range(2):
        async with client.stream("POST", url, headers=headers, json=body) as response:
            latency_ms = int((now() - start) * 1000)
            if response.status_code < 200 or response.status_code >= 300:
                raw = await response.aread()
                text = raw.decode("utf-8", "ignore")[:2000]
                if can_retry_with_partial("responses", response.status_code, text, body):
                    learn_responses_partial_default(provider)
                    body = apply_responses_provider_defaults(body, provider)
                    continue
                reason = classify_error(response.status_code, text)
                if reason == "invalid_request":
                    reason = "responses_request_shape_unverified"
                return {
                    "healthy": False,
                    "reason": reason,
                    "shape_status": "probe_unverified" if reason == "responses_request_shape_unverified" else "",
                    "shape_invalid_required": RESPONSES_INVALID_REQUEST_CONFIRMATIONS if reason == "responses_request_shape_unverified" else None,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "sample": text[:300],
                    "endpoint_url": url,
                }
            first = b""
            async for chunk in response.aiter_raw():
                if chunk:
                    first = chunk
                    break
            text = first.decode("utf-8", "ignore")[:2000] if first else ""
            break
    if not text:
        return {
            "healthy": False,
            "reason": "empty_stream",
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "sample": "",
            "endpoint_url": url,
        }
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if response_has_error_json(data) or event_stream_probe_has_error(text):
        sample = json.dumps(data, ensure_ascii=False)[:1000] if data is not None else text
        reason = classify_error(response.status_code, sample)
        if reason == "invalid_request":
            reason = "responses_request_shape_unverified"
        return {
            "healthy": False,
            "reason": reason,
            "shape_status": "probe_unverified" if reason == "responses_request_shape_unverified" else "",
            "shape_invalid_required": RESPONSES_INVALID_REQUEST_CONFIRMATIONS if reason == "responses_request_shape_unverified" else None,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "sample": sample[:300],
            "endpoint_url": url,
        }
    is_event_stream = "event:" in text or "data:" in text
    if not is_event_stream:
        if data is None:
            return {
                "healthy": False,
                "reason": "invalid_json_response",
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "sample": text[:300],
                "endpoint_url": url,
            }
        quality = probe_content_quality_result(data, "responses")
        if not quality.get("healthy"):
            return {
                "healthy": False,
                "reason": quality.get("reason"),
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "sample": quality.get("sample", ""),
                "endpoint_url": url,
                "quality_checked": quality.get("quality_checked"),
                "quality_score": quality.get("quality_score"),
            }
    return {
        "healthy": True,
        "reason": "ok",
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "endpoint_url": url,
        "shape_status": "codex_shape_verified",
        "shape_verification_source": "diagnostic_codex_shape",
    }


async def probe_one(provider: dict[str, Any], local_model: str, actual_model: str, kind: str) -> dict[str, Any]:
    probe_cfg = (CONFIG.get("probe") or {}).get(kind) or {}
    if not probe_cfg.get("enabled", True):
        return {"healthy": False, "reason": "probe_disabled"}
    if kind == "responses" and not ENABLE_RESPONSES_PROBE:
        return {"healthy": False, "reason": "responses_probe_disabled"}

    start = now()
    attempts = probe_attempts_for_kind(provider, kind, probe_cfg)
    attempt_records: list[dict[str, Any]] = []
    last_result: dict[str, Any] | None = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(PROBE_TIMEOUT_SECONDS), follow_redirects=True) as client:
            for attempt in attempts:
                urls = upstream_urls(provider, attempt.get("path") or probe_cfg.get("path") or f"/{kind}")
                if not urls:
                    result = apply_probe_attempt_metadata(
                        {
                            "healthy": False,
                            "reason": "no_endpoint",
                            "latency_ms": int((now() - start) * 1000),
                        },
                        attempt,
                    )
                    attempt_records.append(probe_attempt_record(attempt, result))
                    last_result = result
                    continue
                for url in urls:
                    attempt_start = now()
                    if kind == "responses" and attempt.get("body_format") == "codex-responses":
                        result = await probe_codex_responses_shape(client, provider, actual_model, url, attempt_start)
                    else:
                        result = await probe_standard_http_attempt(client, provider, actual_model, kind, probe_cfg, attempt, url)
                    result = apply_probe_attempt_metadata(result, attempt)
                    attempt_records.append(probe_attempt_record(attempt, result))
                    if result.get("healthy"):
                        result["latency_ms"] = int((now() - start) * 1000)
                        result["probe_attempts"] = attempt_records
                        result["probe_attempt_count"] = len(attempt_records)
                        return result
                    last_result = result
            if last_result:
                last_result["latency_ms"] = int((now() - start) * 1000)
                last_result["probe_attempts"] = attempt_records
                last_result["probe_attempt_count"] = len(attempt_records)
                return last_result
            return {
                "healthy": False,
                "reason": "no_probe_attempts",
                "latency_ms": int((now() - start) * 1000),
                "probe_attempts": attempt_records,
                "probe_attempt_count": len(attempt_records),
                "probe_strategy_version": PROBE_STRATEGY_VERSION,
            }
    except Exception as exc:
        return {
            "healthy": False,
            "reason": f"exception:{type(exc).__name__}",
            "latency_ms": int((now() - start) * 1000),
            "sample": str(exc)[:300],
            "probe_attempts": attempt_records,
            "probe_attempt_count": len(attempt_records),
            "probe_strategy_version": PROBE_STRATEGY_VERSION,
        }


def probe_candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    previous = candidate.get("previous")
    reason = str((previous or {}).get("reason") or "")
    if reason.startswith("runtime_failure:"):
        state_rank = 0
    elif previous is None or not previous.get("checked_at"):
        state_rank = 1
    elif candidate.get("due"):
        state_rank = 2
    else:
        state_rank = 3
    return (
        state_rank,
        0 if candidate.get("due") else 1,
        -int(candidate["item"].get("priority", 0)),
        -int(candidate["item"].get("weight", 0)),
        candidate["item"].get("provider_name") or "",
        candidate["local_model"],
        candidate["kind"],
    )


async def resolve_probe_candidate(candidate: dict[str, Any], run_probe: bool, semaphore: asyncio.Semaphore) -> tuple[str, str, str, dict[str, Any]]:
    provider = candidate["provider"]
    item = candidate["item"]
    kind = candidate["kind"]
    local_model = candidate["local_model"]
    actual_model = candidate["actual_model"]
    matrix_key = candidate["matrix_key"]
    previous = candidate["previous"]
    due = candidate["due"]
    if run_probe:
        async with semaphore:
            result = await probe_one(provider, local_model, actual_model, kind)
        item.update(
            {
                "healthy": bool(result.get("healthy")),
                "reason": result.get("reason"),
                "status_code": result.get("status_code"),
                "latency_ms": result.get("latency_ms"),
                "checked_at": int(now()),
                "next_probe_at": int(now()) + probe_cooldown_seconds(result.get("reason"), bool(result.get("healthy"))),
                "sample": result.get("sample", ""),
                "quality_checked": result.get("quality_checked"),
                "quality_score": result.get("quality_score"),
                "request_format": result.get("request_format") or item.get("request_format"),
                "client_profile": result.get("client_profile") or item.get("client_profile") or "default",
                "probe_attempt": result.get("probe_attempt") or "",
                "probe_attempts": result.get("probe_attempts") or [],
                "probe_attempt_count": result.get("probe_attempt_count") or 0,
                "probe_strategy_version": result.get("probe_strategy_version") or PROBE_STRATEGY_VERSION,
                "probe_path": result.get("probe_path") or item.get("probe_path"),
                "shape_status": result.get("shape_status") or "",
                "shape_invalid_required": result.get("shape_invalid_required"),
                "shape_verification_source": result.get("shape_verification_source") or "",
                "responses_compat_mode": result.get("responses_compat_mode") or "",
                "skipped": False,
                "skip_reason": "",
            }
        )
        if result.get("healthy") and runtime_failure_cooling_down(previous):
            item = preserve_probe_state(item, previous)
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
    return kind, local_model, matrix_key, item


async def probe_all(force: bool = False) -> None:
    async with PROBE_RUN_LOCK:
        await probe_all_once(force)


async def probe_all_once(force: bool = False) -> None:
    global LAST_PROBE_AT
    await reload_config()
    old_health = deepcopy(HEALTH)
    new_health: dict[str, dict[str, dict[str, Any]]] = {"chat": {}, "responses": {}}
    probe_limit = 0 if force else max(1, PROBE_MAX_PER_CYCLE)
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
                    "request_format": request_format_label(provider, kind),
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

    candidates.sort(key=probe_candidate_sort_key)
    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)
    probes_scheduled = 0
    tasks = []
    for candidate in candidates:
        run_probe = False
        if candidate["due"] and (force or probes_scheduled < probe_limit):
            run_probe = True
            probes_scheduled += 1
        tasks.append(resolve_probe_candidate(candidate, run_probe, semaphore))

    for kind, local_model, matrix_key, item in await asyncio.gather(*tasks):
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
            "health": health_with_freshness(),
            "health_policy": health_policy_summary(),
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
                    "fallback_only": bool(provider.get("fallback_only", False)),
                }
                for provider in PROVIDERS
            ],
            "health": health_with_freshness(),
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
        for model in sorted(all_models, key=model_sort_rank):
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
    if not allow_paid and (item.get("route_group") == "paid_fallback" or item.get("fallback_only")):
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
        adjusted_latency = max(
            1,
            int(item.get("latency_ms") or 1000) + int(item.get("_adapter_latency_penalty_ms") or 0),
        )
        item["_adjusted_latency_ms"] = adjusted_latency
        item["_score"] = max(1, int(item.get("weight") or 1)) * (1000 / adjusted_latency)
    items.sort(
        key=lambda item: (
            -int(item.get("priority", 0)),
            -item.get("_score", 0),
            item.get("_adjusted_latency_ms") or 999999,
            int(item.get("_adapter_latency_penalty_ms") or 0),
        )
    )
    return items


def route_bucket_name(item: dict[str, Any]) -> str:
    if item.get("route_group") == "paid_fallback" or item.get("fallback_only"):
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
    if responses_real_shape_invalid_reason(reason) and float(item.get("next_probe_at") or 0) > now():
        return False
    if responses_request_shape_reason(reason) and item.get("kind") == "responses":
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
    if responses_request_shape_reason(reason) and item.get("kind") == "responses":
        return True
    return not item.get("checked_at")


def should_mark_runtime_failure(reason: str, kind: str | None = None) -> bool:
    if kind == "responses" and responses_request_shape_reason(reason):
        return False
    return reason not in {"invalid_request", "client_invalid_input"}


def should_verify_responses_request_shape(kind: str, endpoint_reasons: list[str]) -> bool:
    return bool(endpoint_reasons) and kind == "responses" and all(reason == "invalid_request" for reason in endpoint_reasons)


def should_mark_provider_all_endpoints_failed(kind: str, endpoint_reasons: list[str]) -> bool:
    return runtime_failure_reason_for_endpoint_failures(kind, endpoint_reasons) is not None


def runtime_failure_reason_for_endpoint_failures(kind: str, endpoint_reasons: list[str]) -> str | None:
    if not endpoint_reasons:
        return "all_endpoints_failed"
    if should_verify_responses_request_shape(kind, endpoint_reasons):
        return None
    markable = [reason for reason in endpoint_reasons if should_mark_runtime_failure(reason, kind)]
    if not markable:
        return None
    unique = set(markable)
    if len(unique) == 1:
        return markable[0]
    if unique <= {"model_unsupported", "not_found"}:
        return "model_unsupported"
    if unique <= {"quota"}:
        return "quota"
    if unique <= {"auth_or_forbidden"}:
        return "auth_or_forbidden"
    if unique <= {"provider_config_error"}:
        return "provider_config_error"
    if unique <= {"rate_limited"}:
        return "rate_limited"
    if unique <= {"server_unavailable", "empty_stream", "exception"}:
        return "server_unavailable"
    return "all_endpoints_failed"


def transient_runtime_failure_reason(reason: str) -> bool:
    return reason in {"server_unavailable", "empty_stream", "all_endpoints_failed"} or reason.startswith("exception:")


def exploration_enabled(controls: dict[str, Any]) -> bool:
    if ROUTE_EXPLORATION_MAX_CANDIDATES <= 0 or ROUTE_EXPLORATION_RATE <= 0:
        return False
    if controls.get("provider_id") or controls.get("route_group"):
        return False
    return random.random() < ROUTE_EXPLORATION_RATE


def exploration_candidate_allowed(item: dict[str, Any]) -> bool:
    if item.get("fallback_only") or item.get("route_group") == "paid_fallback":
        return False
    return item.get("route_group", "primary") in {"opportunistic", "primary", "backup"}


def retryable_probe_candidate_allowed(item: dict[str, Any], kind: str, controls: dict[str, Any]) -> bool:
    if item.get("healthy"):
        return False
    if kind != "responses":
        return False
    reason = str(item.get("reason") or "")
    if not responses_request_shape_reason(reason):
        return False
    if item.get("fallback_only") or item.get("route_group") == "paid_fallback":
        return False
    return provider_matches_controls(item, controls) and shadow_candidate_allowed(item, controls)


def healthy_candidate_buckets(model: str, kind: str, controls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    controls = controls or {}
    all_items = [deepcopy(item) for item in (HEALTH.get(kind, {}).get(model) or {}).values()]
    all_items = [item for item in all_items if provider_matches_controls(item, controls)]
    healthy = [item for item in all_items if item.get("healthy")]
    primary = sorted_route_bucket(
        [
            item
            for item in healthy
            if item.get("route_group", "primary") == "primary" and not item.get("fallback_only")
        ]
    )
    backup = sorted_route_bucket(
        [item for item in healthy if item.get("route_group") == "backup" and not item.get("fallback_only")]
    )
    paid = sorted_route_bucket(
        [
            item
            for item in healthy
            if item.get("route_group") == "paid_fallback" or item.get("fallback_only")
        ]
    )
    other = sorted_route_bucket(
        [
            item
            for item in healthy
            if item.get("route_group", "primary") not in {"primary", "backup", "paid_fallback"}
            and not item.get("fallback_only")
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
        {"name": "primary", "items": primary},
        {"name": "backup", "items": backup},
        {"name": "other", "items": other},
        {"name": "probe_retry", "items": retryable_probe},
        {"name": "explore", "items": explore},
        {"name": "shadow", "items": shadow},
        {"name": "paid_fallback", "items": paid},
    ]
    return [bucket for bucket in buckets if bucket["items"]]


ROUTE_BUCKET_ORDER = ["primary", "backup", "other", "probe_retry", "explore", "shadow", "paid_fallback"]


def annotate_route_item(item: dict[str, Any], client_kind: str, upstream_kind: str) -> dict[str, Any]:
    item["_client_kind"] = client_kind
    item["_upstream_kind"] = upstream_kind
    item["_format_adapter"] = adapter_name(client_kind, upstream_kind)
    if codex_compat_adapter_candidate(item, client_kind, upstream_kind):
        item["_format_adapter"] = "codex_responses_to_chat"
        item["_codex_compat_adapter"] = True
    if client_kind != upstream_kind:
        item["_adapter_latency_penalty_ms"] = ADAPTER_LATENCY_PENALTY_MS
    else:
        item["_adapter_latency_penalty_ms"] = 0
    return item


def codex_compat_adapter_candidate(item: dict[str, Any], client_kind: str, upstream_kind: str) -> bool:
    if client_kind != "chat" or upstream_kind != "responses":
        return False
    if str(item.get("responses_compat_mode") or "") == "codex":
        return True
    shape_status = str(item.get("shape_status") or "")
    shape_source = str(item.get("shape_verification_source") or "")
    return shape_status == "codex_shape_verified" or shape_source in {"diagnostic_codex_shape", "runtime_codex_compat_adapter"}


def route_item_format_adapter_allowed(
    item: dict[str, Any],
    client_kind: str,
    upstream_kind: str,
    body: dict[str, Any],
) -> bool:
    if client_kind == upstream_kind:
        if client_kind == "responses" and request_has_tools(body):
            if item.get("tool_call_support") == "unsupported":
                return False
            if request_has_tool_loop_history(body) and item.get("tool_call_support") != "verified":
                return False
        if client_kind == "chat":
            return chat_body_can_use_native_chat_upstream(body)
        return True
    if not ADAPTIVE_FORMAT_ROUTING:
        return False
    if client_kind == "responses" and upstream_kind == "chat":
        return responses_body_can_use_chat_adapter(body)
    if client_kind == "chat" and upstream_kind == "responses":
        if codex_compat_adapter_candidate(item, client_kind, upstream_kind):
            return chat_body_can_use_codex_compat_responses_adapter(body)
        return chat_body_can_use_responses_adapter(body)
    return False


def tool_loop_chat_adapter_candidates(model: str, body: dict[str, Any], controls: dict[str, Any]) -> list[dict[str, Any]]:
    if not (request_has_tools(body) and request_has_tool_loop_history(body)):
        return []
    candidates: list[dict[str, Any]] = []
    for item in (HEALTH.get("chat", {}).get(model) or {}).values():
        if item.get("healthy"):
            continue
        if item.get("tool_call_support") == "unsupported":
            continue
        if str(item.get("reason") or "") not in {"empty_response", "low_signal_response"}:
            continue
        if not provider_matches_controls(item, controls):
            continue
        candidate = deepcopy(item)
        if not route_item_format_adapter_allowed(candidate, "responses", "chat", body):
            continue
        candidate["_shadow"] = True
        candidate["_tool_loop_fallback"] = True
        candidates.append(annotate_route_item(candidate, "responses", "chat"))
    return sorted_route_bucket(candidates)


def adaptive_candidate_buckets(
    model: str,
    client_kind: str,
    body: dict[str, Any],
    controls: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: {"native": [], "adapter": []} for name in ROUTE_BUCKET_ORDER
    }
    upstream_kinds = [client_kind, "responses" if client_kind == "chat" else "chat"]
    for upstream_kind in upstream_kinds:
        for bucket in healthy_candidate_buckets(model, upstream_kind, controls):
            bucket_items = combined.setdefault(bucket["name"], {"native": [], "adapter": []})
            target = bucket_items["native" if upstream_kind == client_kind else "adapter"]
            for item in bucket["items"]:
                if route_item_format_adapter_allowed(item, client_kind, upstream_kind, body):
                    target.append(annotate_route_item(item, client_kind, upstream_kind))
    controls = controls or {}
    if client_kind == "responses":
        for item in tool_loop_chat_adapter_candidates(model, body, controls):
            name = route_bucket_name(item)
            combined.setdefault(name, {"native": [], "adapter": []})["adapter"].append(item)
    buckets = []
    for name in ROUTE_BUCKET_ORDER:
        bucket_items = combined.get(name) or {"native": [], "adapter": []}
        native_items = bucket_items.get("native") or []
        adapter_items = bucket_items.get("adapter") or []
        if native_items:
            buckets.append({"name": name, "items": sorted_route_bucket(native_items)})
        if adapter_items:
            buckets.append({"name": name, "items": sorted_route_bucket(adapter_items)})
    return buckets


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
            return pick_priority_weighted(items), bucket["name"]
    return None


def candidate_attempt_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("provider_id") or ""),
        str(item.get("actual_model") or ""),
        str(item.get("_upstream_kind") or item.get("kind") or ""),
    )


def pick_priority_weighted(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("candidates must not be empty")
    highest_priority = max(int(item.get("priority") or 0) for item in candidates)
    highest = [item for item in candidates if int(item.get("priority") or 0) == highest_priority]
    if any("_score" in item for item in highest):
        highest.sort(key=lambda item: (-float(item.get("_score") or 0), item.get("_adjusted_latency_ms") or 999999))
        best_score = float(highest[0].get("_score") or 0)
        highest = [item for item in highest if float(item.get("_score") or 0) == best_score]
    return pick_weighted(highest)


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
        expire_model_cache = reason in {"model_unsupported", "not_found"} and any(
            item.get("source") == "upstream_models" for item in matched
        )
        now_int = int(now())
        for item in matched:
            previous_count = (
                int(item.get("runtime_failure_count") or 0)
                if item.get("runtime_failure_reason") == reason
                else 0
            )
            failure_count = previous_count + 1
            if (
                item.get("healthy")
                and transient_runtime_failure_reason(reason)
                and failure_count < RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS
            ):
                item["runtime_failure_count"] = failure_count
                item["runtime_failure_required"] = RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS
                item["runtime_failure_reason"] = reason
                item["runtime_failure_last_at"] = now_int
                item["last_runtime_error"] = reason
                continue
            item["healthy"] = False
            item["reason"] = f"runtime_failure:{reason}"
            item["checked_at"] = now_int
            item["next_probe_at"] = now_int + probe_cooldown_seconds(reason, False)
            item["runtime_failure_count"] = failure_count
            item["runtime_failure_required"] = RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS
            item["runtime_failure_reason"] = reason
            item["runtime_failure_last_at"] = now_int
            item["last_runtime_error"] = reason
        if expire_model_cache and provider_id in MODEL_CACHE:
            MODEL_CACHE[provider_id]["next_refresh_at"] = 0
            MODEL_CACHE[provider_id]["reason"] = f"runtime_{reason}"
        if matched:
            await save_state()


async def mark_responses_shape_invalid_attempt(
    kind: str,
    model: str,
    provider_id: str,
    body: dict[str, Any],
    incoming_headers: dict[str, str] | None,
    latency_ms: int | None = None,
) -> None:
    if kind != "responses":
        return
    fingerprint = request_shape_fingerprint(body, incoming_headers)
    async with STATE_LOCK:
        matched = [
            item
            for item in (HEALTH.get(kind, {}).get(model) or {}).values()
            if item.get("provider_id") == provider_id
        ]
        now_int = int(now())
        for item in matched:
            previous_fingerprint = item.get("shape_fingerprint")
            previous_count = int(item.get("shape_invalid_count") or 0) if previous_fingerprint == fingerprint else 0
            count = previous_count + 1
            confirmed = count >= RESPONSES_INVALID_REQUEST_CONFIRMATIONS
            item["healthy"] = False
            item["reason"] = "runtime_failure:real_shape_invalid" if confirmed else "runtime_failure:responses_request_shape_unverified"
            item["checked_at"] = now_int
            item["shape_status"] = "real_shape_invalid" if confirmed else "confirming"
            item["shape_invalid_count"] = count
            item["shape_invalid_required"] = RESPONSES_INVALID_REQUEST_CONFIRMATIONS
            item["shape_fingerprint"] = fingerprint
            item["shape_invalid_last_at"] = now_int
            item["shape_verification_source"] = "runtime_real_request"
            if latency_ms is not None:
                item["latency_ms"] = latency_ms
            item["next_probe_at"] = now_int + (
                RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS if confirmed else RESPONSES_INVALID_REQUEST_RETRY_SECONDS
            )
        if matched:
            await save_state()


async def mark_tool_call_support(
    kind: str,
    model: str,
    provider_id: str,
    supported: bool,
    reason: str = "",
) -> None:
    async with STATE_LOCK:
        matched = [
            item
            for item in (HEALTH.get(kind, {}).get(model) or {}).values()
            if item.get("provider_id") == provider_id
        ]
        now_int = int(now())
        for item in matched:
            item["tool_call_support"] = "verified" if supported else "unsupported"
            item["tool_call_checked_at"] = now_int
            if supported:
                item.pop("tool_call_failure_reason", None)
            else:
                item["tool_call_failure_reason"] = reason or "tool_call_unavailable"
        if matched:
            await save_state()


async def mark_runtime_success(
    kind: str,
    model: str,
    provider_id: str,
    latency_ms: int,
    codex_compat: bool = False,
    tool_call_observed: bool = False,
) -> None:
    async with STATE_LOCK:
        matched = [
            item
            for item in (HEALTH.get(kind, {}).get(model) or {}).values()
            if item.get("provider_id") == provider_id
        ]
        for item in matched:
            item["healthy"] = True
            item["reason"] = "ok"
            item["status_code"] = 200
            item["latency_ms"] = latency_ms
            item["checked_at"] = int(now())
            item["next_probe_at"] = int(now()) + PROBE_SUCCESS_TTL_SECONDS
            item["sample"] = ""
            item["skip_reason"] = ""
            item["skipped"] = False
            item.pop("runtime_failure_count", None)
            item.pop("runtime_failure_required", None)
            item.pop("runtime_failure_reason", None)
            item.pop("runtime_failure_last_at", None)
            item.pop("last_runtime_error", None)
            if tool_call_observed:
                item["tool_call_support"] = "verified"
                item["tool_call_checked_at"] = int(now())
                item.pop("tool_call_failure_reason", None)
            if kind == "responses":
                if codex_compat:
                    item["shape_status"] = "codex_shape_verified"
                    item["shape_verification_source"] = "runtime_codex_compat_adapter"
                    item["responses_compat_mode"] = "codex"
                else:
                    item.pop("shape_status", None)
                    item.pop("shape_verification_source", None)
                    item.pop("responses_compat_mode", None)
                item.pop("shape_invalid_count", None)
                item.pop("shape_invalid_required", None)
                item.pop("shape_fingerprint", None)
                item.pop("shape_invalid_last_at", None)
        if matched:
            await save_state()


def log_route_fields(chosen: dict[str, Any], route_bucket: str | None = None) -> dict[str, Any]:
    return {
        "route_bucket": route_bucket or chosen.get("_route_bucket") or route_bucket_name(chosen),
        "route_group": chosen.get("route_group", "primary"),
        "cost_tier": chosen.get("cost_tier", "free"),
        "fallback_only": bool(chosen.get("fallback_only", False)),
        "shadow": bool(chosen.get("_shadow", False)),
        "upstream_kind": chosen.get("_upstream_kind") or chosen.get("kind") or "",
        "request_format": chosen.get("request_format") or "",
        "client_profile": normalize_client_profile(chosen.get("client_profile")),
        "format_adapter": chosen.get("_format_adapter") or "native",
        "adapter_latency_penalty_ms": int(chosen.get("_adapter_latency_penalty_ms") or 0),
    }


def normalize_responses_upstream_body(body: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    req_body = deepcopy(body)
    req_body["model"] = chosen["actual_model"]
    if "instructions" not in req_body:
        req_body["instructions"] = ""
    req_body.setdefault("store", False)
    return apply_responses_provider_defaults(req_body, chosen)


async def relay_non_stream(
    path: str,
    body: dict[str, Any],
    kind: str,
    controls: dict[str, Any] | None = None,
    incoming_headers: dict[str, str] | None = None,
) -> JSONResponse:
    controls = controls or {}
    request_id = f"gw_{uuid.uuid4().hex[:16]}"
    model = body.get("model")
    if not model:
        return JSONResponse({"error": {"message": "Missing model", "type": "invalid_request_error"}}, status_code=400)
    buckets = adaptive_candidate_buckets(model, kind, body, controls)
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
                "request_shape": request_shape(body, incoming_headers),
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
        attempt_key = candidate_attempt_key(chosen)
        for bucket in buckets:
            bucket["items"] = [item for item in bucket["items"] if candidate_attempt_key(item) != attempt_key]
        provider = get_provider_by_id(chosen["provider_id"])
        if not provider:
            continue
        upstream_kind = chosen.get("_upstream_kind") or kind
        upstream_path = path if upstream_kind == kind else upstream_path_for_kind(upstream_kind)
        req_body = prepare_upstream_body(body, chosen, kind)
        route_fields = log_route_fields(chosen, route_bucket)
        tried.append({"provider_id": chosen["provider_id"], "actual_model": chosen["actual_model"], **route_fields})
        start = now()
        endpoint_reasons: list[str] = []
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(provider.get("timeout_seconds") or REQUEST_TIMEOUT_SECONDS),
                follow_redirects=True,
            ) as client:
                response = None
                endpoint_url = ""
                codex_compat_retry_used = False
                for candidate_url in upstream_urls(provider, upstream_path):
                    endpoint_url = candidate_url
                    while True:
                        headers = upstream_request_headers(provider, incoming_headers, upstream_kind, chosen, request_id, bool(req_body.get("stream", False)))
                        response = await client.post(candidate_url, headers=headers, json=req_body)
                        text_sample = response.text[:1000]
                        if can_retry_with_partial(upstream_kind, response.status_code, text_sample, req_body):
                            learn_responses_partial_default(chosen)
                            req_body = apply_responses_provider_defaults(req_body, chosen)
                            continue
                        if not codex_compat_retry_used and can_retry_with_codex_compat_adapter(kind, upstream_kind, response.status_code, text_sample, chosen):
                            codex_compat_retry_used = True
                            enable_codex_compat_adapter(chosen)
                            req_body = prepare_upstream_body(body, chosen, kind)
                            route_fields = log_route_fields(chosen, route_bucket)
                            continue
                        break
                    if 200 <= response.status_code < 300:
                        break
                    endpoint_reasons.append(classify_error(response.status_code, response.text[:1000]))
                if response is None:
                    raise RuntimeError("no endpoint url")
            latency_ms = int((now() - start) * 1000)
            text = response.text
            try:
                data = response.json()
            except Exception:
                data = None
            if 200 <= response.status_code < 300 and not response_has_error_json(data):
                tool_call_observed = request_has_tools(body) and response_data_has_tool_call(data, upstream_kind)
                await mark_runtime_success(
                    upstream_kind,
                    model,
                    chosen["provider_id"],
                    latency_ms,
                    bool(chosen.get("_codex_compat_adapter")),
                    tool_call_observed,
                )
                if request_has_tools(body) and not tool_call_observed and tool_loop_text_detected(probe_response_text(data, upstream_kind)):
                    await mark_tool_call_support(upstream_kind, model, chosen["provider_id"], False, "tool_loop_text")
                client_data = convert_upstream_response_for_client(data, chosen, kind, request_id, model, req_body)
                await append_request_log(
                    {
                        "request_id": request_id,
                        "kind": kind,
                        "stream": bool(body.get("stream", False)),
                        "requested_model": model,
                        "actual_model": chosen["actual_model"],
                        "provider_id": chosen["provider_id"],
                        "path": upstream_path,
                        "endpoint_url": endpoint_url,
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "success": True,
                        "usage": extract_usage(data),
                        "route_controls": controls,
                        "request_shape": request_shape(body, incoming_headers),
                        **route_fields,
                    }
                )
                if client_data is not None:
                    return JSONResponse(client_data, status_code=response.status_code)
                return JSONResponse({"raw": text}, status_code=response.status_code)
            reason = classify_error(response.status_code, text[:1000])
            if not endpoint_reasons or endpoint_reasons[-1] != reason:
                endpoint_reasons.append(reason)
            if should_verify_responses_request_shape(upstream_kind, endpoint_reasons):
                await mark_responses_shape_invalid_attempt(upstream_kind, model, chosen["provider_id"], req_body, incoming_headers, latency_ms)
            else:
                runtime_failure_reason = runtime_failure_reason_for_endpoint_failures(upstream_kind, endpoint_reasons)
                if runtime_failure_reason:
                    await mark_runtime_failure(upstream_kind, model, chosen["provider_id"], runtime_failure_reason)
                elif should_mark_runtime_failure(reason, upstream_kind):
                    await mark_runtime_failure(upstream_kind, model, chosen["provider_id"], reason)
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": bool(body.get("stream", False)),
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": upstream_path,
                    "endpoint_url": endpoint_url,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "success": False,
                    "error_type": reason,
                    "error_sample": redact_text(text, 500),
                    "usage": extract_usage(data),
                    "route_controls": controls,
                    "request_shape": request_shape(body, incoming_headers),
                    **route_fields,
                }
            )
            last_error = {"status_code": response.status_code, "reason": reason, "body": text[:500], "tried": tried}
        except Exception as exc:
            reason = f"exception:{type(exc).__name__}"
            upstream_kind = chosen.get("_upstream_kind") or kind
            await mark_runtime_failure(upstream_kind, model, chosen["provider_id"], reason)
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": bool(body.get("stream", False)),
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": upstream_path if "upstream_path" in locals() else path,
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
    incoming_headers: dict[str, str] | None = None,
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

    buckets = adaptive_candidate_buckets(model, kind, body, controls)
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
                "request_shape": request_shape(body, incoming_headers),
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
        attempt_key = candidate_attempt_key(chosen)
        for bucket in buckets:
            bucket["items"] = [item for item in bucket["items"] if candidate_attempt_key(item) != attempt_key]
        provider = get_provider_by_id(chosen["provider_id"])
        if not provider:
            continue

        upstream_kind = chosen.get("_upstream_kind") or kind
        upstream_path = path if upstream_kind == kind else upstream_path_for_kind(upstream_kind)
        req_body = prepare_upstream_body(body, chosen, kind)
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
                codex_compat_retry_used = False
                for endpoint_url in upstream_urls(provider, upstream_path):
                    partial_retry_used = False
                    while True:
                        headers = upstream_request_headers(provider, incoming_headers, upstream_kind, chosen, request_id, bool(req_body.get("stream", True)))
                        async with client.stream("POST", endpoint_url, headers=headers, json=req_body) as response:
                            if response.status_code < 200 or response.status_code >= 300:
                                raw = await response.aread()
                                raw_text = raw.decode("utf-8", "ignore")
                                if not partial_retry_used and can_retry_with_partial(upstream_kind, response.status_code, raw_text[:1000], req_body):
                                    partial_retry_used = True
                                    learn_responses_partial_default(chosen)
                                    req_body = apply_responses_provider_defaults(req_body, chosen)
                                    continue
                                if not codex_compat_retry_used and can_retry_with_codex_compat_adapter(kind, upstream_kind, response.status_code, raw_text[:1000], chosen):
                                    codex_compat_retry_used = True
                                    enable_codex_compat_adapter(chosen)
                                    req_body = prepare_upstream_body(body, chosen, kind)
                                    route_fields = log_route_fields(chosen, route_bucket)
                                    continue
                                reason = classify_error(response.status_code, raw_text[:1000])
                                endpoint_reasons.append(reason)
                                await append_request_log(
                                    {
                                        "request_id": request_id,
                                        "kind": kind,
                                        "stream": True,
                                        "requested_model": model,
                                        "actual_model": chosen["actual_model"],
                                        "provider_id": chosen["provider_id"],
                                        "path": upstream_path,
                                        "endpoint_url": endpoint_url,
                                        "status_code": response.status_code,
                                        "latency_ms": int((now() - start) * 1000),
                                        "success": False,
                                        "error_type": reason,
                                        "error_sample": redact_text(raw_text, 500),
                                        "route_controls": controls,
                                        "request_shape": request_shape(body, incoming_headers),
                                        **route_fields,
                                    }
                                )
                                break

                            stream_adapter = StreamFormatAdapter(chosen, kind, request_id, model, req_body)
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
                                        "path": upstream_path,
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
                                break

                            latency_ms = int((now() - start) * 1000)
                            await mark_runtime_success(upstream_kind, model, chosen["provider_id"], latency_ms, bool(chosen.get("_codex_compat_adapter")))
                            await append_request_log(
                                {
                                    "request_id": request_id,
                                    "kind": kind,
                                    "stream": True,
                                    "requested_model": model,
                                    "actual_model": chosen["actual_model"],
                                    "provider_id": chosen["provider_id"],
                                    "path": upstream_path,
                                    "endpoint_url": endpoint_url,
                                    "status_code": response.status_code,
                                    "latency_ms": latency_ms,
                                    "success": True,
                                    "route_controls": controls,
                                    "request_shape": request_shape(body, incoming_headers),
                                    **route_fields,
                                }
                            )
                            stream_started = True
                            converted = stream_adapter.feed(first)
                            if converted:
                                if b"[DONE]" in converted:
                                    done_sent = True
                                if b"response.completed" in converted:
                                    response_completed = True
                                yield converted
                            async for chunk in raw_chunks:
                                if chunk:
                                    converted = stream_adapter.feed(chunk)
                                    if not converted:
                                        continue
                                    if b"[DONE]" in converted:
                                        done_sent = True
                                    if b"response.completed" in converted:
                                        response_completed = True
                                    yield converted
                            converted = stream_adapter.flush()
                            if converted:
                                if b"[DONE]" in converted:
                                    done_sent = True
                                if b"response.completed" in converted:
                                    response_completed = True
                                yield converted
                            if kind == "responses" and not response_completed:
                                completion = stream_adapter.completion_event()
                                if completion:
                                    yield completion
                            if not done_sent:
                                yield b"data: [DONE]\n\n"
                            if request_has_tools(body):
                                if stream_adapter.tool_call_observed():
                                    await mark_tool_call_support(upstream_kind, model, chosen["provider_id"], True)
                                elif stream_adapter.tool_loop_detected():
                                    await mark_tool_call_support(upstream_kind, model, chosen["provider_id"], False, "tool_loop_text")
                            return
                    if stream_started:
                        return
                    continue

                runtime_failure_reason = runtime_failure_reason_for_endpoint_failures(upstream_kind, endpoint_reasons)
                if should_verify_responses_request_shape(upstream_kind, endpoint_reasons):
                    await mark_responses_shape_invalid_attempt(
                        upstream_kind,
                        model,
                        chosen["provider_id"],
                        req_body,
                        incoming_headers,
                        int((now() - start) * 1000),
                    )
                elif runtime_failure_reason:
                    await mark_runtime_failure(upstream_kind, model, chosen["provider_id"], runtime_failure_reason)
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
            await mark_runtime_failure(upstream_kind, model, chosen["provider_id"], f"exception:{type(exc).__name__}")
            await append_request_log(
                {
                    "request_id": request_id,
                    "kind": kind,
                    "stream": True,
                    "requested_model": model,
                    "actual_model": chosen["actual_model"],
                    "provider_id": chosen["provider_id"],
                    "path": upstream_path,
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
            "request_shape": request_shape(body, incoming_headers),
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
    incoming_headers = dict(getattr(request, "headers", {}) or {})
    if body.get("stream", False):
        return StreamingResponse(relay_stream("/chat/completions", body, "chat", controls, incoming_headers), media_type="text/event-stream")
    return await relay_non_stream("/chat/completions", body, "chat", controls, incoming_headers)


@app.post("/v1")
async def v1_chat_alias(request: Request, authorization: str | None = Header(default=None)):
    return await chat_completions(request, authorization)


@app.post("/v1/responses")
async def responses(request: Request, authorization: str | None = Header(default=None)):
    if not auth_ok(authorization):
        return JSONResponse({"error": {"message": "Unauthorized", "type": "auth_error"}}, status_code=401)
    body = await request.json()
    controls = request_route_controls(request)
    incoming_headers = dict(getattr(request, "headers", {}) or {})
    if body.get("stream", False):
        return StreamingResponse(relay_stream("/responses", body, "responses", controls, incoming_headers), media_type="text/event-stream")
    return await relay_non_stream("/responses", body, "responses", controls, incoming_headers)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def fallback(path: str):
    return JSONResponse({"error": {"message": f"Unsupported path: /{path}", "type": "unsupported_path"}}, status_code=404)
