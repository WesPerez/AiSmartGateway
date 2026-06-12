# AI Smart Gateway Implementation Review

This is the public, sanitized implementation review for AI Smart Gateway.
It intentionally excludes real domains, server paths, IP addresses, secrets,
provider keys, request logs, backup paths, and private conversation details.

## Scope

AI Smart Gateway is an internal routing layer behind New API. New API remains
the public-facing control plane for users, tokens, quota, subscriptions,
model metadata, and public request logs. Smart Gateway focuses on downstream
provider routing, health state, failover, and route-level observability.

## Public Architecture

```text
Client
  -> New API public endpoint
  -> New API router channel
  -> AI Smart Gateway
  -> Authorized upstream providers
```

New API should be the only public API front door. Smart Gateway should normally
be reachable only from New API and from trusted operator networks.

## Responsibilities

New API is responsible for:

- Users, API tokens, quota, subscriptions, and groups.
- Public model management and model pricing.
- Channel creation for authorized upstream credentials.
- Public request logs and user-level billing records.

AI Smart Gateway is responsible for:

- Synchronizing tagged New API channels into a runtime provider pool.
- Maintaining model and endpoint health by API kind.
- Routing requests by priority, weight, cost tier, and fallback policy.
- Cooling down repeated failures to avoid wasting upstream quota.
- Recording final upstream flow logs for operational diagnosis.
- Normalizing compatible base URLs for a single logical provider.

## Routing Policy

Providers can be classified as:

- `primary`: normal preferred upstreams.
- `opportunistic`: low-cost or temporary upstreams that may be unstable.
- `backup`: lower priority but still acceptable.
- `paid_fallback`: paid or expensive upstreams used only after other options fail.

Cost tiers can be:

- `free`
- `metered`
- `paid`
- `unknown`

The router should not repeatedly probe known-missing models or unhealthy
providers. It should use cooldown windows for model unsupported, quota,
rate limit, server error, and exception cases.

## Model Discovery

Upstream `/models` responses are treated as hints, not ground truth. Some
providers return incomplete or static model lists, while still accepting real
requests for additional models.

The gateway therefore supports:

- Upstream model list fetch with cache.
- Declared model lists from New API channels.
- Canonical model aliases.
- Real minimal probes with cooldown.
- On-demand retry candidates for models whose probe request shape is known to
  be weaker than a real client request.

The source channel `models` field in New API is treated as an operator
declaration and must not be destructively pruned just because current runtime
health is bad. Smart Gateway health state controls effective routing; New API
channel declarations remain the operator's candidate list.

## Responses `invalid_request`

Responses probes are weaker than real Codex requests. A provider returning
`400 invalid_request` or `invalid codex request` to a minimal synthetic probe is
not enough evidence to mark the provider/model unavailable.

Current behavior:

- Responses probe `invalid_request` is classified as request-shape-unverified.
- Runtime Responses `invalid_request` does not trigger long runtime cooldown.
- Such providers remain bounded retry candidates before paid fallback.
- Paid fallback is never blocked only because a non-paid provider returned
  `invalid_request`.

Recommended next behavior:

- Use real client request shape for bounded verification.
- Confirm the same provider/model/kind/request-shape class up to three times
  before marking it real-shape-invalid.
- Do not replay after a stream has started.
- Clear the verification failure counter immediately on runtime success.

## Responses API Streaming

For OpenAI Responses-compatible streaming clients, the gateway must not close
the stream without a terminal Responses event. If the upstream omits
`response.completed`, the gateway may synthesize a minimal completion event
before sending `[DONE]`. If the route fails before a successful stream starts,
the gateway emits a `response.failed` event.

This avoids clients reporting that the stream closed before completion.

## New API Integration

Recommended source-pool workflow:

1. Add authorized upstream providers as New API channels.
2. Tag provider channels with `gateway-source`.
3. Keep the Smart Gateway router itself as a normal New API channel.
4. Run the sync script periodically to generate Smart Gateway provider config.
5. Manage end-user tokens, groups, quota, and subscriptions in New API.
6. Use Smart Gateway only for route policy, health matrix, and final upstream logs.

New API router channel settings should preserve Codex/Responses semantics:

- body pass-through enabled
- `store` pass-through enabled
- Codex/OpenAI request headers passed through
- upstream model auto-sync disabled on the router channel

The router channel is a New API channel, not a user group. User groups such as
`default` and `vip` remain New API concepts.

## Related Documents

- [Current New API / Smart Gateway boundary](current-newapi-smart-gateway-boundary.zh-CN.md)
- [New API, Sub2API, and AI Smart Gateway operations](NEWAPI.md)
- [Recent routing retrospective](retrospective-routing-review.zh-CN.md)

## Security Notes

Do not commit:

- `.env`
- real provider config files
- API keys, cookies, or bearer tokens
- New API database files
- request logs
- health-state caches
- backups
- local virtual environments or test dependency directories

The repository should contain only examples, code, sanitized docs, and deploy
templates.

## Verification

Recommended verification before release:

```bash
python -m py_compile smart-gateway/app/main.py smart-gateway/app/admin_ui.py scripts/sync-newapi-router.py
pytest -q smart-gateway/tests
git grep -n -I -E 'sk-[A-Za-z0-9_-]{12,}|password|secret|token|api[_-]?key'
```

Any grep hit should be reviewed. Placeholder values and code variable names are
acceptable; real credentials are not.
