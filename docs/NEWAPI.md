# New API, Sub2API, and AI Smart Gateway Operations

This is the public, sanitized successor to the older `NEWAPI.txt` deployment
note. It describes the current architecture. It intentionally omits production
domains, real server paths, API keys, tokens, cookies, database paths, request
logs, and private provider details.

## Current Architecture

```text
Client / Codex / OpenAI-compatible tool
  -> New API public endpoint
  -> New API channel: Smart Gateway Router
  -> AI Smart Gateway
  -> authorized upstream providers
```

New API is the public front door. AI Smart Gateway is the downstream routing
engine behind New API. Sub2API is a separate New API-based gateway project and
may be used as an upstream provider or as a reference deployment, but it is not
the public control plane for this project unless the operator explicitly makes
it so.

## Project Roles

### New API

New API owns public management:

- Users, tokens, quota, subscriptions, and groups.
- Public API keys issued to clients.
- User-facing request logs and billing records.
- Channel creation for real upstream credentials.
- Model management, model visibility, and pricing/multiplier settings.

Real upstream channels should be created in New API and tagged
`gateway-source`. The Smart Gateway router itself is also a New API channel,
usually named `Smart Gateway Router`, but it is not a user group.

### AI Smart Gateway

AI Smart Gateway owns downstream routing:

- Sync tagged New API channels into a runtime provider pool.
- Keep model health by API kind: `chat` and `responses`.
- Route by route group, priority, weight, runtime health, and fallback policy.
- Handle multi-base-url providers as one logical provider.
- Cool down repeated unsupported/quota/rate-limit/server failures.
- Log final upstream flow: selected provider, route bucket, model, latency,
  error type, and request shape summary.
- Normalize Responses requests for Codex-like upstreams where safe.

Smart Gateway is not a second user/token/subscription system.

### Sub2API

Sub2API is a separate repository and stack. It provides a New API deployment
with a sidecar for provider probes, optional automation, and backups. In this
architecture it can serve two roles:

- A separate upstream channel that New API or Smart Gateway can call.
- A reference/legacy scaffold for New API operations.

It should not duplicate Smart Gateway's route-level decision making unless an
operator intentionally runs it as another independent gateway.

## Public Client Configuration

Clients should use the New API public endpoint and a New API-issued token:

```text
Base URL: https://api.example.com
API Key: token generated in New API
```

For clients that require `/v1`, the compatibility form may be kept:

```text
Base URL: https://api.example.com/v1
```

Do not distribute Smart Gateway's internal master key to end users. That key is
for the New API router channel and trusted operator checks only.

## Upstream Management Workflow

1. Add the real upstream in New API channel management.
2. Put the upstream's real base URL and credential in New API.
3. Add the channel tag `gateway-source`.
4. Keep the source channel in the normal New API group used for channels.
5. Run the sync script or click the Smart Gateway sync action.
6. Verify the source appears in Smart Gateway's source pool and health views.

The sync script generates Smart Gateway provider config from New API channels.
It must not destructively rewrite source channel model declarations just because
runtime health is currently bad. Runtime health belongs in Smart Gateway state;
operator declarations belong in New API channels.

For known upstreams where credentials are also present in `.env`, the sync
script lets `.env` override the New API channel key for the generated Gateway
provider. This keeps emergency credential rotation simple without editing the
New API source channel first. Current recognized variables are
`UPSTREAM_X666_KEY`, `UPSTREAM_ANYROUTER_KEY`, `UPSTREAM_SHAREDCHAT_KEY`,
`UPSTREAM_MUYUAN_KEY`, `UPSTREAM_EQING_KEY`, and `UPSTREAM_VOLCES_KEY`.

## Source Pool Policy

Provider route groups:

- `primary`: normal preferred upstreams.
- `opportunistic`: low-cost or temporary upstreams that may be unstable.
- `backup`: lower priority but still valid.
- `paid_fallback`: expensive fallback used after other candidates fail.

Cost labels are display/analysis metadata. Actual paid fallback behavior should
be determined by route group/fallback flags, not by the display cost label.

Priority is considered before weight. Weight is used among candidates at the
same effective priority level. Runtime latency can influence ordering inside
the same bucket where implemented, but it must not override the fallback policy.

## Model Discovery

Upstream `/models` is a hint, not truth. Some providers return stale or partial
model lists while still accepting real requests. Some list models that later
fail at runtime.

The current model sources are:

- New API channel-declared models.
- Upstream `/models` when available.
- Canonical aliases and provider model maps.
- Runtime successes discovered from health state.

The public New API model list should be driven by the Smart Gateway router
channel and Smart Gateway's effective availability. Operators can still disable
models in New API model management; sync should respect those manual disables.

The current public model list is additionally constrained by Smart Gateway
`model_include` and `model_exclude`. These filters apply before health exposure
and before the New API router channel ability sync. Current includes are:

```yaml
model_include:
  - deepseek-*
  - gpt-*
  - claude-*
  - doubao-*
  - glm-*
  - grok-*
  - mimo-*
```

Current operational excludes include:

```yaml
model_exclude:
  - "gpt-5.4*"
  - "*-20??????"
```

The first rule temporarily hides `gpt-5.4` variants after clients were observed
requesting cached `gpt-5.4` models while the intended operational model was
`gpt-5.5`. The second hides long date-suffixed models such as
`claude-haiku-4-5-20251001` while keeping shorter aliases such as
`claude-opus-4-8` visible. To re-enable those models, remove the matching
exclude, reload Smart Gateway, and sync the New API router channel again.
`grok-*` was added to the include list on 2026-06-14; Grok models still require
normal health probe success before they are exposed.
The full probe and router sync on 2026-06-14 exposed
`grok-4.20-fast` and `grok-4.20-0309-non-reasoning`. Other discovered Grok
variants stayed hidden because the currently reachable upstreams returned
non-healthy probe results such as rate limiting.

The effective public list is runtime-dependent and should be read from
`/v1/models` after a probe or router sync. After the 2026-06-14 Grok follow-up
probe, the list contained 16 models, including `grok-4.20-fast`,
`grok-4.20-0309-non-reasoning`, `gpt-5.5`, `gpt-5.5-openai-compact`, Claude
short aliases, DeepSeek/GLM, and Mimo variants.

## Health Detection Strategy

Health is tracked by:

```text
API kind -> local model -> provider -> actual upstream model
```

The system distinguishes:

- `ok`: successful probe or runtime request.
- `model_unsupported` / `not_found`: likely wrong model for that upstream.
- `quota`: balance or quota issue.
- `rate_limited`: temporary limit.
- `server_unavailable`: 5xx or upstream gateway failure.
- `auth_or_forbidden`: credential or permission problem.
- `provider_config_error`: upstream New API/provider-side operational config
  is missing, for example `price not configured` / `价格未配置` for a model.
- `empty_response` / `low_signal_response`: HTTP 2xx with no useful model
  text. This prevents a provider that only returns `ok`, `pong`, an empty
  completion, or another low-signal response from being treated as healthy.
- `responses_request_shape_unverified`: the fixed probe or current request
  shape was rejected, but that does not prove the model is unavailable for a
  real Codex-shaped request.

Cooldowns should apply to unsupported models, quota, rate limits, server
errors, auth errors, and exceptions. Responses request-shape failures should be
handled separately because they often mean the probe is weaker than a real
client request.

Default health-loop and cooldown values:

- `PROBE_INTERVAL_SECONDS=60`
- `PROBE_TIMEOUT_SECONDS=12`
- `PROBE_MAX_PER_CYCLE=12`
- `MODELS_REFRESH_SECONDS=3600`
- `HEALTH_FRESH_TTL_SECONDS=300`
- `ADAPTER_SYNTHESIZE_USAGE=true`
- success cache: 21600 seconds
- unsupported/not found: 86400 seconds
- auth/forbidden, provider config error, and quota: 3600 seconds
- rate limited: 1800 seconds
- server unavailable and exceptions: 900 seconds
- empty or low-signal probe output: 900 seconds
- unknown: 1800 seconds
- Responses request-shape retry: 60 seconds
- Responses confirmed real-shape invalid: 1800 seconds

The admin overview API exposes these values as `health_policy`; the operations
UI renders them in the `探测矩阵` help panel so operators can see the live
policy instead of reading code.

Probe content quality is enabled by default. The bundled probe asks for a short
sentence instead of `ping`, then scores the returned text. A successful 2xx
response still fails health if the extracted Chat/Responses text is empty or
below `PROBE_MIN_QUALITY_SCORE`. This check is only for synthetic health
probes; real user requests can still legitimately ask for terse output without
poisoning provider health.

Runtime success also requires observable model output. Smart Gateway no longer
marks a 2xx non-streamed response, an SSE `response.completed`, or a streamed
Chat/Responses request as successful until it has seen text or a tool call. If
the upstream sends only an empty completion, the runtime result is
`empty_response`, the request log is failed, and the provider/model/kind is
cooled down. This prevents clients such as Claude Desktop from seeing a silent
successful completion with no assistant content.

Runtime `server_unavailable`, `empty_stream`, `empty_response`,
`all_endpoints_failed`, and `exception:*` are treated as transient by default.
A healthy item is not removed from routing after the first such runtime failure;
Smart Gateway records a pending `runtime_failure_count` and only marks it unhealthy after
`RUNTIME_TRANSIENT_FAILURE_CONFIRMATIONS` consecutive transient failures
(default `2`). Any runtime success clears the pending counter. Non-transient
failures such as unsupported model, auth, quota, rate limit, and confirmed real
shape invalid still enter cooldown immediately.

Some upstreams return SSE even when the client request is non-streaming. Smart
Gateway now aggregates non-streamed Chat/Responses SSE bodies back into the
expected JSON response before deciding whether output was observed. This avoids
misclassifying a valid Chat SSE response as `empty_response` during
`chat_to_responses` fallback, and prevents a Responses adapter failure from
unnecessarily poisoning the native Chat health item.

Tool-bearing Responses requests have an additional runtime signal. HTTP 200
with plain text is not enough to prove agentic tool support. If a native
Responses stream with `tools` emits no `function_call` and instead returns
tool-loop text such as repeated "correct tool invocation" guidance, Smart
Gateway records `tool_call_support=unsupported` for that provider/model/kind.
Later requests with the same loop history skip unverified or unsupported native
Responses candidates and may try a safely mappable Chat adapter candidate
instead. A real streamed or non-streamed function call records
`tool_call_support=verified`.

`HEALTH_FRESH_TTL_SECONDS` is an operations-facing freshness window. A healthy
item checked inside this window is shown as fresh; a healthy item older than
this window but still inside the success cache is shown as cached/stale health.
Routing can still use cached health, but operators should treat it as less
real-time than a recent runtime success or probe.

## Responses and Codex Compatibility

Codex-like clients usually use `/v1/responses`, stream mode, and a richer body
than a minimal probe. Important fields/headers can include:

- `instructions`
- `store`
- `tools`
- `reasoning`
- `text`
- `metadata`
- `OpenAI-Beta`
- `Originator`
- `Session_id`
- `X-Codex-Beta-Features`
- `X-Codex-Turn-Metadata`
- `X-Stainless-*`
- `User-Agent`

New API's router channel should enable body pass-through and header pass-through
for the Codex/OpenAI headers above. Smart Gateway should preserve those headers
to the upstream while always replacing the upstream authorization with the
provider credential.

Smart Gateway currently normalizes Responses bodies by adding safe defaults
such as `instructions: ""` and `store: false` when absent. It does not invent
large tool lists or hidden Codex metadata.

Some OpenAI-compatible Responses providers may reject requests without
provider-specific optional fields. One observed example is a `MissingParameter`
error for `partial`. Smart Gateway handles this generically: when a Responses
runtime request, minimal probe, or Codex-shape diagnostic gets a clear
missing-`partial` error, it retries once with `partial` inferred from `stream`
and learns that default for the provider for later requests. This is
error-driven compatibility, not a model-specific rule. The learned value is an
in-process compatibility cache; an operator may also set `responses_defaults`
on a provider if the behavior should be explicit after restart.

For upstreams that restrict accepted clients, provider-level headers may be
used to force a compatible client identity. One Claude aggregation provider was
observed returning a client-restricted error when probes looked like
`python-httpx`; the sync script now preserves a provider-specific
Claude Code identity override for that source.

Providers may also set `proxy_url` for upstream-only egress routing. The sync
script injects `proxy_url` for sharedchat from
`GATEWAY_SHAREDCHAT_PROXY_URL`, `SHAREDCHAT_PROXY_URL`,
`GATEWAY_CN_PROXY_URL`, or `CN_PROXY_URL`. This is intentionally provider
scoped: it sends only that upstream's traffic through the proxy and does not
change New API, admin UI, or other provider traffic. The provider signature
includes `proxy_url`, so changing it causes config reloads and fresh probes.

Current Muyuan behavior is stricter than the earlier UA-only workaround. Plain
OpenAI Chat bodies are rejected even with a Claude Code-like UA. The working
shape is Chat path `/chat/completions` with Anthropic/Claude Code-style body
(`system`, Anthropic `messages`, `tools`/`tool_choice` when present) plus
`User-Agent: claude-cli/2.1.133`, `anthropic-version`, and the Claude Code beta
header. Smart Gateway represents this as `chat_request_format: anthropic` on
the provider. This only fixes supported Chat-compatible paths. If the same
provider returns `not implemented` or client restriction for `/responses`, it
remains non-healthy for native Responses.

## Real Codex Shape Verification

Low-cost probes are useful for cheap screening, but they are not authoritative
for Codex/Responses compatibility. A correct verification path must be based on
a real Codex request shape, not on a hand-written minimal `curl` body.

The verified Codex CLI shape from `codex_exec 0.139.0` has these properties:

- `POST /v1/responses`
- streaming SSE response expected through `Accept: text/event-stream`
- large request body, about 38 KB even for a tiny prompt, because Codex sends
  full agent instructions and runtime context
- `instructions` populated with the Codex agent instructions
- `input` as the real Codex conversation payload
- `reasoning` present when reasoning effort is configured
- headers including `Originator: codex_exec`, `User-Agent: codex_exec/...`,
  `Session-Id`, `Thread-Id`, `X-Codex-Beta-Features`, and
  `X-Codex-Turn-Metadata`

This distinction matters. A simplified probe or hand-written JSON body can
return `400 invalid codex request` while the real Codex request shape succeeds.
Therefore:

- Minimal probe failures are only hints.
- Runtime client requests are the strongest evidence.
- Synthetic verification must replay a captured/sanitized Codex-shape template,
  not a small generic Responses body.
- A failed weak runtime shape must not immediately revoke an already healthy
  Codex-compatible provider. Smart Gateway records the request-shape
  fingerprint and confirmation count; only after
  `RESPONSES_INVALID_REQUEST_CONFIRMATIONS` failures for the same fingerprint
  is the provider/model/kind marked `real_shape_invalid`.
- Authorization is always replaced with the provider key; captured user tokens
  must never be stored or replayed.
- Captured verification templates must be stored redacted, bounded in size, and
  versioned by client kind, API kind, and request-shape fingerprint.

The anyrouter incident confirmed this rule. With a captured real Codex request
body/headers and the provider key injected, both configured anyrouter base URLs
returned valid SSE `200 OK` three times:

- `https://anyrouter.top/v1/responses`: 3/3 successful real-shape checks.
- `https://a-ocnfniawgw.cn-shanghai.fcapp.run/v1/responses`: 3/3 successful
  real-shape checks.

## `invalid_request` Handling

The important lesson from the recent anyrouter incident is:

```text
400 invalid_request from a minimal probe is not enough evidence to mark a
Responses model/provider unavailable.
```

Current behavior:

- Probe `invalid_request` for Responses becomes request-shape-unverified.
- Runtime `invalid_request` for Responses is verified with the real client
  request shape before the provider is judged unavailable.
- Verification is keyed by the request-shape fingerprint. The default threshold
  is 3 real request failures for the same provider/model/API kind/request shape.
- For Codex clients, verification must use the real Codex request shape or a
  captured/sanitized Codex-shape template. A minimal probe is not enough.
- Before 3 confirmations, such providers remain retry candidates before paid
  fallback.
- After 3 confirmations, the provider/model/kind is marked
  `runtime_failure:real_shape_invalid` and receives a short cooldown.
- A successful real request immediately marks the provider healthy and clears
  the request-shape verification counter.
- Paid fallback is not blocked merely because a non-paid provider returned
  `invalid_request`.

The default verification/cooldown knobs are:

- `RESPONSES_INVALID_REQUEST_CONFIRMATIONS=3`
- `RESPONSES_INVALID_REQUEST_RETRY_SECONDS=60`
- `RESPONSES_INVALID_REQUEST_COOLDOWN_SECONDS=1800`

This gives a better balance than either extreme:

- Do not trust a weak synthetic probe.
- Do not treat a hand-written request as proof of Codex incompatibility.
- Do not hammer a provider forever when real requests repeatedly prove the same
  shape is invalid.

## Route Order

The current route buckets are intended to preserve availability:

```text
healthy primary
-> healthy backup/other
-> Responses request-shape retry candidates
-> exploration/shadow candidates
-> paid fallback
```

This was a stopgap to keep potentially usable primary providers in play before
paid fallback while avoiding client hard failures. The cleaner target model is
to treat request-shape-unverified primary providers as a primary sub-state with
a bounded verification budget, not as a generic bucket between backup and
fallback. The verification budget should prefer real runtime requests and use
captured Codex-shape templates only for explicit admin-triggered diagnostics.

## Adaptive Format Routing

The client-facing API kind and the upstream API kind are now separate routing
concepts:

```text
client kind: what the caller sent and expects back
upstream kind: the provider endpoint Smart Gateway chooses
```

Within the same route bucket, native routes are tried before converted routes.
Converted routes remain available as fallback, but a lower adjusted latency no
longer lets an adapter outrank a healthy native candidate for the same client
format. When the request body is a safe shape, Smart Gateway may adapt:

- `/v1/responses` client request -> healthy `/chat/completions` upstream ->
  converted back to a Responses response.
- `/v1/chat/completions` client request -> healthy `/responses` upstream ->
  converted back to a Chat Completions response.

The plain small-JSON adapter intentionally refuses complex or lossy shapes such
as tools, function calling, `reasoning`, `include`, `prompt_cache_key`,
`previous_response_id`, and Codex-specific encrypted reasoning payloads. Those
requests require either native compatibility or a dedicated compatibility mode.
Adapted routes carry an `adapter_latency_penalty_ms` score penalty for ordering
among adapter candidates, and logs include `upstream_kind` and `format_adapter`
so operators can see when conversion was used.

There is one important safety boundary: a Responses health item verified only by
the Codex diagnostic shape (`shape_status=codex_shape_verified` or
`shape_verification_source=diagnostic_codex_shape`) is not treated as a generic
small-JSON Chat -> Responses adapter candidate. That evidence proves
Codex-style Responses works, so the router uses a dedicated
`codex_responses_to_chat` adapter instead. This decision is made per health
item from `responses_compat_mode=codex`, `shape_status=codex_shape_verified`,
or a Codex diagnostic/runtime verification source; it is not hard-coded to a
provider or model. The adapter converts safely mappable Chat requests into a
Codex-compatible Responses body with Codex identity headers, low reasoning
effort, `include=["reasoning.encrypted_content"]`, `prompt_cache_key`, and
`client_metadata`. It supports OpenAI function tools, `tool_choice`,
`parallel_tool_calls`, assistant `tool_calls`, and `tool` result messages when
they can be represented as Responses function tools/calls/outputs. It still
refuses legacy `functions`/`function_call` and unsupported lossy shapes.
Successful runtime use persists `responses_compat_mode=codex` so later route
decisions keep using the same compatible shape.

This compatibility mode is learned in two generic ways:

- Probe-time: a minimal Responses probe fails with request-shape
  `invalid_request`, but the Codex diagnostic shape succeeds.
- Runtime: a safe Chat -> Responses conversion first tries the ordinary small
  Responses body; if the upstream returns `invalid_request` before any client
  output starts, the gateway retries the same endpoint once with
  `codex_responses_to_chat` and persists `responses_compat_mode=codex` on
  success.

Streaming adapters buffer complete SSE events before conversion, so a single
event split across multiple upstream network chunks is not dropped. This applies
to both Chat stream -> Responses stream and Responses stream -> Chat stream.
Responses `function_call` stream events are converted to Chat `tool_calls`
deltas instead of being emitted as plain text.

For Chat upstream -> Responses client conversion, Smart Gateway also preserves
and normalizes usage information. Chat-style `prompt_tokens` /
`completion_tokens` are mapped to Responses-style `input_tokens` /
`output_tokens`, while the original keys are kept for OpenAI-compatible
gateways that still parse chat usage fields. If an upstream stream completes
without usage, `ADAPTER_SYNTHESIZE_USAGE=true` makes the adapter emit a
conservative estimated usage on `response.completed` with `estimated: true`.
This prevents New API from recording successful Responses requests as
zero-token failures such as `total tokens is 0, cannot consume quota`.
The final `response.completed.response` also carries full `output` and
`output_text` for Chat -> Responses streams. New API's Claude/Anthropic
conversion path may reject a stream with `422` / `NO OUTPUT IN RESPONSE` when
only delta events were sent and the completed response object has no output.

Real validation on 2026-06-13 covered:

- Volcengine `deepseek-v4-pro`: native Responses stream succeeded; Chat client
  request selected the lower-latency Responses upstream and converted back to
  Chat successfully.
- Fufu `mimo-v2-flash`: native Chat and native Responses both succeeded.
- Muyuan `claude-opus-4-8`: Responses client requests, both non-stream and
  stream, used the Chat upstream and converted back to Responses successfully.
- Anyrouter `gpt-5.5`: plain Responses small JSON still returns
  `invalid codex request`, but Codex-compatible Chat -> Responses conversion now
  succeeds through `codex_responses_to_chat`; normal `gpt-5.5` Chat routing
  selects Anyrouter Responses instead of the paid Chat fallback. Runtime
  learning also covers the case where a new provider has not yet been classified
  as Codex-compatible by probe state.
- 2026-06-14 follow-up: Chat stream requests from Codex-style clients can carry
  `tools`, `tool_choice`, `parallel_tool_calls`, `reasoning_effort`, and
  `stream_options`. The route filter now evaluates Codex-compatible eligibility
  per Responses health item, so these requests can select a verified Codex
  Responses upstream instead of failing locally with `no_healthy_upstream`.
  Real validation against Anyrouter `gpt-5.5` confirmed both a tool-bearing
  text stream and a forced `tool_choice` stream; the latter returned Chat
  `tool_calls` deltas after passing through `/responses`.
- Image-bearing Chat requests use the same Codex-compatible path when the
  Responses health item has Codex evidence. Chat content parts such as
  `{"type":"image_url","image_url":{"url":"..."}}` are mapped to Responses
  `{"type":"input_image","image_url":"..."}` while preserving `detail`. Plain
  small-JSON conversion remains text-only. Request logs now include
  `message_content_types` and `has_image_content` even for local
  `no_healthy_upstream` decisions, so multimodal routing failures can be
  diagnosed from logs without seeing the full image payload.
  Upstream `400 invalid_value` errors on `param=input` are classified as
  `client_invalid_input` and do not cool down provider health, because malformed
  or unsupported image data is a request issue rather than proof that the
  provider/model/kind is unhealthy.

## Operations UI

New API UI is for public gateway administration:

- Users and tokens.
- Groups and subscriptions.
- Channels.
- Model management.
- Pricing and model ratios.
- Public request logs and billing.

Smart Gateway UI is for route operations:

- Model availability, with `按模型` and `按上游` views in one tab.
- Probe matrix (`探测矩阵`) with live health-policy help.
- Final upstream route logs.
- Source pool strategy.
- Sync/reload controls.

Smart Gateway UI should not replace New API's channel/user/token system.

The former top-level `运行时模型` and `上游模型状态` pages were merged because
they represented the same health matrix from two angles. `按模型` answers
"which public model is usable and through which preferred/fallback upstreams";
`按上游` answers "which models does this source provide and what cooldown or
error state is each one in". Both views share model/upstream filters and the
`显示异常` toggle. Tables use fixed layouts so showing unhealthy rows does not
change column widths.

Model ordering is consistent across backend APIs, UI lists, and the New API
sync script:

```text
model family rank -> numeric version parts descending -> text
```

This puts `gpt-5.5` before `gpt-5.4-mini` and `claude-opus-4-8` before
`claude-opus-4-6`.

## Known Operational Issues and Lessons

- A client-side model catalog can make a request appear to target another model
  in the client UI. Always check Gateway request logs for the actual requested
  model and final upstream model.
- `413 Payload Too Large` is usually an upstream/provider gateway body limit.
  The client must compact the conversation or the provider must raise its body
  size limit.
- New API may require two-factor authentication or Passkey for sensitive admin
  actions such as viewing keys. This is a New API security policy, not a Smart
  Gateway routing issue.
- A channel test may fail while real usage succeeds if the channel test sends a
  weaker or different request shape.
- `/models` can be empty or stale and still not prove that real requests are
  impossible.
- Multi-base-url variants of the same provider should remain one logical
  provider so the same quota pool is not counted multiple times.

## Security

Never commit:

- `.env`
- provider config with real keys
- New API database files
- request logs
- health-state runtime caches
- cookies, bearer tokens, refresh tokens, or session data
- production domains or private server paths in public docs

Use placeholders such as:

```text
https://api.example.com
example-redacted-key
provider-primary
provider-paid-fallback
```

## Verification

Before pushing public changes:

```bash
python -m py_compile smart-gateway/app/main.py scripts/sync-newapi-router.py
pytest -q smart-gateway/tests
git status --short --ignored
git grep -n -I -E 'sk-[A-Za-z0-9_-]{12,}|password|secret|token|api[_-]?key'
```

Review grep hits manually. Code identifiers such as `ADMIN_TOKEN` or
`api_key_env` are acceptable; real secret values are not.
