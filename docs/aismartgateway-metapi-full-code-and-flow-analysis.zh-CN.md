# AiSmartGateway 全链路代码审计与 metapi 对比

生成时间：2026-06-14  
审计范围：`/root/AiSmartGateway` 与 `/root/metapi`  
metapi 来源：`https://github.com/cita-777/metapi.git`，本机路径 `/root/metapi`，当前 `git pull --ff-only` 结果为 `Already up to date`。

## 0. 总结结论

AiSmartGateway 是一个“New API 后置智能路由器”。它不负责用户体系、余额、下游 Key、模型市场和账号生命周期，核心集中在 `smart-gateway/app/main.py`：从 New API 转进来的 OpenAI Chat/Responses 请求，基于 `HEALTH` 矩阵、provider 配置、运行时反馈和格式 adapter 选择一个真实上游，完成请求体/请求头转换、上游调用、流式/非流式转换、输出校验、健康状态回写和请求日志。

metapi 是一个“完整的上游聚合平台”。它自己就是公开代理入口，拥有下游 API Key、站点/账号/Token、余额、签到、模型发现、路由生成、代理日志、计费、OAuth、React 管理台、Electron 桌面端和多数据库运行时。它的健康体系不是单一矩阵，而是 DB 路由表 + 运行时站点健康倍率 + 通道冷却 + endpoint 运行时记忆 + 模型可用性探测 + 冷却恢复探测的组合。

最关键差异：

| 维度 | AiSmartGateway | metapi |
|---|---|---|
| 定位 | New API 后置路由层 | 一体化中转聚合平台 |
| 公共鉴权 | `MASTER_API_KEY`，通常由 New API 调它 | `PROXY_TOKEN` 或托管下游 API Key，直接面对客户端 |
| 管理鉴权 | `ADMIN_TOKEN` | `AUTH_TOKEN` + IP allowlist |
| 路由数据 | YAML provider + `HEALTH` 内存/JSON 文件 | DB 表：sites/accounts/tokens/routes/channels/keys/logs |
| 健康核心 | provider/model/kind 健康矩阵 | 通道冷却、站点健康倍率、模型可用性表、endpoint runtime memory |
| 探活粒度 | provider + actual model + `chat/responses` | account/token + model，channel 恢复，endpoint 类型记忆 |
| 转发校验 | adapter gate、请求 shape、输出观测、工具调用观测、Responses shape 确认 | downstream policy、route/channel eligibility、endpoint fallback、empty output detection、proxy log/billing |
| 协议适配 | Chat/Responses/Anthropic/Codex 兼容集中在 Python 单文件 | transformer/surface/provider profile 分层，覆盖 Chat/Responses/Claude/Gemini/Codex/文件/图片/视频等 |
| 成功判定 | 2xx 之外必须有可观测输出或工具调用 | 2xx 后用 transformer/`detectProxyFailure` 判空；是否启用空内容失败由配置控制 |

## 1. AiSmartGateway 文件覆盖清单

以下按 Git 跟踪文件覆盖。`.test_deps/`、`.venv/`、`data/`、`backups/` 属于本机测试依赖、运行状态或备份，不是产品源码；其中 `data/health_state.json` 和 `data/request_logs.jsonl` 是运行时状态/日志，代码会读写它们，但不作为源码审计对象。

| 文件 | 行数 | 角色 |
|---|---:|---|
| `README.md` | 106 | 部署与使用入口，说明 New API + Smart Gateway 组合 |
| `.env.example` | - | 环境变量样例 |
| `.gitignore` | - | 忽略规则 |
| `config/gateway.yaml` | 77 | 模型 include/exclude、canonical model、probe body、同步行为等全局策略 |
| `docker-compose.yml` | 55 | New API、Smart Gateway、网络和 volume 编排 |
| `deploy/Caddyfile` | 20 | 反代/前门部署示例 |
| `deploy/ai-smart-gateway-sync-newapi.service` | 10 | systemd 同步服务 |
| `deploy/ai-smart-gateway-sync-newapi.timer` | 10 | systemd 定时同步 |
| `scripts/migrate-env-from-subapi2.sh` | 46 | 旧环境变量迁移辅助 |
| `scripts/verify.sh` | 112 | 本地验证脚本 |
| `scripts/sync-newapi-router.py` | 780 | 从 New API channels 生成 provider 配置，并创建/更新 New API router channel |
| `smart-gateway/Dockerfile` | 20 | Python 服务镜像 |
| `smart-gateway/requirements.txt` | 6 | 运行依赖：FastAPI/Uvicorn/httpx/PyYAML 等 |
| `smart-gateway/requirements-dev.txt` | 5 | 测试依赖 |
| `smart-gateway/app/__init__.py` | 0 | 包标识 |
| `smart-gateway/app/admin_ui.py` | 2618 | 管理后台单页 HTML/JS |
| `smart-gateway/app/main.py` | 5792 | 核心：配置、探活、路由、转发、格式转换、日志、admin API |
| `smart-gateway/tests/test_gateway.py` | 4537 | 主行为测试，覆盖探活、路由、adapter、Responses/Codex、运行时标记等 |
| `smart-gateway/tests/test_sync_newapi_router.py` | 345 | New API 同步脚本测试 |
| `docs/NEWAPI.md` | 647 | New API 集成设计与同步说明 |
| `docs/current-newapi-smart-gateway-boundary.zh-CN.md` | 181 | 当前边界说明：New API 是前门，Smart Gateway 是后置路由 |
| `docs/full-api-gateway-implementation-review.md` | 176 | 实现复盘与风险点 |
| `docs/retrospective-routing-review.zh-CN.md` | 997 | 路由复盘，尤其是 Codex/Responses 兼容教训 |
| `docs/ai-smart-gateway-comprehensive-analysis.md` | 未跟踪 | 本机已有的旧分析草稿，未覆盖 metapi 对比，本文件不覆盖它 |

## 2. AiSmartGateway 主代码地图

`main.py` 是单文件核心，分层如下：

| 行号范围 | 主题 | 关键点 |
|---|---|---|
| `main.py:27-86` | 环境变量和全局状态 | `CONFIG_DIR`、`DATA_DIR`、`STATE_FILE`、`REQUEST_LOG_FILE`、`MASTER_API_KEY`、`ADMIN_TOKEN`、probe TTL、并发、运行时失败确认数、`CONFIG/PROVIDERS/HEALTH/MODEL_CACHE` |
| `main.py:89-236` | 通用工具和请求日志 | 时间、YAML、脱敏、usage 归一、token 估算、JSONL request log |
| `main.py:245-390` | 配置、认证、模型、provider 签名 | env 展开、base URL 规范化、Bearer/admin auth、include/exclude、canonical model、probe target、health key |
| `main.py:394-539` | Responses SSE 事件、probe cooldown、shape fingerprint、状态保留 | `response.*` 事件生成、Responses invalid request 策略、runtime cooling |
| `main.py:539-590` | 状态持久化与配置 reload | `health_state.json` 原子写入；加载 `gateway.yaml` 和 `providers.yaml` |
| `main.py:590-934` | admin/source policy 辅助 | provider 脱敏、New API channel 标签、source policy 更新、概览统计 |
| `main.py:969-1296` | 上游 HTTP 头、客户端 profile、请求 shape、Codex 诊断体 | provider auth 覆盖、代理、Codex/Claude/OpenAI profile、真实请求 shape 摘要 |
| `main.py:1307-1516` | 错误分类、输出质量、probe 内容判断 | `classify_error`、低信号文本、工具循环文本、probe output quality |
| `main.py:1516-2674` | 请求体转换和 adapter gate | Chat/Responses/Anthropic/Codex body 转换、unsafe field gate、partial 默认学习、Codex compat adapter |
| `main.py:2679-3370` | 非流式/流式响应转换 | Chat -> Responses、Responses -> Chat、SSE 聚合、tool call 输出识别 |
| `main.py:3371-3522` | `StreamFormatAdapter` | 流式中完整 SSE event 缓冲、转换、输出/工具调用观测 |
| `main.py:3523-4261` | 模型发现和健康探活 | `/models` 抓取、probe profile、标准 probe、Codex diagnostic、调度和保存 |
| `main.py:4355-4664` | FastAPI startup、health、admin API、models API | 启动加载、后台 probe、管理接口、`/v1/models` |
| `main.py:4687-5059` | 路由候选构造和选择 | header route controls、bucket、shadow/explore、adapter 排序、weighted selection |
| `main.py:5070-5239` | 运行时状态回写 | runtime failure、Responses shape invalid、tool support、runtime success |
| `main.py:5239-5760` | 转发核心 | `relay_non_stream`、`relay_stream`、请求日志字段、body normalize |
| `main.py:5761-5792` | 公开路由 | `/v1/chat/completions`、`/v1` POST alias、`/v1/responses`、fallback 404 |

`admin_ui.py` 是内嵌管理前端，不参与请求转发本身，但完整展示和操作上述状态：overview、model availability、probe matrix、source policy、request logs、manual reload/sync。它依赖 `main.py` 的 admin API。

`scripts/sync-newapi-router.py` 是 New API 集成核心：读取 New API SQLite channels，将带 `gateway-source` group/tag 的源渠道写成 Smart Gateway providers，再创建/更新名为 `Smart Gateway Router` 的 New API channel，base URL 指向 `http://smart-gateway:8000`，key 为 `MASTER_API_KEY`。

## 3. AiSmartGateway 健康检查完整链路

### 3.1 状态结构

健康矩阵是：

```text
HEALTH = {
  "chat": {
    local_model: {
      "provider_id::actual_model": health_item
    }
  },
  "responses": {
    local_model: {
      "provider_id::actual_model": health_item
    }
  }
}
```

`health_item` 至少围绕这些字段工作：

| 字段 | 含义 |
|---|---|
| `provider_id` | 上游 provider |
| `local_model` | 对外暴露/匹配的模型名 |
| `actual_model` | 上游真实模型名 |
| `kind` | `chat` 或 `responses` |
| `healthy` | 当前可路由健康状态 |
| `reason` | 最近探测/运行时原因 |
| `checked_at` / `next_probe_at` | 最近探测和下次允许探测 |
| `latency_ms` | 探测延迟 |
| `priority` / `weight` / `route_group` / `cost_tier` | 路由排序输入 |
| `provider_signature` | provider 关键配置签名，变更后重新探测 |
| `probe_profile` / `request_format` / `probe_strategy_version` | 哪种 profile/协议探测成功 |
| `responses_compat_mode` / `shape_status` | Responses/Codex shape 兼容证据 |
| `runtime_failure_count` / `runtime_failure_reason` | 真实请求失败反馈 |
| `responses_shape_invalid_count` / fingerprint | 真实 Responses 请求 shape invalid 确认 |
| `tool_call_support` | 工具调用是否验证/不支持 |

状态从 `DATA_DIR/health_state.json` 读取和保存，保存路径由 `STATE_FILE` 定义。写入是 `.tmp` 后替换，避免半写。

### 3.2 配置加载

启动时 `startup_event()`：

1. 创建 `DATA_DIR`。
2. `load_state()` 恢复 `HEALTH`、`MODEL_CACHE`、`LAST_PROBE_AT`。
3. `reload_config()` 读取 `config/gateway.yaml` 和 `config/providers.yaml`。
4. 如果 `PROBE_ON_STARTUP=true`，创建后台 `probe_loop()`。

`reload_config()` 的关键行为：

1. `gateway.yaml` 进入 `CONFIG`。
2. `providers.yaml` 中 `${ENV}` 被展开。
3. 每个 provider 规范化：
   - `base_url`/`base_urls` 去重、补 `/v1`；
   - 跳过 `enabled=false`、缺 `base_url` 或缺 `api_key` 的 provider；
   - 带上 `priority`、`weight`、`timeout_seconds`、headers、proxy、route group、cost tier、fallback flags；
   - 形成 `PROVIDERS`。

### 3.3 模型发现

模型候选来源：

1. 上游 `/models` 返回。
2. provider 的 `declared_models`。
3. provider 的 `model_map`。
4. `CONFIG.canonical_models`。
5. `CONFIG.model_include` / `CONFIG.model_exclude` 最后过滤。

关键点：`/models` 是“发现提示”，不是最终真相；真实可用性由 probe 和运行时反馈确认。

`fetch_models()` 会对每个 provider 的 base URL 尝试多个 client profile：configured/default/codex/claude-cli/claude-code。成功且返回非空就缓存；失败时回旧缓存或空列表。缓存签名包含 provider 关键配置和 probe 策略版本。

### 3.4 probe 调度

`probe_loop()` 每 `PROBE_INTERVAL_SECONDS` 调 `probe_all()`；`probe_all()` 用 `PROBE_RUN_LOCK` 防止并发重入；实际工作在 `probe_all_once(force=False)`。

`probe_all_once()` 的完整步骤：

1. `reload_config()` 保证 provider 和全局策略最新。
2. 深拷贝旧 `HEALTH`。
3. 对每个 provider 调 `get_models_for_provider()`。
4. `build_probe_targets()` 生成 `(local_model, actual_model)`。
5. 对每个 target 建 `chat` 和 `responses` 两类候选；如果 `ENABLE_RESPONSES_PROBE=false` 跳过 responses。
6. 根据旧状态判断是否 due：
   - `force=true`；
   - 没有历史；
   - provider signature 变了；
   - `next_probe_at <= now()`；
   - 运行时失败需要复核。
7. `probe_candidate_sort_key()` 排序：
   - 运行时失败优先；
   - 未探测优先；
   - due 优先；
   - 同级再按 `priority`、`weight`。
8. 非 force 时最多调度 `PROBE_MAX_PER_CYCLE` 个 due probe。
9. 并发由 `PROBE_CONCURRENCY` 控制。
10. `resolve_probe_candidate()` 决定执行 probe 还是保留旧状态。
11. 结果合并回 `new_health`。
12. 更新 `HEALTH`、`LAST_PROBE_AT`，并 `save_state()`。

### 3.5 单个 probe 如何判定

`probe_one(provider, local_model, actual_model, kind)`：

1. 读取 `CONFIG.probe[kind]`，可配置禁用。
2. `probe_attempts_for_kind()` 构造 attempt 列表。
3. 对每个 attempt 依次执行。
4. 成功则立即返回健康 item。
5. 全失败则返回最后一次失败结果，并设置 cooldown。

Chat attempt 主要包括：

| profile | 用途 |
|---|---|
| `chat/openai/default` | 标准 OpenAI Chat |
| `chat/openai/codex` | Codex 风格 header |
| `chat/anthropic/default` | Anthropic Messages body |
| `chat/anthropic/claude-cli` | Claude CLI 风格 |
| `chat/anthropic/claude-code` | Claude Code 风格 |

Responses attempt 主要包括：

| profile | 用途 |
|---|---|
| `responses/openai/default` | 标准 OpenAI Responses |
| `responses/openai/codex` | Codex 风格 header |
| `responses/codex/diagnostic` | Codex shape 诊断，带 reasoning/tools/prompt cache metadata 等 |

标准 HTTP probe：

1. 构造简短请求体，默认要求模型回答可验证文本。
2. 对 `/chat/completions` 或 `/responses` POST。
3. 检查 HTTP 状态。
4. 检查 JSON/error envelope。
5. 提取输出文本。
6. `probe_content_quality_result()` 打分，默认 `PROBE_CONTENT_QUALITY_CHECK=true`，阈值 `PROBE_MIN_QUALITY_SCORE=80`。
7. 低信号文本如 `ok`、`pong` 等不会被当成稳定可用。
8. 如果 Responses 报缺 `partial`，`learn_responses_partial_default()` 学习该 provider 需要 `partial = stream_bool`，并重试。

Codex shape diagnostic：

1. 构造 `codex_shape_diagnostic_body()`，不是简单 ping。
2. 使用 Codex 相关 headers。
3. 按 SSE/Responses 输出分析事件。
4. 成功会写入 Codex/Responses shape 兼容证据，供后续转发时 `chat -> codex responses` adapter 使用。

### 3.6 cooldown 与错误分类

`classify_error(status_code, text)` 将错误归类，`probe_cooldown_seconds(reason, healthy)` 决定下一次探测时间。

| 原因 | 默认冷却 |
|---|---:|
| 成功 | 21600 秒 |
| `responses_request_shape_unverified` | 60 秒 |
| `responses_real_shape_invalid` | 1800 秒 |
| `model_unsupported` / `not_found` | 86400 秒 |
| `auth_or_forbidden` / `provider_config_error` | 3600 秒 |
| `quota` | 3600 秒 |
| `rate_limited` | 1800 秒 |
| `server_unavailable` / `empty_stream` | 900 秒 |
| `empty_response` / `low_signal_response` | 900 秒 |
| `exception:*` | 900 秒 |
| 其他未知 | 1800 秒 |

错误分类覆盖：

| 分类 | 典型触发 |
|---|---|
| `quota` | quota/balance/insufficient/额度/余额 |
| `client_restricted` | unsupported client、仅支持 Codex/Claude 等 |
| `model_unsupported` | unsupported model、no such model、no available channel |
| `provider_config_error` | price not configured、价格未配置 |
| `client_invalid_input` | 明确是客户端请求字段错误 |
| `invalid_request` | invalid codex request、missing partial、invalid responses shape |
| `html_or_cloudflare` | HTML/Cloudflare |
| `auth_or_forbidden` | 401/403 |
| `not_found` | 404 |
| `rate_limited` | 429/rate limit |
| `server_unavailable` | 5xx |

### 3.7 运行时健康反馈

真实转发不是只依赖后台探活。`relay_non_stream()` 和 `relay_stream()` 会把真实请求结果回写到同一 `HEALTH`。

成功路径调用 `mark_runtime_success()`：

1. 清除 `runtime_failure_*`。
2. 清除 shape invalid 计数。
3. 标记 `healthy=true`。
4. 写 `last_runtime_success_at`。
5. 刷新 `next_probe_at = now + PROBE_SUCCESS_TTL_SECONDS`。
6. 如果看到工具调用，`mark_tool_call_support(..., "verified")`。
7. 如果是 Codex compat adapter 成功，记录 `responses_compat_mode=codex` 等证据。

失败路径：

1. `mark_runtime_failure(kind, model, provider_id, reason)`。
2. 对 transient 失败，如 `server_unavailable`、`empty_stream`、`empty_response`、`all_endpoints_failed`、`exception:*`，如果当前还健康，需要 `RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS` 次确认，默认 2 次，才真正打不健康。
3. 对非 transient 失败，立即进入 cooldown。
4. 对真实 Responses shape invalid，走 `mark_responses_shape_invalid_attempt()`；默认同一 request shape 需要 3 次确认才标记 `runtime_failure:real_shape_invalid`，确认前保留健康/未验证状态，避免一次客户端怪请求把 provider 打死。
5. 工具循环文本会把 `tool_call_support` 标成 `unsupported`，真实工具调用则标成 `verified`。
6. 如果真实请求返回 `model_unsupported` 或 `not_found`，且命中的健康项来源是上游 `/models` 发现的 `upstream_models`，会把该 provider 的 `MODEL_CACHE.next_refresh_at` 置 0，促使后续重新拉取模型列表。

## 4. AiSmartGateway 转发校验完整链路

### 4.1 入口与认证

公开 API：

| 路由 | 行为 |
|---|---|
| `GET /health` | 服务存活，不需要 master key |
| `GET /v1/models` | 返回当前健康模型，需要 `MASTER_API_KEY` |
| `GET /v1` | `/v1/models` alias |
| `POST /v1/chat/completions` | Chat 转发 |
| `POST /v1` | Chat alias |
| `POST /v1/responses` | Responses 转发 |
| fallback | 404 JSON |

`auth_ok()` 只接受 `Authorization: Bearer <MASTER_API_KEY>`。Smart Gateway 不保留客户端原始 auth；转发上游时 `provider_headers()` 会用 provider 的 `api_key` 生成新 Authorization。

Admin API 使用 `ADMIN_TOKEN`，支持 `Authorization: Bearer` 或 `x-admin-token`。

### 4.2 路由控制头

`request_route_controls()` 支持：

| header | 用途 |
|---|---|
| `x-gateway-provider` | 强制 provider id |
| `x-gateway-route-group` | 限定路由组 |
| `x-gateway-allow-paid` | 是否允许付费兜底 |

这些控制只影响候选过滤，不会绕过健康、adapter gate、输出校验。

### 4.3 候选桶

`adaptive_candidate_buckets(model, kind, body, controls)` 是路由核心：

1. 先看客户端请求 kind 的原生上游。
2. 再看另一种 kind 的 adapter 上游。
3. 每个 kind 调 `healthy_candidate_buckets()`。
4. 按 provider/header controls 过滤。
5. 按健康与 route group 分桶。
6. 可加入 `probe_retry`、`explore`、`shadow`、`paid_fallback`。
7. `explore` 默认由 `ROUTE_EXPLORATION_RATE=0.15` 控制，且默认每次最多 `ROUTE_EXPLORATION_MAX_CANDIDATES=1` 个；如果请求指定 provider 或 route group，则不做随机探索。
8. `route_item_format_adapter_allowed()` 做格式安全 gate。
9. `annotate_route_item()` 标记 `_upstream_kind`、`_format_adapter`、adapter latency penalty。
10. native 候选优先于 adapter。
11. 按 `ROUTE_BUCKET_ORDER` 排序：

```text
primary -> backup -> other -> probe_retry -> explore -> shadow -> paid_fallback
```

每个桶内 `sorted_route_bucket()` 使用：

```text
priority 越大越优先
score = weight * (1000 / adjusted_latency_ms)
adapter 会有 latency penalty
```

最终 `select_route_candidate()` 从第一个非空桶选；同一 priority 内按 score/weight 加权随机。

### 4.4 格式 adapter gate

转发前不会盲目互转。关键 gate：

| 方向 | 函数 | 主要规则 |
|---|---|---|
| Responses client -> Chat upstream | `responses_body_can_use_chat_adapter()` | 遇到 Responses-only/高风险字段拒绝 |
| Chat client -> Responses upstream | `chat_body_can_use_responses_adapter()` | 遇到 Chat-only/不确定字段拒绝 |
| Chat client -> Codex Responses upstream | `chat_body_can_use_codex_compat_responses_adapter()` | 更严格；只有有 Codex shape 证据才允许 |
| Native Chat | `chat_body_can_use_native_chat_upstream()` | 基础 Chat 兼容性 |

因此“有健康上游”不等于“一定可用于当前请求”。当前请求体的 shape 会参与路由。

### 4.5 上游请求体准备

`prepare_upstream_body(body, chosen, client_kind)`：

| 场景 | 行为 |
|---|---|
| Chat -> Chat | `chat_body_to_chat_upstream_body()`，规范 messages/tools/tool_choice |
| Chat -> Anthropic Chat | `anthropic_chat_body_from_openai_chat_body()`，转换 system/messages/tools |
| Chat -> Responses | `chat_body_to_responses_body()` |
| Chat -> Codex compat Responses | `chat_body_to_codex_compat_responses_body()`，补 Codex 兼容字段 |
| Responses -> Responses | `normalize_responses_upstream_body()`，补 provider defaults、partial |
| Responses -> Chat | `responses_body_to_chat_body()` |

`request_shape()` 会摘要真实请求形态，写入日志和 shape invalid fingerprint；它不是完整保存敏感原文。

### 4.6 上游请求头准备

`upstream_request_headers()` / `provider_headers()` 的安全边界：

1. 上游 Authorization 总是 provider API key，不复用客户端 key。
2. 只透传少量白名单 header。
3. 根据 profile 添加 Codex/Claude/Anthropic header。
4. 支持 provider 自定义 headers。
5. 支持 proxy URL。

### 4.7 非流式成功路径

`relay_non_stream()` 关键步骤：

1. 生成 `request_id`。
2. JSON body 解析后确认 `model`。
3. 解析 route controls。
4. 计算 `client_kind`：chat 或 responses。
5. `adaptive_candidate_buckets()` 构造候选。
6. `total_candidates` 为 0 则 503。
7. `attempts = min(MAX_RETRIES_PER_REQUEST, total_candidates)`。
8. 每次尝试：
   - 选一个候选；
   - 从所有 bucket 移除同一 `(provider, actual_model, upstream_kind)`；
   - 找 provider；
   - 确定 upstream kind 和 path；
   - 准备 body/headers；
   - 对 provider 的多个 base URL 逐个尝试；
   - 处理 partial/Codex compat 重试；
   - 读取响应。
9. 2xx 后仍要做输出校验：
   - JSON 或 SSE 聚合；
   - `response_data_has_output()` 或工具调用；
   - 空输出/工具循环不会当成功。
10. 需要时 `convert_upstream_response_for_client()` 转回客户端协议。
11. `mark_runtime_success()`。
12. `append_request_log()` 写 JSONL。
13. 返回客户端。

### 4.8 流式成功路径

`relay_stream()` 与非流式共享路由和请求准备，差异：

1. 用 `client.stream("POST", ...)`。
2. 上游 chunk 进入 `StreamFormatAdapter.feed()`。
3. Adapter 用 `pop_complete_sse_events()` 保证只处理完整 SSE event。
4. Native 时也会观察输出和工具调用。
5. 跨协议时：
   - Chat SSE -> Responses SSE；
   - Responses SSE -> Chat SSE；
   - 必要时合成 `response.completed` 或 `[DONE]`。
6. 流已经开始后，不能重新发 HTTP 错误；只能发送 error event / `[DONE]`。
7. 流结束后仍检查是否有 output；空流会 `mark_runtime_failure(..., "empty_stream")`。
8. 成功后调用 `mark_runtime_success()` 并写 request log。

## 5. 一个请求从进入到成功：Chat 示例

以 `POST /v1/chat/completions` 非流式为例：

1. 客户端通常先请求 New API。
2. New API router channel 将请求转给 Smart Gateway：`http://smart-gateway:8000/v1/chat/completions`。
3. Smart Gateway 读取 `Authorization`。
4. `auth_ok()` 校验 `MASTER_API_KEY`。
5. 读取 JSON body。
6. 确认 `model` 存在。
7. 读取 `x-gateway-*` route controls。
8. `adaptive_candidate_buckets(model, "chat", body, controls)`。
9. 在 `HEALTH["chat"][model]` 找原生 Chat 健康项。
10. 在 `HEALTH["responses"][model]` 找可 adapter 的 Responses 健康项。
11. 过滤 provider、route group、paid fallback。
12. 检查 adapter 是否能承载当前 body。
13. 按 bucket/native/adapter/priority/score 排序。
14. `select_route_candidate()` 选中一个候选。
15. 记录 attempted key，防止同一上游重复尝试。
16. 找到 provider 配置。
17. 如果是 Chat native，构造 Chat upstream body；如果 provider `chat_request_format=anthropic`，转为 Anthropic body。
18. 如果是 Chat -> Responses，构造 Responses body；如果是 Codex compat，构造 Codex 兼容 Responses body。
19. `upstream_request_headers()` 设置 provider key 和 profile headers。
20. 对 provider `base_urls` 逐个 POST。
21. 如果上游报 missing partial，学习 partial 默认并重试。
22. 如果 Chat -> Responses 普通 adapter 失败且满足条件，启用 Codex compat adapter 再试。
23. 上游返回 2xx。
24. 读取 JSON 或聚合 SSE。
25. `detect/output` 判断必须有文本、refusal 或 tool call。
26. 如果上游协议不同，转换回 Chat response。
27. `mark_runtime_success("chat", model, provider_id, ...)`。
28. 如有工具调用，`tool_call_support=verified`。
29. 写 `request_logs.jsonl`。
30. 返回 New API。
31. New API 再返回给最终客户端。

## 6. 一个请求从进入到成功：Responses 示例

以 `POST /v1/responses` 流式为例：

1. New API 或客户端转入 `/v1/responses`。
2. `auth_ok()` 校验 `MASTER_API_KEY`。
3. body 中 `model` 必须存在。
4. 计算 route controls。
5. `adaptive_candidate_buckets(model, "responses", body, controls)`。
6. 优先 Responses native；再考虑 Chat adapter。
7. 如果当前请求含 Responses-only 字段，Chat adapter gate 会拒绝。
8. 如果选到 Responses native，`normalize_responses_upstream_body()` 处理 defaults/partial。
9. 如果选到 Chat adapter，`responses_body_to_chat_body()` 转成 Chat。
10. 构造上游 headers，provider key 覆盖客户端 auth。
11. 发起流式请求。
12. `StreamFormatAdapter` 处理 SSE。
13. Native Responses 直接透传并观察 output/tool call。
14. Chat adapter 则把 Chat chunks 转成 Responses events。
15. 如果需要，合成 completed event。
16. 流结束后确认有输出。
17. `mark_runtime_success("responses", ...)`。
18. 如果 shape 由 Codex 兼容 adapter 证明，记录 compat 证据。
19. 写 request log。
20. 返回流结束。

## 7. AiSmartGateway docs 对照

### 7.1 与代码一致的结论

| 文档 | 与代码一致之处 |
|---|---|
| `README.md` | Smart Gateway 位于 New API 之后，提供 `/v1/models`、Chat、Responses；同步脚本维护 New API router channel |
| `docs/NEWAPI.md` | `gateway-source` source channel、`Smart Gateway Router` router channel、`MASTER_API_KEY`、New API abilities/models/ModelRatio 同步方向与脚本一致 |
| `docs/current-newapi-smart-gateway-boundary.zh-CN.md` | 明确 New API 是前门，Smart Gateway 不做用户/计费/分组；代码也只校验 master key，不持有用户体系 |
| `docs/full-api-gateway-implementation-review.md` | 指出健康、Responses shape、运行时反馈、输出校验是核心风险面；代码确实围绕这些点加强 |
| `docs/retrospective-routing-review.zh-CN.md` | 对 Codex/Responses 兼容、真实 shape、工具调用和路由复盘的描述与代码方向一致 |

### 7.2 需要精确化的点

1. 文档里多处把“真实 Codex 模板/抓包模板”作为理想方向或复盘经验；当前代码实现的是合成的 `codex_shape_diagnostic_body()` 加运行时 fingerprint/确认机制，没有持久化“捕获到的真实模板库”。
2. `/models` 在文档中容易被理解为可用性真相；代码里它只是候选发现，最终由 probe + runtime success/failure 决定。
3. Source channel models 不会被脚本按健康结果回写裁剪；`sync_source_channel_models()` 明确返回 0，New API source channel 的 models 是 operator declaration。
4. 已有未跟踪 `docs/ai-smart-gateway-comprehensive-analysis.md` 对健康和转发已有概览，但没有覆盖完整文件清单、真实成功链路、docs-vs-code 差异和 metapi 对比。

## 8. metapi 项目结构与请求链路

metapi 当前 Git 跟踪文件约 1133 个，明显大于 AiSmartGateway。核心读到的文件：

| 文件 | 行数 | 角色 |
|---|---:|---|
| `src/server/index.ts` | 308 | 服务启动、DB 初始化、runtime settings、route rebuild、scheduler、API/proxy route 注册 |
| `src/server/middleware/auth.ts` | 192 | admin auth、proxy auth、托管下游 key |
| `src/server/routes/proxy/router.ts` | 25 | 所有 `/v1/*` 代理路由挂载 `proxyAuthMiddleware` |
| `src/server/routes/proxy/chat.ts` | 19 | Chat/Claude route 薄入口 |
| `src/server/routes/proxy/responses.ts` | 68 | Responses/compact/WebSocket route 薄入口 |
| `src/server/routes/proxy/models.ts` | 21 | `/v1/models` |
| `src/server/proxy-core/surfaces/chatSurface.ts` | 1512 | Chat/Claude 请求完整代理 surface |
| `src/server/proxy-core/surfaces/openAiResponsesSurface.ts` | 1427 | Responses/compact/Codex session 请求完整代理 surface |
| `src/server/proxy-core/surfaces/sharedSurface.ts` | 749 | 通用选通道、sticky/lease、日志、成功/失败工具 |
| `src/server/services/tokenRouter.ts` | 3806 | route/channel 选择、冷却、运行时健康倍率、成功/失败回写 |
| `src/server/services/modelAvailabilityProbeService.ts` | 447 | 后台模型可用性探测 |
| `src/server/services/channelRecoveryProbeService.ts` | 299 | 冷却/活跃通道恢复探测 |
| `src/server/services/runtimeModelProbe.ts` | 236 | 真实轻量模型 probe |
| `src/server/services/proxyFailureJudge.ts` | 203 | 2xx 后空输出/错误关键词判失败 |
| `src/server/services/proxyRetryPolicy.ts` | 103 | 是否跨通道重试、是否终止 endpoint fallback |
| `src/server/services/siteApiEndpointService.ts` | 296 | 一个站点多个 API endpoint 的选择、5 分钟冷却和轮换 |
| `src/server/services/upstreamEndpointDerivation.ts` | 约 300 | chat/messages/responses endpoint 候选推导 |
| `src/server/services/upstreamRequestBuilder.ts` | 约 830 | 上游请求体/请求头构造 |
| `src/server/services/upstreamEndpointRuntimeMemory.ts` | 432 | endpoint 成功/失败记忆，6h block、24h preferred |
| `src/server/db/schema.ts` | 559 | sites/accounts/tokens/routes/channels/logs/usage/downstream keys schema |

### 8.1 metapi 启动

`src/server/index.ts`：

1. `ensureRuntimeDatabaseReady()` 初始化 runtime DB。
2. 从 `settings` 读取运行时 DB 和其他设置，可切 SQLite/MySQL/Postgres。
3. 补兼容列：site、route grouping、proxy file/log 等。
4. `applyRuntimeSettings()` 应用 DB 中的设置覆盖。
5. 修复时间、迁移 site API key 到 account、seed 默认站点、OAuth identity backfill。
6. `routeRefreshWorkflow.rebuildRoutesOnly()` 启动时重建路由。
7. 注册 `/api/*` 管理接口，非 public API 走 `authMiddleware`。
8. 注册 `proxyRoutes()`，所有 `/v1/*` 走 `proxyAuthMiddleware`。
9. 启动 scheduler：
   - checkin；
   - backup；
   - site announcement；
   - model availability probe；
   - channel recovery probe；
   - sub2api refresh；
   - update center；
   - usage aggregation；
   - admin snapshot warm；
   - OAuth callback servers；
   - proxy file/log retention。

### 8.2 metapi 公共鉴权

`proxyAuthMiddleware()` 支持：

1. `Authorization: Bearer <token>`。
2. `x-api-key`。
3. `x-goog-api-key`。
4. `?key=`。

`authorizeDownstreamToken()` 返回 global token 或托管下游 API Key。托管 key 会带 policy：模型白名单、route 白名单、站点倍率、排除站点、排除 credential、用量/费用限制等。

### 8.3 metapi 路由选择

`tokenRouter.selectChannel()`：

1. 先用 downstream policy 判断模型是否允许。
2. 加载/恢复站点运行时健康状态。
3. `findRoute()` 在 enabled `token_routes` 中匹配：
   - explicit group display name；
   - exact model；
   - display name；
   - pattern/regex。
4. `loadRouteMatch()` 读 `route_channels`，join accounts/sites/account_tokens，并加载 OAuth route unit members。
5. `getCandidateEligibilityReasons()` 过滤：
   - source model 不匹配；
   - channel disabled；
   - account status；
   - site disabled；
   - downstream key 排除；
   - 当前请求已尝试；
   - token 不可用；
   - cooldown 中。
6. 根据 route strategy 选择：
   - `round_robin`：按 last selected/used 排序，不看 priority；
   - `stable_first`：按近期成功率/历史健康分主池和观察池，少量真实请求灰度观察池；
   - `weighted`：按 priority 分层，同层加权随机。
7. 加权输入包括：
   - channel weight；
   - cost/balance/usage；
   - site global weight；
   - downstream site multiplier；
   - runtime health multiplier；
   - historical health multiplier；
   - channel session load multiplier；
   - 同站点多通道贡献拆分。
8. `finalizeSelectedCandidateForDispatch()` 解析实际 token、actual model、记录 `lastSelectedAt`，OAuth route unit 还会选 member。

### 8.4 metapi 转发成功链路

以 `POST /v1/chat/completions` 为例：

1. `proxyRoutes()` 的 onRequest 调 `proxyAuthMiddleware()`。
2. `chatProxyRoute()` 调 `handleChatSurfaceRequest()`。
3. transformer 解析下游 body；失败直接返回 4xx。
4. `ensureModelAllowedForDownstreamKey()` 检查托管 key policy。
5. 解析 downstream policy、forced channel、client context。
6. 解析文件引用，生成 OpenAI 兼容中间 body。
7. 创建 failure toolkit、sticky session key、debug trace。
8. 在 `while retryCount <= maxRetries` 内选通道：
   - sticky preferred；
   - forced channel；
   - normal select；
   - 首次无通道会尝试 `refreshModelsAndRebuildRoutes()` 后再选。
9. `resolveUpstreamEndpointCandidates()` 生成 endpoint 候选：`chat`、`messages`、`responses`，受平台、模型、文件、reasoning、pricing catalog 和 runtime memory 影响。
10. `buildUpstreamEndpointRequest()` 按 endpoint 和平台构造请求：
   - 阻断下游 Authorization/x-api-key/cookie 等敏感头；
   - 透传白名单；
   - 用选中 channel/account/token 生成 provider auth；
   - OpenAI/Responses/Anthropic/Gemini/Codex/Claude provider profile 分别处理。
11. `executeEndpointFlow()` 在同一 site API base URL 内尝试 endpoint 候选。
12. 401/403 可触发 OAuth token refresh recovery。
13. endpoint 失败会写 endpoint runtime memory：某 endpoint block 6h，成功 endpoint preferred 24h。
14. `runWithSiteApiEndpointPool()` 支持一个 site 下多个 API endpoint；retryable endpoint 失败冷却 5 分钟并轮到下一个 endpoint。
15. 取得 2xx upstream。
16. 流式：
   - SSE hijack；
   - transformer proxy stream 转换；
   - 解析 usage；
   - 流已开始后不跨通道重试。
17. 非流式：
   - 读取文本；
   - JSON/SSE final payload 解析；
   - `detectProxyFailure()` 判空输出或错误关键词；
   - transformer 转回下游格式。
18. `recordSurfaceSuccess()`：
   - usage self-log fallback；
   - billing；
   - `tokenRouter.recordSuccess()`；
   - 托管 downstream key cost usage；
   - `proxy_logs`；
   - OAuth quota headers snapshot。
19. 绑定 sticky channel。
20. 返回客户端。

### 8.5 metapi 健康和冷却

metapi 的健康分多层：

1. **通道冷却**：`route_channels.cooldown_until`、`fail_count`、`consecutive_fail_count`、`cooldown_level`。
2. **OAuth route unit member 冷却**：同样字段在 `oauth_route_unit_members`。
3. **站点运行时健康倍率**：`tokenRouter_site_runtime_health_v1` 存在 `settings`，包括 penalty、latency EMA、recent success/failure、breaker。
4. **模型可用性表**：`model_availability` 和 `token_model_availability`。
5. **endpoint runtime memory**：同站点/模型/能力下 chat/messages/responses 的 preferred/block 状态。
6. **site API endpoint 冷却**：一个站点可有多个 endpoint，失败后 endpoint 自己冷却。

代码中的具体冷却：

| 类型 | 规则 |
|---|---|
| weighted/stable route channel | Fibonacci backoff：15s、15s、30s、45s...，受 `TOKEN_ROUTER_FAILURE_COOLDOWN_MAX_SEC` 上限限制 |
| round-robin route channel | 连续失败 3 次后升级，默认 10 分钟、1 小时、24 小时 |
| usage-limit rate limit | 解析 quota reset hint；没有 hint 时默认 5 分钟 |
| site runtime breaker | transient failure 5 分钟窗口内 3 次触发，1 分钟、5 分钟、30 分钟 |
| site API endpoint | retryable 失败后 5 分钟 |
| endpoint runtime memory | endpoint block 6 小时，success preferred 24 小时 |
| channel recovery probe | 每 30 秒 sweep，最多 4 个，串行 probe，冷却 channel 30 秒可复查，active channel 5 分钟复查 |
| model availability probe | 默认关闭；开启后默认 30 分钟 interval、15 秒 timeout、并发 1 |

`docs/operations.md` 中“通道失败后自动冷却 10 分钟”是运维简化描述；代码实际如上更细。

## 9. AiSmartGateway 与 metapi 深度对比

### 9.1 架构边界

AiSmartGateway 假定 New API 已经解决：

1. 用户认证。
2. 用户余额和计费。
3. 分组/渠道前门。
4. 外部客户端兼容。

所以 AiSmartGateway 可以把复杂度集中到：

1. 上游健康。
2. 模型和协议兼容。
3. 路由选择。
4. 真实失败回写。
5. New API router channel 同步。

metapi 不依赖 New API 作为前门。它自己管理：

1. 下游 API Key。
2. 上游站点和账号。
3. token 同步/刷新。
4. 模型发现和路由生成。
5. 计费、日志、统计。
6. 管理 UI 和桌面端。

### 9.2 健康检查对比

| 问题 | AiSmartGateway | metapi |
|---|---|---|
| “这个模型能不能用？” | provider/model/kind probe 给出明确健康矩阵 | model availability 表 + route/channel availability + runtime feedback |
| “真实请求失败怎么办？” | 写回 `HEALTH`，可能改变路由；transient 需确认 | `recordFailure()` 更新 channel/member cooldown、site health penalty、proxy log |
| “协议不兼容怎么办？” | Responses shape 诊断、request shape fingerprint、adapter gate | endpoint candidates + runtime memory，失败后 block endpoint，成功后 preferred |
| “空响应怎么办？” | 默认强制输出质量/输出观测；空输出失败 | `PROXY_EMPTY_CONTENT_FAIL` 默认 false；开启后判空 |
| “恢复怎么做？” | 后台 probe 到期后复查；runtime success 也恢复 | channel recovery probe、model availability probe、runtime success、route rebuild |
| “状态放哪里？” | JSON 文件 + 内存 | DB + settings + 内存 runtime memory |

AiSmartGateway 的健康更“模型矩阵化”，适合少量专注上游后置路由。metapi 的健康更“平台运营化”，适合多站点、多账号、多租户和长时间运行。

### 9.3 转发校验对比

| 校验环节 | AiSmartGateway | metapi |
|---|---|---|
| 下游鉴权 | 单 master key | global proxy token + managed downstream keys |
| 模型权限 | 依赖 New API；内部只按健康暴露 | downstream key 支持模型白名单/route 白名单 |
| 路由过滤 | provider/header controls、route group、paid fallback | downstream policy、site/account/channel/token status、cooldown |
| 请求 shape | `request_shape()` + adapter unsafe fields | transformer preflight + provider/request builder |
| 协议转换 | 单文件函数和 `StreamFormatAdapter` | transformers/surfaces/provider profiles |
| 上游 auth | provider `api_key` 覆盖 | selected token/account/OAuth provider headers |
| 成功判定 | 2xx + output/tool call 必须可观测 | 2xx + transformer；可选 empty content failure |
| 失败重试 | bucket 内跨 provider/model 重试，最多 `MAX_RETRIES_PER_REQUEST` | channel retry，默认 `PROXY_MAX_CHANNEL_ATTEMPTS=3` |
| 同站多 endpoint | provider `base_urls` 顺序尝试 | `site_api_endpoints` 可冷却/轮换 |
| 日志 | JSONL request logs | DB `proxy_logs` + debug traces/attempts + usage projections |

### 9.4 协议适配对比

AiSmartGateway 的优点：

1. 所有转换逻辑在一个文件，定位快。
2. Chat/Responses/Codex 关键路径非常集中。
3. 对 Responses shape 和工具调用的失败确认很谨慎。
4. 输出质量默认严格，适合“转发必须真的能答”的网关。

AiSmartGateway 的代价：

1. `main.py` 超过 5700 行，长期维护压力大。
2. 新增协议会继续扩大单文件。
3. 没有 DB 层的多租户策略和审计能力。

metapi 的优点：

1. transformer/provider profile 分层，协议扩展性强。
2. DB schema 能承载账号、token、route、usage、debug。
3. 下游 key policy 和成本/用量控制适合多人使用。
4. endpoint runtime memory 能自动学习同一模型适合 chat/messages/responses 哪个 endpoint。

metapi 的代价：

1. 系统大，部署和运维复杂。
2. 健康状态分散在多个服务/表/内存状态中，排障需要跨文件。
3. 默认空内容失败关闭，若要 AiSmartGateway 式严格转发，需要显式配置。

## 10. 可互相借鉴的点

AiSmartGateway 可以借鉴 metapi：

1. 把单文件拆成 `routing`、`health`、`adapters`、`streaming`、`admin`、`newapi_sync` 模块。
2. 增加 endpoint runtime memory，把“某 provider 的 responses endpoint 不适合该模型”与 provider/model 健康分开。
3. 对 request logs 加 debug attempt 明细，方便复盘每次 fallback。
4. 为 provider base URLs 引入独立 endpoint cooldown，而不是只在一次请求内轮询。

metapi 可以借鉴 AiSmartGateway：

1. 默认开启更严格的 2xx 输出观测，避免“HTTP 成功但空内容”进入 success。
2. 对 Responses real shape invalid 引入按 request fingerprint 的多次确认，减少误伤通道。
3. 对 Codex/Responses 兼容增加更明确的诊断矩阵。
4. 在管理 UI 中增加类似 `HEALTH` 的 per-model/per-endpoint 可读矩阵。

## 11. 最终判断

如果目标是“让 New API 后面的一组上游更聪明、更稳地被路由”，AiSmartGateway 的设计更贴合：小、直接、健康矩阵强、输出校验严格。

如果目标是“替代 New API/One API 做完整聚合平台，并直接面向多个团队/客户端”，metapi 更贴合：账号、token、下游 key、计费、日志和 UI 都已经内建。

两者不完全是同类项目。AiSmartGateway 是 New API 生态里的后置智能路由组件；metapi 是完整的中转站聚合系统。健康检查和转发校验上，AiSmartGateway 更强调“某 provider 的某模型某协议是否真的可用”，metapi 更强调“在多账号、多通道、多协议、多租户环境中持续挑一个当前最合适的通道并计费审计”。
