#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DB = os.getenv("NEWAPI_DB", "/newapi-data/one-api.db")
DEFAULT_PROVIDERS = os.getenv("GATEWAY_PROVIDERS_FILE", "config/providers.yaml")
DEFAULT_ENV = os.getenv("GATEWAY_ENV_FILE", ".env")
DEFAULT_HEALTH_STATE = os.getenv("GATEWAY_HEALTH_STATE_FILE", "data/health_state.json")
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18000"
SOURCE_GROUP = "gateway-source"
SOURCE_TAG = "gateway-source"
DEFAULT_GROUP = "default"
DEFAULT_ROUTER_GROUPS = ["default", "vip"]
ROUTER_NAME = "Smart Gateway Router"
ROUTER_BASE_URL = "http://smart-gateway:8000"
ROUTER_SETTING = {
    "force_format": False,
    "thinking_to_content": False,
    "proxy": "",
    "pass_through_body_enabled": True,
    "system_prompt": "",
    "system_prompt_override": False,
}
ROUTER_SETTINGS = {
    "allow_service_tier": True,
    "disable_store": False,
    "allow_safety_identifier": True,
    "allow_include_obfuscation": True,
    "upstream_model_update_check_enabled": False,
    "upstream_model_update_auto_sync_enabled": False,
    "upstream_model_update_ignored_models": [],
    "upstream_model_update_last_detected_models": [],
    "upstream_model_update_last_check_time": 0,
}
ROUTER_PARAM_OVERRIDE = {
    "operations": [
        {
            "mode": "pass_headers",
            "value": [
                "OpenAI-Beta",
                "Originator",
                "Session_id",
                "X-Codex-Beta-Features",
                "X-Codex-Turn-Metadata",
                "X-Stainless-Arch",
                "X-Stainless-Lang",
                "X-Stainless-OS",
                "X-Stainless-Package-Version",
                "X-Stainless-Retry-Count",
                "X-Stainless-Runtime",
                "X-Stainless-Runtime-Version",
                "X-Request-Id",
                "User-Agent",
            ],
        }
    ]
}
DEFAULT_MODEL_RATIO = 0.5
MODEL_RATIO_KEY = "ModelRatio"
MODEL_RATIO_ARCHIVE_KEY = "SmartGatewayModelRatioArchive"
MODEL_SYNC_TAG = "smart-gateway"
MODEL_AUTO_DISABLED_TAG = "smart-gateway-auto-disabled"
VOLCES_CODING_DECLARED_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.1",
]
MUYUAN_CLIENT_HEADERS = {
    "User-Agent": "claude-cli/2.1.133",
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14",
}


def resolve_path(path: str, alternates: list[str]) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    for alt in alternates:
        alt_path = Path(alt)
        if alt_path.exists():
            return alt_path
    return candidate


def resolve_newapi_db(path: str, env: dict[str, str]) -> Path:
    alternates = ["/newapi-data/one-api.db"]
    data_dir = env.get("NEWAPI_DATA_DIR") or os.getenv("NEWAPI_DATA_DIR")
    if data_dir:
        alternates.insert(0, str(Path(data_dir) / "one-api.db"))
    return resolve_path(path, alternates)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    target_dir = path.parent / "backups" if path.name.endswith(".db") else path.parent.parent / "data" / "config_backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime())
    target = target_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    if path.suffix in {".yaml", ".yml", ".env"}:
        target.chmod(0o600)
    return target


def slug(value: str) -> str:
    text = re.sub(r"^https?://", "", value.strip().lower())
    text = re.sub(r"[^a-z0-9_.-]+", "_", text)
    return text.strip("._-") or "provider"


def route_policy_for(name: str, base_url: str) -> dict[str, Any]:
    text = f"{name} {base_url}".lower()
    if "eqing" in text:
        return {"route_group": "paid_fallback", "cost_tier": "paid", "fallback_only": True, "priority": 10, "weight": 100}
    if "anyrouter" in text:
        return {"route_group": "primary", "cost_tier": "free", "fallback_only": False, "priority": 100, "weight": 100}
    if "muyuan" in text:
        return {"route_group": "primary", "cost_tier": "free", "fallback_only": False, "priority": 90, "weight": 100}
    if "sharedchat" in text:
        return {"route_group": "opportunistic", "cost_tier": "free", "fallback_only": False, "priority": 80, "weight": 100}
    if "volces" in text or "ark.cn-beijing.volces" in text:
        return {"route_group": "backup", "cost_tier": "metered", "fallback_only": False, "priority": 60, "weight": 100}
    return {"route_group": "opportunistic", "cost_tier": "unknown", "fallback_only": False, "priority": 50, "weight": 100}


def split_tags(value: str | None) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\s]+", value or "") if item.strip()]


def ensure_tag(value: str | None, required: str) -> str:
    tags = split_tags(value)
    if required not in tags:
        tags.insert(0, required)
    return ",".join(dict.fromkeys(tags))


def apply_route_tags(policy: dict[str, Any], tag_value: str | None) -> dict[str, Any]:
    tags = set(split_tags(tag_value))
    if "gateway-source" in tags and not any(tag.startswith("gw:") for tag in tags):
        return dict(policy)
    route_groups = {"primary", "opportunistic", "backup", "paid_fallback", "other"}
    cost_tiers = {"free", "metered", "paid", "unknown"}
    updated = dict(policy)
    for tag in tags:
        if tag.startswith("gw:"):
            value = tag.removeprefix("gw:")
            if value in route_groups:
                updated["route_group"] = value
            elif value in cost_tiers:
                updated["cost_tier"] = value
            elif value == "fallback-only":
                updated["fallback_only"] = True
            elif value == "not-fallback-only":
                updated["fallback_only"] = False
    if updated.get("route_group") == "paid_fallback":
        updated["fallback_only"] = True
        if updated.get("cost_tier") in {"unknown", "free"}:
            updated["cost_tier"] = "paid"
    return updated


def normalize_base_url(base_url: str) -> tuple[str, bool]:
    value = base_url.strip().rstrip("/")
    if re.search(r"/v\d+$", value) or value.endswith("/codex"):
        return value, value.endswith("/codex")
    return f"{value}/v1", False


def compatible_base_urls(name: str, base_url: str) -> list[str]:
    text = f"{name} {base_url}".lower()
    if "anyrouter" not in text and "a-ocnfniawgw.cn-shanghai.fcapp.run" not in text:
        return []
    candidates = [
        base_url,
        normalize_base_url("https://a-ocnfniawgw.cn-shanghai.fcapp.run")[0],
        normalize_base_url("https://anyrouter.top")[0],
    ]
    return list(dict.fromkeys(candidates))


def provider_client_headers(name: str, base_url: str) -> dict[str, str]:
    text = f"{name} {base_url}".lower()
    if "muyuan.do" in text:
        return dict(MUYUAN_CLIENT_HEADERS)
    return {}


def provider_chat_request_format(name: str, base_url: str) -> str:
    text = f"{name} {base_url}".lower()
    if "muyuan.do" in text:
        return "anthropic"
    return ""


def provider_from_channel(row: sqlite3.Row) -> dict[str, Any]:
    name = row["name"] or f"newapi_channel_{row['id']}"
    base_url, exact = normalize_base_url(row["base_url"] or "")
    policy = apply_route_tags(route_policy_for(name, base_url), row["tag"])
    provider: dict[str, Any] = {
        "id": f"newapi_ch{row['id']}_{slug(name)}",
        "name": name,
        "enabled": row["status"] == 1,
        "base_url": base_url,
        "api_key": row["key"],
        "priority": policy["priority"],
        "weight": int(row["weight"] or policy["weight"] or 100),
        "timeout_seconds": 60.0,
        "route_group": policy["route_group"],
        "cost_tier": policy["cost_tier"],
        "fallback_only": policy["fallback_only"],
        "declared_models": [item.strip() for item in (row["models"] or "").split(",") if item.strip()],
        "headers": provider_client_headers(name, base_url),
        "source": "new-api-channel",
        "new_api_channel_id": row["id"],
    }
    chat_format = provider_chat_request_format(name, base_url)
    if chat_format:
        provider["chat_request_format"] = chat_format
    if exact:
        provider["base_url_exact"] = True
    base_urls = compatible_base_urls(name, base_url)
    if base_urls:
        provider["base_urls"] = base_urls
    if "ark.cn-beijing.volces" in base_url:
        provider["declared_models"] = VOLCES_CODING_DECLARED_MODELS
        provider["models_from_declared_only"] = True
    return provider


def load_router_models(master_key: str, gateway_url: str) -> str:
    if not master_key:
        return "gpt-5.5"
    request = urllib.request.Request(
        f"{gateway_url.rstrip('/')}/v1/models",
        headers={"Authorization": f"Bearer {master_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return "gpt-5.5"
    models = sorted(
        {str(item.get("id")) for item in data.get("data", []) if isinstance(item, dict) and item.get("id")},
        key=model_sort_rank,
    )
    return ",".join(models) if models else "gpt-5.5"


def model_version_key(model: str) -> tuple[int, ...]:
    return tuple(int(value) for value in re.findall(r"\d+", str(model or "")))


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


def load_json_option(con: sqlite3.Connection, key: str) -> dict[str, Any]:
    row = con.execute("select value from options where key = ?", (key,)).fetchone()
    try:
        data = json.loads(row[0]) if row and row[0] else {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def write_json_option(con: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    con.execute(
        """
        insert into options (key, value) values (?, ?)
        on conflict(key) do update set value = excluded.value
        """,
        (key, text),
    )


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"pragma table_info({table})").fetchall()}


def model_ratio_default(model: str, ratios: dict[str, Any], archive: dict[str, Any]) -> Any:
    if model in archive:
        return archive[model]
    if model in ratios:
        return ratios[model]
    lowered = model.lower()
    for prefix, value in [
        ("gpt-5.5", ratios.get("gpt-5.5", DEFAULT_MODEL_RATIO)),
        ("gpt-5", ratios.get("gpt-5.5", DEFAULT_MODEL_RATIO)),
        ("claude-opus", ratios.get("claude-opus-4-7", 7.5)),
        ("claude-sonnet", ratios.get("claude-sonnet-4-6", 1.5)),
        ("claude-haiku", ratios.get("claude-haiku-4-5-20251001", 0.5)),
        ("deepseek", ratios.get("deepseek-chat", 0.135)),
        ("glm", ratios.get("glm-5.1", DEFAULT_MODEL_RATIO)),
        ("gemini", ratios.get("gemini-2.5-pro", 0.625)),
    ]:
        if lowered.startswith(prefix):
            return value
    return ratios.get("gpt-5.5", DEFAULT_MODEL_RATIO)


def sync_model_ratio(con: sqlite3.Connection, models_csv: str) -> tuple[int, int]:
    models = [item.strip() for item in models_csv.split(",") if item.strip()]
    current = set(models)
    ratios = load_json_option(con, MODEL_RATIO_KEY)
    archive = load_json_option(con, MODEL_RATIO_ARCHIVE_KEY)
    archive.update(ratios)
    next_ratios: dict[str, Any] = {}
    added = 0
    for model in models:
        if model not in archive and model not in ratios:
            added += 1
        next_ratios[model] = model_ratio_default(model, ratios, archive)
        archive[model] = next_ratios[model]
    removed = len([model for model in ratios if model not in current])
    write_json_option(con, MODEL_RATIO_KEY, next_ratios)
    write_json_option(con, MODEL_RATIO_ARCHIVE_KEY, archive)
    return added, removed


def parse_groups(value: str | None) -> list[str]:
    groups = [item.strip() for item in (value or "").split(",") if item.strip()]
    return groups or DEFAULT_ROUTER_GROUPS


def disabled_models(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "select model_name, tags from models where status = 0 and deleted_at is null"
    ).fetchall()
    disabled: set[str] = set()
    for row in rows:
        tags = split_tags(row["tags"])
        if row["model_name"] and MODEL_AUTO_DISABLED_TAG not in tags:
            disabled.add(str(row["model_name"]))
    return disabled


def filter_models_csv(models_csv: str, disabled: set[str]) -> str:
    models = [item.strip() for item in models_csv.split(",") if item.strip() and item.strip() not in disabled]
    return ",".join(sorted(dict.fromkeys(models), key=model_sort_rank))


def channel_id_from_provider_id(provider_id: str | None) -> int | None:
    match = re.match(r"^newapi_ch(\d+)_", provider_id or "")
    if not match:
        return None
    return int(match.group(1))


def load_healthy_models_by_channel(path: Path) -> tuple[dict[int, set[str]], set[int]]:
    if not path.exists():
        return {}, set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, set()
    health = data.get("health") if isinstance(data, dict) else {}
    if not isinstance(health, dict):
        return {}, set()

    healthy: dict[int, set[str]] = {}
    seen: set[int] = set()
    for kind in ("chat", "responses"):
        model_groups = health.get(kind) or {}
        if not isinstance(model_groups, dict):
            continue
        for local_model, items in model_groups.items():
            if not isinstance(items, dict):
                continue
            for item in items.values():
                if not isinstance(item, dict):
                    continue
                channel_id = channel_id_from_provider_id(str(item.get("provider_id") or ""))
                if channel_id is None:
                    continue
                seen.add(channel_id)
                model_name = str(item.get("local_model") or local_model or "").strip()
                if item.get("healthy") and model_name:
                    healthy.setdefault(channel_id, set()).add(model_name)
    return healthy, seen


def sync_source_channel_models(
    con: sqlite3.Connection,
    source_rows: list[sqlite3.Row],
    healthy_by_channel: dict[int, set[str]],
    seen_channel_ids: set[int],
) -> int:
    # Source channel model lists are operator declarations in New API, not
    # runtime health state. Keep them stable; Smart Gateway uses health_state
    # for effective routing and cooldowns.
    return 0


def sync_router_abilities(
    con: sqlite3.Connection,
    router_id: int,
    source_channel_ids: list[int],
    models_csv: str,
    router_groups: list[str],
) -> int:
    models = [item.strip() for item in models_csv.split(",") if item.strip()]
    if source_channel_ids:
        placeholders = ",".join("?" for _ in source_channel_ids)
        con.execute(
            f"delete from abilities where channel_id in ({placeholders})",
            tuple(source_channel_ids),
        )
    con.execute("delete from abilities where channel_id = ?", (router_id,))
    if not models:
        return 0
    rows = [
        (group, model, router_id, 1, 1000, 100, "")
        for group in router_groups
        for model in models
    ]
    con.executemany(
        """
        insert into abilities ("group", model, channel_id, enabled, priority, weight, tag)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def sync_models_table(con: sqlite3.Connection, models_csv: str) -> int:
    models = [item.strip() for item in models_csv.split(",") if item.strip()]
    current = set(models)
    now_ts = int(time.time())
    added = 0
    rows = con.execute(
        "select id, model_name, tags, status from models where deleted_at is null"
    ).fetchall()
    for row in rows:
        tags = split_tags(row["tags"])
        if MODEL_SYNC_TAG in tags and row["model_name"] not in current and row["status"] != 0:
            if MODEL_AUTO_DISABLED_TAG not in tags:
                tags.append(MODEL_AUTO_DISABLED_TAG)
            con.execute(
                "update models set tags = ?, status = 0, updated_time = ? where id = ?",
                (",".join(tags), now_ts, row["id"]),
            )
    for model in models:
        exists = con.execute(
            "select id, tags from models where model_name = ? and deleted_at is null",
            (model,),
        ).fetchone()
        if exists:
            tags = split_tags(exists["tags"])
            if MODEL_SYNC_TAG not in tags:
                tags.append(MODEL_SYNC_TAG)
            tags = [tag for tag in tags if tag != MODEL_AUTO_DISABLED_TAG]
            con.execute(
                "update models set tags = ?, status = 1, updated_time = ? where id = ?",
                (",".join(tags), now_ts, exists["id"]),
            )
        else:
            con.execute(
                """
                insert into models (
                    model_name, description, icon, tags, vendor_id, endpoints,
                    status, sync_official, created_time, updated_time, name_rule
                ) values (?, '', '', 'smart-gateway', null, '["openai"]', 1, 0, ?, ?, 0)
                """,
                (model, now_ts, now_ts),
            )
            added += 1
    return added


def write_if_changed(path: Path, text: str, no_backup: bool) -> tuple[bool, Path | None]:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == text:
        return False, None
    backup_path = None if no_backup else backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    return True, backup_path


def reload_smart_gateway(admin_token: str, gateway_url: str) -> bool:
    if not admin_token:
        return False
    req = urllib.request.Request(
        f"{gateway_url.rstrip('/')}/gateway-admin/reload",
        data=b"",
        headers={"Authorization": f"Bearer {admin_token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def connect_network() -> None:
    try:
        subprocess.run(
            ["docker", "network", "connect", "ai-smart-gateway_ai-gateway", "subapi-new-api"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return


def sync(args: argparse.Namespace) -> None:
    providers_path = resolve_path(args.providers, ["/workspace/config/providers.yaml", "/app/config/providers.yaml"])
    env_path = resolve_path(args.env, ["/workspace/.env"])
    env = load_env(env_path)
    db_path = resolve_newapi_db(args.db, env)
    health_state_path = resolve_path(getattr(args, "health_state", DEFAULT_HEALTH_STATE), ["/data/health_state.json"])
    master_key = env.get("MASTER_API_KEY", "")
    admin_token = env.get("ADMIN_TOKEN", "")
    gateway_url = args.gateway_url.rstrip("/")
    if not master_key:
        raise SystemExit("MASTER_API_KEY is missing in Smart Gateway .env")
    router_groups = parse_groups(args.router_groups or os.getenv("NEW_API_ROUTER_GROUPS"))

    db_backup = None if args.no_backup else backup(db_path)
    providers_backup = None
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if args.auto_adopt_default_channels:
            con.execute(
                """
                update channels
                set tag = ?, "group" = ?, priority = case when coalesce(priority, 0) <= 0 then 50 else priority end,
                    weight = case when coalesce(weight, 0) <= 0 then 100 else weight end
                where coalesce(name, '') != ?
                  and coalesce(base_url, '') != ?
                  and "group" = ?
                  and coalesce(status, 1) = 1
                  and coalesce(tag, '') = ''
                """,
                ("gateway-source,gw:opportunistic,gw:unknown", DEFAULT_GROUP, ROUTER_NAME, ROUTER_BASE_URL, DEFAULT_GROUP),
            )
        source_rows = con.execute(
            """
            select * from channels
            where (
                ',' || replace(coalesce(tag, ''), ' ', '') || ',' like ?
                or "group" = ?
            )
              and coalesce(base_url, '') != ?
              and coalesce(name, '') != ?
            order by priority desc, weight desc, id asc
            """,
            (f"%,{SOURCE_TAG},%", SOURCE_GROUP, ROUTER_BASE_URL, ROUTER_NAME),
        ).fetchall()
        if not source_rows and args.bootstrap:
            con.execute(
                """
                update channels
                set tag = ?, "group" = ?
                where coalesce(name, '') != ?
                  and coalesce(base_url, '') != ?
                  and "group" = ?
                """,
                (SOURCE_TAG, DEFAULT_GROUP, ROUTER_NAME, ROUTER_BASE_URL, DEFAULT_GROUP),
            )
            con.commit()
            source_rows = con.execute(
                """
                select * from channels
                where (
                    ',' || replace(coalesce(tag, ''), ' ', '') || ',' like ?
                    or "group" = ?
                )
                  and coalesce(base_url, '') != ?
                  and coalesce(name, '') != ?
                order by priority desc, weight desc, id asc
                """,
                (f"%,{SOURCE_TAG},%", SOURCE_GROUP, ROUTER_BASE_URL, ROUTER_NAME),
            ).fetchall()

        healthy_by_channel, seen_channel_ids = load_healthy_models_by_channel(health_state_path)
        source_models_changed = sync_source_channel_models(con, source_rows, healthy_by_channel, seen_channel_ids)

        providers = [provider_from_channel(row) for row in source_rows]
        for row, provider in zip(source_rows, providers):
            if int(row["status"] or 0) != 1:
                provider["declared_models"] = []
        source_channel_ids = [int(row["id"]) for row in source_rows]
        if not providers:
            raise SystemExit(f"No New API channels found in group {SOURCE_GROUP!r}")

        if source_channel_ids:
            for row in source_rows:
                normalized_tag = ensure_tag(row["tag"], SOURCE_TAG)
                if row["tag"] != normalized_tag or row["group"] != DEFAULT_GROUP:
                    con.execute(
                        'update channels set tag = ?, "group" = ? where id = ?',
                        (normalized_tag, DEFAULT_GROUP, row["id"]),
                    )

        providers_text = yaml.safe_dump({"providers": providers}, allow_unicode=True, sort_keys=False)
        providers_changed, providers_backup = write_if_changed(providers_path, providers_text, args.no_backup)

        discovered_models = load_router_models(master_key, gateway_url)
        models = filter_models_csv(discovered_models, disabled_models(con))
        now_ts = int(time.time())
        channel_columns = table_columns(con, "channels")
        router_extra_columns = [column for column in ("setting", "settings", "param_override") if column in channel_columns]
        router_extra_values = {
            "setting": json.dumps(ROUTER_SETTING, ensure_ascii=False, separators=(",", ":")),
            "settings": json.dumps(ROUTER_SETTINGS, ensure_ascii=False, separators=(",", ":")),
            "param_override": json.dumps(ROUTER_PARAM_OVERRIDE, ensure_ascii=False, separators=(",", ":")),
        }
        existing = con.execute("select id from channels where name = ? or base_url = ?", (ROUTER_NAME, ROUTER_BASE_URL)).fetchone()
        if existing:
            extra_set = "".join(f", {column} = ?" for column in router_extra_columns)
            con.execute(
                f"""
                update channels
                set type = 1, key = ?, base_url = ?, models = ?, "group" = ?, status = 1,
                    priority = 1000, weight = 100, auto_ban = 0, test_model = 'gpt-5.5',
                    tag = ''{extra_set},
                    remark = 'New API front door -> Smart Gateway intelligent upstream router'
                where id = ?
                """,
                (
                    master_key,
                    ROUTER_BASE_URL,
                    models,
                    DEFAULT_GROUP,
                    *(router_extra_values[column] for column in router_extra_columns),
                    existing["id"],
                ),
            )
            router_id = existing["id"]
        else:
            extra_insert_columns = "".join(f", {column}" for column in router_extra_columns)
            extra_placeholders = "".join(", ?" for _ in router_extra_columns)
            con.execute(
                f"""
                insert into channels (
                    type, key, status, name, weight, created_time, base_url, models,
                    "group", priority, auto_ban, test_model{extra_insert_columns}, remark
                ) values (1, ?, 1, ?, 100, ?, ?, ?, ?, 1000, 0, 'gpt-5.5'{extra_placeholders},
                    'New API front door -> Smart Gateway intelligent upstream router')
                """,
                (
                    master_key,
                    ROUTER_NAME,
                    now_ts,
                    ROUTER_BASE_URL,
                    models,
                    DEFAULT_GROUP,
                    *(router_extra_values[column] for column in router_extra_columns),
                ),
            )
            router_id = int(con.execute("select last_insert_rowid()").fetchone()[0])
        model_ratio_added, model_ratio_removed = sync_model_ratio(con, models)
        abilities_synced = sync_router_abilities(con, int(router_id), source_channel_ids, models, router_groups)
        model_rows_added = sync_models_table(con, models)
        con.commit()
    finally:
        con.close()

    connect_network()
    did_reload = reload_smart_gateway(admin_token, gateway_url) if providers_changed or args.force_reload else False
    print(f"synced {len(providers)} source channels into {providers_path}")
    print(f"router channel id: {router_id}")
    print(f"provider config changed: {providers_changed}")
    print(f"model ratios added: {model_ratio_added}")
    print(f"model ratios removed from active set: {model_ratio_removed}")
    print(f"source channel models pruned: {source_models_changed}")
    print(f"router abilities synced: {abilities_synced}")
    print(f"model rows added: {model_rows_added}")
    print(f"router groups: {','.join(router_groups)}")
    print(f"smart gateway reload: {did_reload}")
    print(f"database backup: {db_backup}")
    print(f"providers backup: {providers_backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync New API source channels into AI Smart Gateway.")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument("--env", default=DEFAULT_ENV)
    parser.add_argument("--health-state", default=DEFAULT_HEALTH_STATE)
    parser.add_argument("--gateway-url", default=os.getenv("SMART_GATEWAY_INTERNAL_URL", DEFAULT_GATEWAY_URL))
    parser.add_argument("--router-groups", default="", help="comma-separated New API groups served by Smart Gateway Router")
    parser.add_argument("--bootstrap", action="store_true", help="move current default direct channels to gateway-source first")
    parser.add_argument("--auto-adopt-default-channels", action="store_true", help="tag enabled default New API channels without tags as gateway-source")
    parser.add_argument("--no-backup", action="store_true", help="skip backup files; useful for frequent automatic sync")
    parser.add_argument("--force-reload", action="store_true", help="reload Smart Gateway even when provider config is unchanged")
    args = parser.parse_args()
    sync(args)


if __name__ == "__main__":
    main()
