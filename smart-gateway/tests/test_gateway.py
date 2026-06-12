from __future__ import annotations

import importlib
import json
import sqlite3

import httpx
import pytest
import respx
from starlette.requests import Request


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    (config_dir / "gateway.yaml").write_text(
        """
canonical_models:
  good-model:
    - good-model
model_include:
  - "*"
model_exclude:
  - "*embedding*"
probe:
  chat:
    enabled: true
    path: /chat/completions
    body:
      messages:
        - role: user
          content: ping
      max_tokens: 8
      stream: false
  responses:
    enabled: true
    path: /responses
    body:
      input: ping
      max_output_tokens: 8
      stream: false
""",
        encoding="utf-8",
    )
    (config_dir / "providers.yaml").write_text(
        """
providers:
  - id: p1
    name: Provider 1
    enabled: true
    base_url: https://p1.example/v1
    api_key: ${P1_KEY}
    priority: 100
    weight: 100
    declared_models:
      - good-model
      - text-embedding-3-small
  - id: p2
    name: Provider 2
    enabled: true
    base_url: https://p2.example/v1
    api_key: ${P2_KEY}
    priority: 100
    weight: 100
    declared_models:
      - good-model
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("MASTER_API_KEY", "master")
    monkeypatch.setenv("ADMIN_TOKEN", "admin")
    monkeypatch.setenv("P1_KEY", "sk-p1")
    monkeypatch.setenv("P2_KEY", "sk-p2")
    monkeypatch.setenv("PROBE_ON_STARTUP", "false")
    monkeypatch.setenv("PROBE_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("MODELS_REFRESH_SECONDS", "3600")
    monkeypatch.setenv("PROBE_MAX_PER_CYCLE", "100")
    monkeypatch.setenv("PROBE_SUCCESS_TTL_SECONDS", "3600")
    monkeypatch.setenv("PROBE_UNSUPPORTED_TTL_SECONDS", "86400")
    import app.main as main

    module = importlib.reload(main)
    return module


@pytest.mark.asyncio()
async def test_auth_and_unsupported_path(gateway):
    response = await gateway.fallback("anything")
    assert response.status_code == 404


def test_normalize_base_url_preserves_versioned_paths(gateway):
    assert gateway.normalize_base_url("https://example.test/v1") == "https://example.test/v1"
    assert gateway.normalize_base_url("https://example.test/api/coding/v3") == "https://example.test/api/coding/v3"
    assert gateway.normalize_base_url("https://example.test/codex") == "https://example.test/codex/v1"
    assert gateway.normalize_base_url("https://example.test/codex", exact=True) == "https://example.test/codex"


def test_normalize_base_urls_keeps_compatible_endpoints(gateway):
    provider = {
        "base_url": "https://primary.example",
        "base_urls": ["https://backup.example/v1", "https://primary.example/v1"],
    }

    assert gateway.normalize_base_urls(provider) == [
        "https://primary.example/v1",
        "https://backup.example/v1",
    ]


def test_provider_model_filter_selects_latest_per_rule(gateway):
    provider = {
        "model_filters": [
            {"include": ["deepseek-*flash*"], "limit": 1},
            {"include": ["deepseek-*pro*"], "limit": 1},
            {"include": ["glm-*"], "limit": 1},
        ]
    }
    models = [
        "deepseek-v4-flash-260425",
        "deepseek-v3-flash-250101",
        "deepseek-v4-pro-260425",
        "deepseek-v3-pro-250101",
        "glm-4-5-air-20250728",
        "glm-4-7-251222",
        "doubao-seed-2-0-pro-260215",
    ]

    assert gateway.provider_model_filter(provider, models) == [
        "deepseek-v4-flash-260425",
        "deepseek-v4-pro-260425",
        "glm-4-7-251222",
    ]


def test_build_probe_targets_keeps_declared_models_missing_from_upstream_models(gateway):
    provider = {
        "declared_models": ["glm-5.1", "deepseek-v4-flash"],
        "model_filters": [{"include": ["glm-*"], "limit": 1}],
    }
    fetched_models = ["glm-4-7-251222"]

    targets = gateway.build_probe_targets(provider, fetched_models)

    assert {"local_model": "glm-5.1", "actual_model": "glm-5.1", "source": "declared"} in targets
    assert {"local_model": "deepseek-v4-flash", "actual_model": "deepseek-v4-flash", "source": "declared"} in targets
    assert {"local_model": "glm-4-7-251222", "actual_model": "glm-4-7-251222", "source": "upstream_models"} in targets


def test_classify_error_prefers_semantic_reason(gateway):
    assert gateway.classify_error(403, '{"message":"Insufficient account balance"}') == "quota"
    assert gateway.classify_error(404, '{"error":"当前 API 不支持所选模型 gpt-5.5"}') == "model_unsupported"
    assert gateway.classify_error(400, '{"code":"invalid_responses_request","message":"invalid codex request"}') == "invalid_request"


def test_with_channel_fields_treats_only_status_one_as_enabled(gateway):
    provider = {"id": "p1", "base_url": "https://p1.example", "enabled": True}

    assert gateway.with_channel_fields(provider, {"status": 1, "base_url": "https://p1.example"})["enabled"] is True
    assert gateway.with_channel_fields(provider, {"status": 2, "base_url": "https://p1.example"})["enabled"] is False
    assert gateway.with_channel_fields(provider, {"status": 0, "base_url": "https://p1.example"})["enabled"] is False


def test_provider_headers_passthrough_keeps_upstream_authorization(gateway):
    headers = gateway.provider_headers(
        {"api_key": "sk-upstream", "headers": {}},
        {
            "authorization": "Bearer sk-user",
            "openai-beta": "responses=v1",
            "x-stainless-runtime": "node",
            "user-agent": "codex-test",
            "x-not-allowed": "drop",
        },
    )

    assert headers["Authorization"] == "Bearer sk-upstream"
    assert headers["openai-beta"] == "responses=v1"
    assert headers["x-stainless-runtime"] == "node"
    assert headers["user-agent"] == "codex-test"
    assert "x-not-allowed" not in headers


def test_provider_headers_adds_responses_beta(gateway):
    headers = gateway.provider_headers({"api_key": "sk-upstream", "headers": {}}, {}, "responses")

    assert headers["Authorization"] == "Bearer sk-upstream"
    assert headers["OpenAI-Beta"] == "responses=v1"


def test_normalize_responses_upstream_body_adds_codex_required_defaults(gateway):
    body = {"model": "gpt-5.5", "input": [{"role": "user", "content": "ping"}], "stream": True}
    chosen = {"actual_model": "gpt-5.5"}

    req_body = gateway.normalize_responses_upstream_body(body, chosen)

    assert req_body["model"] == "gpt-5.5"
    assert req_body["instructions"] == ""
    assert req_body["store"] is False
    assert "instructions" not in body
    assert "store" not in body


@pytest.mark.asyncio()
@respx.mock
async def test_probe_lists_only_really_healthy_models(gateway):
    respx.get("https://p1.example/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "good-model"}, {"id": "fake-model"}]})
    )
    respx.get("https://p2.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.post("https://p1.example/v1/chat/completions").mock(return_value=httpx.Response(200, json={"id": "ok"}))
    respx.post("https://p1.example/v1/responses").mock(return_value=httpx.Response(404, json={"error": "missing"}))
    respx.post("https://p2.example/v1/chat/completions").mock(return_value=httpx.Response(403, json={"error": "bad"}))
    respx.post("https://p2.example/v1/responses").mock(return_value=httpx.Response(403, json={"error": "bad"}))

    await gateway.probe_all()

    response = await gateway.list_models("Bearer master")
    models = [item["id"] for item in response["data"]]
    assert models == ["fake-model", "good-model"]
    matrix = await gateway.admin_matrix("Bearer admin", None)
    good_item = next(
        item for item in matrix["health"]["chat"]["good-model"].values() if item["provider_id"] == "p1" and item["actual_model"] == "good-model"
    )
    fake_item = next(
        item for item in matrix["health"]["chat"]["fake-model"].values() if item["provider_id"] == "p1" and item["actual_model"] == "fake-model"
    )
    assert good_item["healthy"] is True
    assert good_item["source"] == "upstream_models+declared"
    assert good_item["request_format"] == "openai-compatible"
    assert good_item["probe_path"] == "/chat/completions"
    assert fake_item["source"] == "upstream_models"
    assert "text-embedding-3-small" not in matrix["health"]["chat"]


@pytest.mark.asyncio()
@respx.mock
async def test_probe_respects_cooldown_and_force_rechecks(gateway):
    models_route = respx.get("https://p1.example/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "good-model"}]})
    )
    respx.get("https://p2.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    chat_route = respx.post("https://p1.example/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    responses_route = respx.post("https://p1.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    respx.post("https://p2.example/v1/chat/completions").mock(return_value=httpx.Response(403, json={"error": "bad"}))
    respx.post("https://p2.example/v1/responses").mock(return_value=httpx.Response(403, json={"error": "bad"}))

    await gateway.probe_all()
    await gateway.probe_all()

    assert models_route.call_count == 1
    assert chat_route.call_count == 1
    assert responses_route.call_count == 1
    item = next(item for item in gateway.HEALTH["chat"]["good-model"].values() if item["provider_id"] == "p1")
    assert item["skipped"] is True
    assert item["skip_reason"] == "cooldown"

    await gateway.probe_all(force=True)

    assert models_route.call_count == 2
    assert chat_route.call_count == 2
    assert responses_route.call_count == 2


@pytest.mark.asyncio()
@respx.mock
async def test_probe_success_overrides_responses_request_shape_runtime_failure(gateway):
    respx.get("https://p1.example/v1/models").mock(return_value=httpx.Response(200, json={"data": [{"id": "good-model"}]}))
    respx.get("https://p2.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.post("https://p1.example/v1/chat/completions").mock(return_value=httpx.Response(200, json={"id": "ok"}))
    respx.post("https://p1.example/v1/responses").mock(return_value=httpx.Response(200, json={"id": "ok"}))
    respx.post("https://p2.example/v1/chat/completions").mock(return_value=httpx.Response(403, json={"error": "bad"}))
    respx.post("https://p2.example/v1/responses").mock(return_value=httpx.Response(403, json={"error": "bad"}))
    next_probe_at = int(gateway.now()) + 1800
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "reason": "runtime_failure:invalid_request",
                    "next_probe_at": next_probe_at,
                    "checked_at": int(gateway.now()),
                    "provider_signature": "stale",
                },
            }
        },
        "chat": {},
    }

    await gateway.probe_all()

    item = gateway.HEALTH["responses"]["good-model"]["p1::good-model"]
    assert item["healthy"] is True
    assert item["reason"] == "ok"
    assert item["next_probe_at"] > next_probe_at


@pytest.mark.asyncio()
@respx.mock
async def test_probe_keeps_declared_models_when_probe_budget_is_exhausted(gateway):
    gateway.PROBE_MAX_PER_CYCLE = 1
    respx.get("https://p1.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get("https://p2.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.post("https://p1.example/v1/chat/completions").mock(return_value=httpx.Response(200, json={"id": "ok"}))

    await gateway.probe_all()

    assert "good-model" in gateway.HEALTH["responses"]
    item = next(
        item
        for item in gateway.HEALTH["responses"]["good-model"].values()
        if item["provider_id"] == "p1" and item["actual_model"] == "good-model"
    )
    assert item["healthy"] is False
    assert item["source"] == "declared"
    assert item["reason"] == "probe_budget_exhausted"

    candidates = gateway.healthy_candidates("good-model", "responses")
    assert any(candidate["provider_id"] == "p1" and candidate["_shadow"] for candidate in candidates)


@pytest.mark.asyncio()
async def test_non_stream_failover_marks_failed_provider(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "timeout_seconds": 3, "headers": {}},
        {"id": "p2", "base_url": "https://p2.example/v1", "api_key": "sk-p2", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
                "p2": {"provider_id": "p2", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
            }
        },
        "responses": {},
    }
    monkeypatch.setattr(gateway, "pick_weighted", lambda candidates: candidates[0])

    with respx.mock:
        respx.post("https://p1.example/v1/chat/completions").mock(return_value=httpx.Response(500, json={"error": "down"}))
        p2_route = respx.post("https://p2.example/v1/chat/completions").mock(return_value=httpx.Response(200, json={"id": "ok"}))
        response = await gateway.relay_non_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}]},
            "chat",
            incoming_headers={"openai-beta": "responses=v1", "authorization": "Bearer sk-user"},
        )
        assert response.status_code == 200
        assert json.loads(response.body.decode())["id"] == "ok"

    assert gateway.HEALTH["chat"]["good-model"]["p1"]["healthy"] is False
    assert gateway.HEALTH["chat"]["good-model"]["p2"]["healthy"] is True
    assert p2_route.calls.last.request.headers["Authorization"] == "Bearer sk-p2"
    assert p2_route.calls.last.request.headers["openai-beta"] == "responses=v1"
    logs = gateway.read_recent_request_logs()
    assert logs[0]["success"] is True
    assert logs[0]["provider_id"] == "p2"
    assert logs[0]["usage"] == {}
    assert logs[1]["success"] is False
    assert logs[1]["provider_id"] == "p1"


@pytest.mark.asyncio()
async def test_non_stream_uses_paid_fallback_only_after_primary_fails(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "primary", "base_url": "https://primary.example/v1", "api_key": "sk-primary", "timeout_seconds": 3, "headers": {}},
        {"id": "paid", "base_url": "https://paid.example/v1", "api_key": "sk-paid", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "responses": {},
    }
    monkeypatch.setattr(gateway, "pick_weighted", lambda candidates: candidates[0])

    with respx.mock:
        primary_route = respx.post("https://primary.example/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "down"})
        )
        paid_route = respx.post("https://paid.example/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"id": "ok"})
        )
        response = await gateway.relay_non_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}]},
            "chat",
        )

    assert response.status_code == 200
    assert primary_route.call_count == 1
    assert paid_route.call_count == 1
    logs = gateway.read_recent_request_logs()
    assert logs[0]["provider_id"] == "paid"
    assert logs[0]["route_bucket"] == "paid_fallback"


@pytest.mark.asyncio()
async def test_non_stream_uses_paid_fallback_after_responses_invalid_request(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {
            "id": "primary",
            "base_url": "https://primary.example/v1",
            "base_urls": ["https://primary.example/v1", "https://primary-alt.example/v1"],
            "api_key": "sk-primary",
            "timeout_seconds": 3,
            "headers": {},
        },
        {"id": "paid", "base_url": "https://paid.example/v1", "api_key": "sk-paid", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "chat": {},
    }
    monkeypatch.setattr(gateway, "pick_weighted", lambda candidates: candidates[0])

    with respx.mock:
        respx.post("https://primary.example/v1/responses").mock(
            return_value=httpx.Response(400, json={"error": {"message": "invalid codex request", "code": "invalid_responses_request"}})
        )
        respx.post("https://primary-alt.example/v1/responses").mock(
            return_value=httpx.Response(400, json={"error": {"message": "invalid codex request", "code": "invalid_responses_request"}})
        )
        paid_route = respx.post("https://paid.example/v1/responses").mock(return_value=httpx.Response(200, json={"id": "paid-ok"}))
        response = await gateway.relay_non_stream(
            "/responses",
            {"model": "good-model", "input": "ping", "stream": False},
            "responses",
        )

    assert paid_route.call_count == 1
    assert response.status_code == 200
    payload = json.loads(response.body.decode())
    assert payload["id"] == "paid-ok"
    logs = gateway.read_recent_request_logs()
    assert logs[0]["provider_id"] == "paid"
    assert logs[0]["route_bucket"] == "paid_fallback"


@pytest.mark.asyncio()
async def test_non_stream_respects_forced_provider_and_no_paid(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "primary", "base_url": "https://primary.example/v1", "api_key": "sk-primary", "timeout_seconds": 3, "headers": {}},
        {"id": "paid", "base_url": "https://paid.example/v1", "api_key": "sk-paid", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 100,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "responses": {},
    }
    monkeypatch.setattr(gateway, "pick_weighted", lambda candidates: candidates[0])

    with respx.mock:
        primary_route = respx.post("https://primary.example/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"id": "primary-ok"})
        )
        paid_route = respx.post("https://paid.example/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"id": "paid-ok"})
        )
        response = await gateway.relay_non_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}]},
            "chat",
            {"provider_id": "paid"},
        )

    assert json.loads(response.body.decode())["id"] == "paid-ok"
    assert primary_route.call_count == 0
    assert paid_route.call_count == 1

    denied = await gateway.relay_non_stream(
        "/chat/completions",
        {"model": "good-model", "messages": [{"role": "user", "content": "ping"}]},
        "chat",
        {"provider_id": "paid", "allow_paid": False},
    )
    assert denied.status_code == 503


def test_healthy_candidates_keeps_lower_priority_failover(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "latency_ms": 1000,
                },
                "p2": {
                    "provider_id": "p2",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 100,
                    "latency_ms": 1,
                },
            }
        },
        "responses": {},
    }

    candidates = gateway.healthy_candidates("good-model", "chat")

    assert [item["provider_id"] for item in candidates] == ["p1", "p2"]


def test_select_route_candidate_uses_priority_before_weight(gateway, monkeypatch):
    selected_weights = []

    def fake_pick_weighted(candidates):
        selected_weights.append([item["provider_id"] for item in candidates])
        return candidates[0]

    monkeypatch.setattr(gateway, "pick_weighted", fake_pick_weighted)
    buckets = [
        {
            "name": "primary",
            "items": [
                {"provider_id": "low-heavy", "priority": 10, "weight": 10000},
                {"provider_id": "high-light", "priority": 100, "weight": 1},
                {"provider_id": "high-heavy", "priority": 100, "weight": 100},
            ],
        }
    ]

    chosen, bucket_name = gateway.select_route_candidate(buckets)

    assert bucket_name == "primary"
    assert chosen["provider_id"] == "high-light"
    assert selected_weights == [["high-light", "high-heavy"]]


def test_legacy_paid_cost_tag_is_migrated_to_paid_fallback(gateway):
    provider = {"id": "p1", "base_url": "https://p1.example", "enabled": True}
    item = gateway.with_channel_fields(provider, {"status": 1, "base_url": "https://p1.example", "tag": "gateway-source,gw:paid"})

    assert item["route_group"] == "paid_fallback"
    assert item["fallback_only"] is True


def test_healthy_candidate_buckets_order_paid_last(gateway, monkeypatch):
    monkeypatch.setattr(gateway, "ROUTE_EXPLORATION_RATE", 0.0)
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "backup": {
                    "provider_id": "backup",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 90,
                    "weight": 1,
                    "route_group": "backup",
                    "cost_tier": "metered",
                },
                "shadow::good-model": {
                    "provider_id": "shadow",
                    "actual_model": "good-model",
                    "healthy": False,
                    "priority": 80,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                    "source": "upstream_models",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "responses": {},
    }

    buckets = gateway.healthy_candidate_buckets("good-model", "chat")
    assert [bucket["name"] for bucket in buckets] == ["primary", "backup", "shadow", "paid_fallback"]
    assert [item["provider_id"] for item in gateway.healthy_candidates("good-model", "chat")] == [
        "primary",
        "backup",
        "shadow",
        "paid",
    ]


def test_healthy_candidate_buckets_keeps_explore_after_primary(gateway, monkeypatch):
    monkeypatch.setattr(gateway.random, "random", lambda: 0.0)
    monkeypatch.setattr(gateway, "ROUTE_EXPLORATION_RATE", 1.0)
    monkeypatch.setattr(gateway, "ROUTE_EXPLORATION_MAX_CANDIDATES", 1)
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "opportunistic::good-model": {
                    "provider_id": "opportunistic",
                    "actual_model": "good-model",
                    "healthy": False,
                    "priority": 70,
                    "weight": 1,
                    "route_group": "opportunistic",
                    "cost_tier": "free",
                    "source": "upstream_models",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "responses": {},
    }

    buckets = gateway.healthy_candidate_buckets("good-model", "chat")
    candidates = gateway.healthy_candidates("good-model", "chat")

    assert [bucket["name"] for bucket in buckets] == ["primary", "explore", "paid_fallback"]
    assert [item["provider_id"] for item in candidates] == ["primary", "opportunistic", "paid"]
    assert candidates[1]["_explore"] is True


def test_responses_probe_retry_runs_before_paid_fallback(gateway):
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "primary::good-model": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": False,
                    "kind": "responses",
                    "priority": 100,
                    "weight": 100,
                    "route_group": "primary",
                    "source": "upstream_models+declared",
                    "reason": "runtime_failure:invalid_request",
                    "next_probe_at": int(gateway.now()) + 3600,
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "fallback_only": True,
                },
            }
        },
        "chat": {},
    }

    buckets = gateway.healthy_candidate_buckets("good-model", "responses")

    assert [bucket["name"] for bucket in buckets] == ["probe_retry", "paid_fallback"]


def test_exploration_does_not_include_paid_shadow(gateway, monkeypatch):
    monkeypatch.setattr(gateway.random, "random", lambda: 0.0)
    monkeypatch.setattr(gateway, "ROUTE_EXPLORATION_RATE", 1.0)
    monkeypatch.setattr(gateway, "ROUTE_EXPLORATION_MAX_CANDIDATES", 2)
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "paid-shadow::good-model": {
                    "provider_id": "paid-shadow",
                    "actual_model": "good-model",
                    "healthy": False,
                    "priority": 90,
                    "weight": 1,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                    "source": "upstream_models",
                },
            }
        },
        "responses": {},
    }

    candidates = gateway.healthy_candidates("good-model", "chat")

    assert [item["provider_id"] for item in candidates] == ["primary", "paid-shadow"]
    assert candidates[1]["_shadow"] is True
    assert "_explore" not in candidates[1]


def test_healthy_candidates_route_controls(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "backup": {
                    "provider_id": "backup",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 90,
                    "weight": 1,
                    "route_group": "backup",
                    "cost_tier": "metered",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 1000,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "responses": {},
    }

    by_provider = gateway.healthy_candidates("good-model", "chat", {"provider_id": "backup"})
    no_paid = gateway.healthy_candidates("good-model", "chat", {"allow_paid": False})
    backup_only = gateway.healthy_candidates("good-model", "chat", {"route_group": "backup"})

    assert [item["provider_id"] for item in by_provider] == ["backup"]
    assert [item["provider_id"] for item in no_paid] == ["primary", "backup"]
    assert [item["provider_id"] for item in backup_only] == ["backup"]


def test_healthy_candidates_includes_shadow_upstream_models(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "source": "upstream_models",
                    "kind": "responses",
                    "priority": 100,
                    "weight": 1,
                    "reason": "not_found",
                },
            }
        },
        "responses": {},
    }

    candidates = gateway.healthy_candidates("good-model", "chat")

    assert len(candidates) == 1
    assert candidates[0]["provider_id"] == "p1"
    assert candidates[0]["_shadow"] is True


def test_healthy_candidates_skips_shadow_runtime_failure_during_cooldown(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "source": "upstream_models",
                    "kind": "responses",
                    "priority": 100,
                    "weight": 1,
                    "reason": "runtime_failure:not_found",
                    "next_probe_at": int(gateway.now()) + 3600,
                },
            }
        },
        "responses": {},
    }

    assert gateway.healthy_candidates("good-model", "chat") == []


def test_healthy_candidates_allows_forced_shadow_during_runtime_failure_cooldown(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "source": "upstream_models",
                    "kind": "responses",
                    "priority": 100,
                    "weight": 1,
                    "reason": "runtime_failure:model_unsupported",
                    "next_probe_at": int(gateway.now()) + 3600,
                },
            }
        },
        "responses": {},
    }

    candidates = gateway.healthy_candidates("good-model", "chat", {"provider_id": "p1"})

    assert [item["provider_id"] for item in candidates] == ["p1"]
    assert candidates[0]["_shadow"] is True


def test_healthy_candidates_retries_runtime_invalid_request_for_responses(gateway):
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "source": "upstream_models",
                    "kind": "responses",
                    "priority": 100,
                    "weight": 1,
                    "reason": "runtime_failure:invalid_request",
                    "next_probe_at": int(gateway.now()) + 3600,
                },
            }
        },
        "chat": {},
    }

    candidates = gateway.healthy_candidates("good-model", "responses")

    assert [item["provider_id"] for item in candidates] == ["p1"]
    assert candidates[0]["_probe_retry"] is True
    assert candidates[0]["_shadow"] is True


def test_healthy_candidates_allows_forced_runtime_invalid_request(gateway):
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": False,
                    "source": "upstream_models",
                    "priority": 100,
                    "weight": 1,
                    "reason": "runtime_failure:invalid_request",
                    "next_probe_at": int(gateway.now()) + 3600,
                },
            }
        },
        "chat": {},
    }

    candidates = gateway.healthy_candidates("good-model", "responses", {"provider_id": "p1"})

    assert [item["provider_id"] for item in candidates] == ["p1"]
    assert candidates[0]["_shadow"] is True


@pytest.mark.asyncio()
async def test_runtime_failure_sets_probe_cooldown(gateway):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                },
            }
        },
        "responses": {},
    }

    await gateway.mark_runtime_failure("chat", "good-model", "p1", "model_unsupported")

    item = next(item for item in gateway.HEALTH["chat"]["good-model"].values() if item["provider_id"] == "p1")
    assert item["healthy"] is False
    assert item["reason"] == "runtime_failure:model_unsupported"
    assert item["next_probe_at"] > gateway.now()


def test_runtime_failure_reason_for_endpoint_failures(gateway):
    assert gateway.should_mark_runtime_failure("invalid_request") is False
    assert gateway.should_mark_runtime_failure("invalid_request", "responses") is False
    assert gateway.should_mark_runtime_failure("quota") is True
    assert gateway.runtime_failure_reason_for_endpoint_failures("responses", ["invalid_request", "invalid_request"]) is None
    assert gateway.runtime_failure_reason_for_endpoint_failures("chat", ["invalid_request"]) is None
    assert gateway.runtime_failure_reason_for_endpoint_failures("responses", ["invalid_request", "server_unavailable"]) == "all_endpoints_failed"


@pytest.mark.asyncio()
async def test_stream_does_not_append_gateway_error_after_first_chunk(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
            }
        },
        "responses": {},
    }

    class BrokenStream:
        status_code = 200

        async def aiter_raw(self):
            yield b"data: first\n\n"
            raise httpx.ReadError("stream dropped")

    class BrokenContext:
        async def __aenter__(self):
            return BrokenStream()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return BrokenContext()

    monkeypatch.setattr(gateway.httpx, "AsyncClient", BrokenClient)

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}], "stream": True},
            "chat",
        )
    ]
    joined = b"".join(chunks)
    assert b"data: first" in joined
    assert b"all_upstreams_failed" not in joined
    assert joined.endswith(b"data: [DONE]\n\n")


@pytest.mark.asyncio()
async def test_stream_forwards_chunks_after_first_chunk(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
            }
        },
        "responses": {},
    }

    class MultiChunkStream:
        status_code = 200

        async def aiter_raw(self):
            yield b"data: role\n\n"
            yield b"data: content\n\n"
            yield b"data: [DONE]\n\n"

    class MultiChunkContext:
        async def __aenter__(self):
            return MultiChunkStream()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class MultiChunkClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return MultiChunkContext()

    monkeypatch.setattr(gateway.httpx, "AsyncClient", MultiChunkClient)

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}], "stream": True},
            "chat",
        )
    ]

    assert chunks == [b"data: role\n\n", b"data: content\n\n", b"data: [DONE]\n\n"]


@pytest.mark.asyncio()
async def test_stream_adds_done_marker_when_upstream_omits_it(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
            }
        },
        "responses": {},
    }

    class NoDoneStream:
        status_code = 200

        async def aiter_raw(self):
            yield b"data: first\n\n"

    class NoDoneContext:
        async def __aenter__(self):
            return NoDoneStream()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class NoDoneClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return NoDoneContext()

    monkeypatch.setattr(gateway.httpx, "AsyncClient", NoDoneClient)

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/chat/completions",
            {"model": "good-model", "messages": [{"role": "user", "content": "ping"}], "stream": True},
            "chat",
        )
    ]
    joined = b"".join(chunks)
    assert b"data: first" in joined
    assert joined.endswith(b"data: [DONE]\n\n")
    assert b"all_upstreams_failed" not in joined


@pytest.mark.asyncio()
async def test_responses_stream_adds_completed_event_when_upstream_omits_it(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 100, "weight": 1},
            }
        },
        "chat": {},
    }

    class NoCompletedStream:
        status_code = 200

        async def aiter_raw(self):
            yield b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"ok"}\n\n'

    class NoCompletedContext:
        async def __aenter__(self):
            return NoCompletedStream()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class NoCompletedClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return NoCompletedContext()

    monkeypatch.setattr(gateway.httpx, "AsyncClient", NoCompletedClient)

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/responses",
            {"model": "good-model", "input": "ping", "stream": True},
            "responses",
        )
    ]
    joined = b"".join(chunks)
    assert b"response.output_text.delta" in joined
    assert b"event: response.completed" in joined
    assert b'"status":"completed"' in joined
    assert joined.endswith(b"data: [DONE]\n\n")


@pytest.mark.asyncio()
async def test_responses_stream_error_uses_response_failed_event(gateway):
    gateway.HEALTH = {"responses": {}, "chat": {}}

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/responses",
            {"model": "missing-model", "input": "ping", "stream": True},
            "responses",
        )
    ]
    joined = b"".join(chunks)
    assert b"event: response.failed" in joined
    assert b"no_healthy_upstream" in joined
    assert joined.endswith(b"data: [DONE]\n\n")


@pytest.mark.asyncio()
async def test_responses_stream_invalid_request_does_not_cool_down_provider_after_all_endpoints_fail(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {
            "id": "p1",
            "base_url": "https://p1.example/v1",
            "base_urls": ["https://p1.example/v1", "https://p1-alt.example/v1"],
            "api_key": "sk-p1",
            "timeout_seconds": 3,
            "headers": {},
        },
    ]
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "p1::good-model": {
                    "provider_id": "p1",
                    "actual_model": "good-model",
                    "healthy": True,
                    "source": "upstream_models+declared",
                    "reason": "ok",
                    "priority": 100,
                    "weight": 1,
                },
            }
        },
        "chat": {},
    }

    class InvalidRequestStream:
        status_code = 400

        async def aread(self):
            return b'{"error":{"message":"invalid codex request","code":"invalid_responses_request"}}'

    class InvalidRequestContext:
        async def __aenter__(self):
            return InvalidRequestStream()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class InvalidRequestClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return InvalidRequestContext()

    monkeypatch.setattr(gateway.httpx, "AsyncClient", InvalidRequestClient)

    chunks = [
        chunk
        async for chunk in gateway.relay_stream(
            "/responses",
            {"model": "good-model", "input": "ping", "stream": True},
            "responses",
        )
    ]
    joined = b"".join(chunks)
    item = gateway.HEALTH["responses"]["good-model"]["p1::good-model"]
    assert b"all_upstreams_failed" in joined
    assert item["healthy"] is True
    assert item["reason"] == "ok"


@pytest.mark.asyncio()
async def test_responses_stream_uses_paid_fallback_after_invalid_request(gateway, monkeypatch):
    gateway.PROVIDERS = [
        {"id": "primary", "base_url": "https://primary.example/v1", "api_key": "sk-primary", "timeout_seconds": 3, "headers": {}},
        {"id": "paid", "base_url": "https://paid.example/v1", "api_key": "sk-paid", "timeout_seconds": 3, "headers": {}},
    ]
    gateway.HEALTH = {
        "responses": {
            "good-model": {
                "primary": {
                    "provider_id": "primary",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 100,
                    "weight": 1,
                    "route_group": "primary",
                    "cost_tier": "free",
                },
                "paid": {
                    "provider_id": "paid",
                    "actual_model": "good-model",
                    "healthy": True,
                    "priority": 10,
                    "weight": 100,
                    "route_group": "paid_fallback",
                    "cost_tier": "paid",
                    "fallback_only": True,
                },
            }
        },
        "chat": {},
    }
    monkeypatch.setattr(gateway, "pick_weighted", lambda candidates: candidates[0])

    with respx.mock:
        respx.post("https://primary.example/v1/responses").mock(
            return_value=httpx.Response(400, json={"error": {"message": "invalid codex request", "code": "invalid_responses_request"}})
        )
        paid_route = respx.post("https://paid.example/v1/responses").mock(return_value=httpx.Response(200, text="data: ok\n\n"))
        chunks = [
            chunk
            async for chunk in gateway.relay_stream(
                "/responses",
                {"model": "good-model", "input": "ping", "stream": True},
                "responses",
            )
        ]

    joined = b"".join(chunks)
    assert paid_route.call_count == 1
    assert b"data: ok" in joined


def make_request(host: str = "example.test") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/api/overview",
            "headers": [(b"host", host.encode()), (b"x-forwarded-proto", b"https")],
            "query_string": b"",
            "server": (host, 443),
            "scheme": "https",
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.asyncio()
async def test_admin_overview_requires_token_and_exposes_gateway_config(gateway):
    denied = await gateway.admin_overview(make_request(), None, None)
    assert denied.status_code == 401

    gateway.PROVIDERS = [{"id": "p1", "base_url": "https://p1.example/v1", "api_key": "sk-p1", "priority": 1, "weight": 1}]
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 1, "weight": 1}
            }
        },
        "responses": {},
    }
    overview = await gateway.admin_overview(make_request("api.example.com"), "Bearer admin", None)
    assert overview["base_url"] == "https://api.example.com"
    assert overview["legacy_base_url"] == "https://api.example.com/v1"
    assert overview["new_api_admin_url"] == "https://api.example.com/"
    assert overview["admin_url"] == "https://api.example.com/gateway-admin/"
    assert overview["router_channel_name"] == "Smart Gateway Router"
    assert overview["source_tag"] == "gateway-source"
    assert overview["router_groups"] == "default,vip"
    assert "master_api_key" not in overview
    assert overview["models"] == [{"id": "good-model", "chat_ok": 1, "responses_ok": 0}]


@pytest.mark.asyncio()
async def test_admin_request_logs_requires_token_and_returns_recent_logs(gateway):
    await gateway.append_request_log({"request_id": "req1", "kind": "chat", "success": True})

    denied = await gateway.admin_request_logs(None, None)
    assert denied.status_code == 401

    response = await gateway.admin_request_logs("Bearer admin", None, 10)
    assert response["logs"][0]["request_id"] == "req1"


@pytest.mark.asyncio()
async def test_admin_save_providers_is_read_only_by_default(gateway):
    class BodyRequest:
        async def json(self):
            return {"providers": []}

    result = await gateway.admin_save_providers(BodyRequest(), "Bearer admin", None)

    assert result.status_code == 403


@pytest.mark.asyncio()
async def test_admin_save_providers_validates_and_writes_config_when_enabled(gateway, monkeypatch):
    scheduled = []

    def fake_probe_all(force=False):
        scheduled.append(force)
        async def noop():
            return None
        return noop()

    monkeypatch.setattr(gateway, "probe_all", fake_probe_all)
    monkeypatch.setattr(gateway.asyncio, "create_task", lambda coro: coro.close())
    monkeypatch.setattr(gateway, "ALLOW_GATEWAY_PROVIDER_WRITE", True)

    class BodyRequest:
        async def json(self):
            return {
                "providers": [
                    {
                        "id": "new_provider",
                        "name": "New Provider",
                        "enabled": True,
                        "base_url": "https://new.example/v1",
                        "base_url_exact": True,
                        "api_key": "sk-new",
                        "priority": 50,
                        "weight": 100,
                        "declared_models": ["good-model"],
                    }
                ]
            }

    result = await gateway.admin_save_providers(BodyRequest(), "Bearer admin", None)
    assert result["ok"] is True
    saved = gateway.load_yaml(gateway.PROVIDERS_FILE)
    assert saved["providers"][0]["id"] == "new_provider"
    assert saved["providers"][0]["base_url_exact"] is True
    assert saved["providers"][0]["api_key"] == "sk-new"
    assert scheduled == [False]


def test_update_newapi_source_policy_parses_string_booleans(gateway, tmp_path, monkeypatch):
    db = tmp_path / "one-api.db"
    con = sqlite3.connect(db)
    con.execute(
        'create table channels (id integer primary key, name text, tag text, base_url text, status integer, weight integer, priority integer, models text, "group" text)'
    )
    con.execute(
        'insert into channels (id, name, tag, base_url, status, weight, priority, models, "group") values (2, "anyrouter.top", "gateway-source", "https://old.example", 1, 10, 10, "gpt-5.5", "default")'
    )
    con.commit()
    con.close()
    monkeypatch.setattr(gateway, "NEWAPI_DB", db)

    changed = gateway.update_newapi_source_policy(
        [
            {
                "id": 2,
                "enabled": "true",
                "route_group": "primary",
                "cost_tier": "free",
                "fallback_only": "false",
                "priority": 100,
                "weight": 100,
                "base_url": "https://new.example",
                "models": "gpt-5.5",
            }
        ]
    )

    row = sqlite3.connect(db).execute('select status, tag from channels where id = 2').fetchone()
    assert changed == 1
    assert row == (1, "gateway-source,gw:primary")


def test_load_newapi_channel_rows_ignores_empty_database(gateway, tmp_path, monkeypatch):
    db = tmp_path / "one-api.db"
    sqlite3.connect(db).close()
    monkeypatch.setattr(gateway, "NEWAPI_DB", db)

    assert gateway.load_newapi_channel_rows() == []


@pytest.mark.asyncio()
async def test_admin_reload_uses_incremental_probe_by_default(gateway, monkeypatch):
    scheduled = []

    def fake_probe_all(force=False):
        scheduled.append(force)
        async def noop():
            return None
        return noop()

    monkeypatch.setattr(gateway, "probe_all", fake_probe_all)
    monkeypatch.setattr(gateway.asyncio, "create_task", lambda coro: coro.close())

    result = await gateway.admin_reload("Bearer admin", None)
    forced = await gateway.admin_reload("Bearer admin", None, True)

    assert result["message"] == "reload started: incremental probe"
    assert forced["message"] == "reload started: full probe"
    assert scheduled == [False, True]


@pytest.mark.asyncio()
async def test_v1_root_aliases_models_and_chat(gateway, monkeypatch):
    gateway.HEALTH = {
        "chat": {
            "good-model": {
                "p1": {"provider_id": "p1", "actual_model": "good-model", "healthy": True, "priority": 1, "weight": 1}
            }
        },
        "responses": {},
    }
    models = await gateway.v1_index("Bearer master")
    assert [item["id"] for item in models["data"]] == ["good-model"]

    async def fake_relay_non_stream(path, body, kind, controls=None, incoming_headers=None):
        return gateway.JSONResponse({"path": path, "kind": kind, "model": body["model"]})

    class BodyRequest:
        async def json(self):
            return {"model": "good-model", "messages": [{"role": "user", "content": "ping"}], "stream": False}

    monkeypatch.setattr(gateway, "relay_non_stream", fake_relay_non_stream)
    response = await gateway.v1_chat_alias(BodyRequest(), "Bearer master")
    assert json.loads(response.body.decode()) == {
        "path": "/chat/completions",
        "kind": "chat",
        "model": "good-model",
    }
