# New API 与 Smart Gateway 边界

本文是公开脱敏版说明，不包含真实域名、服务器路径、IP、密钥、日志或上游账号信息。

## 对外入口

公开入口应只暴露 New API：

```text
https://api.example.com
```

客户端 API Key 应在 New API 的令牌页面生成。Smart Gateway 的内部访问 Key 只用于 New API 的路由渠道，不应作为公开客户端 Key 分发。
兼容入口 `https://api.example.com/v1` 可保留给已经配置过 `/v1` 的客户端。

## New API 负责

1. 用户、令牌、额度、订阅、分组。
2. 渠道管理：新增、删除真实上游 Base URL 和 Key。
3. 模型管理：模型展示、权限、价格和倍率。
4. 对外请求日志：用户、token、扣费、New API channel。
5. 安全策略：例如敏感操作要求两步验证或 Passkey。

真实上游通道应保持在正常用户分组中，并设置渠道标签 `gateway-source`。
`Smart Gateway Router` 是 New API 渠道，不是用户分组。

## Smart Gateway 负责

1. 从 New API 同步带 `gateway-source` 标签的源池。
2. 按模型、接口类型和真实上游维护健康矩阵。
3. 按主力、机会、备份、付费兜底策略选择真实上游。
4. 对模型不存在、余额不足、限流、服务异常做冷却。
5. 记录最终真实上游、路由桶、成本层级、失败原因和耗时。
6. 对 Responses `invalid_request` 区分“请求形态待验证”和“模型真实不可用”。

## 当前模型暴露规则

Smart Gateway 的 `/v1/models` 不是所有上游 `/models` 的并集。当前公开模型必须同时满足：

1. 通过 `model_include`。
2. 未命中 `model_exclude`。
3. 至少一个 `chat` 或 `responses` 健康上游达到 `MIN_HEALTHY_PROVIDERS`，且探测返回内容不是空回复或 `ok` / `pong` 这类低信号文本。
4. 同步到 New API Router channel 后未被 New API 模型管理手动禁用。

当前运营屏蔽包含：

```yaml
model_exclude:
  - "gpt-5.4*"
  - "*-20??????"
```

这会隐藏 `gpt-5.4`、`gpt-5.4-mini` 以及 `claude-haiku-4-5-20251001` 这类长日期后缀模型。后续如果要恢复这些模型，需要删除对应规则、reload Smart Gateway，并重新同步 New API Router channel。

## 运维入口

```text
New API: https://api.example.com/
Smart Gateway: https://api.example.com/gateway-admin/
```

Smart Gateway 后台是路由运维视图，不是第二套用户/令牌/订阅系统。新增上游时先在 New API 渠道管理添加，并设置标签为 `gateway-source`。

## 日常管理方式

1. 新增上游：New API 渠道管理新增渠道，填 Base URL 和 Key，标签加 `gateway-source`。
2. 维护源池策略：在 Smart Gateway 后台修改启停、路由桶、成本层级、权重、优先级、Base URL 和声明模型。
3. 关闭上游：在 New API 渠道管理停用，或在 Smart Gateway 源池策略中停用。
4. 调整权重：优先在 Smart Gateway 源池策略里调整；保存后回写 New API 渠道。
5. 设置兜底：把付费渠道设为“付费兜底 + 付费 + 仅兜底”，只有其它候选不可用时才使用。
6. 关闭模型：在 New API 模型管理里关闭模型。同步脚本应尊重关闭状态。
7. 模型价格/倍率：在 New API 模型管理或倍率配置里维护。
8. 最终流向日志：New API 看用户和扣费；Smart Gateway 看最终真实上游和路由原因。
9. 源渠道模型声明：不要因为健康失败自动清空；实际可用性由 Smart Gateway 运行时健康决定。
10. 客户端声称请求模型与日志不一致时，以 Smart Gateway request log 的 `requested_model` 和 `actual_model` 为准；客户端 catalog 或缓存可能发出旧模型。

## Smart Gateway 运维 UI

当前 Smart Gateway 后台顶级页签中，模型相关视图为：

- `模型可用性`：包含 `按模型` 和 `按上游` 两个视角。两者读取同一健康矩阵，只是面向日常确认和排障的不同展示，不再拆成两个顶级页签。
- `探测矩阵`：展示原始探测记录，并带健康策略说明。说明区展示探测间隔、单轮预算、超时、健康新鲜窗口、Responses 二段验证、真实请求三次确认、跨格式路由和各类冷却时间。

`模型可用性` 默认只显示至少一个接口健康的模型或上游模型；勾选“显示异常”后展示异常项。表格使用固定列宽，避免异常详情过长时列宽跳动。

健康项现在额外展示新鲜度：

- `实时`：最近 `HEALTH_FRESH_TTL_SECONDS` 内有探测或真实请求成功，默认 300 秒。
- `缓存`：仍在成功 TTL 内，但已经超过实时新鲜窗口；可路由，但排障时应关注下次探测时间。
- `冷却` / `待探测` / `未知`：分别表示失败冷却、等待探测预算或尚无可靠检测记录。

## 多 Base URL

同一个上游如果有多个兼容 Base URL，不应拆成多个 New API 渠道，否则同一个额度池会被权重计算成多份。应保留一个逻辑渠道，并在 Smart Gateway provider 内部配置多个 `base_urls`。

## Responses 与真实请求验证

固定探活请求可能弱于真实 Codex/Responses 请求。遇到
`invalid_request`、`invalid codex request` 这类错误时，不应直接判定模型不可用。

当前策略是保留这类上游为“请求形态待验证”候选，并允许在付费兜底前做有限重试。真正有效的验证必须使用真实 Codex 请求形态，或使用已捕获并脱敏的 Codex-shape 模板，而不是手写的极简 `curl` 请求。

一次真实 Codex CLI 请求即使 prompt 很小，body 也可能有约 38 KB，包含完整 `instructions`、真实 `input`、`reasoning` 和 `Originator`、`Session-Id`、`Thread-Id`、`X-Codex-Beta-Features`、`X-Codex-Turn-Metadata` 等 header。手写小 JSON 返回 `invalid codex request`，不能证明真实 Codex 不可用。

判断规则：

1. 固定探活失败只作为 hint。
2. 真实运行时请求成功是最强健康证据。
3. 对同一 provider/model/kind/request-shape fingerprint，真实形态连续 3 次失败后才标记 `real_shape_invalid` 并短冷却。
4. 任意一次真实形态成功，立即恢复健康并清空失败计数。
5. 多 Base URL 的同一逻辑上游，应逐个 base URL 验证，但仍归并为一个 provider。

当前默认冷却策略：

- 成功：21600 秒。
- 模型不支持或不存在：86400 秒。
- 鉴权/权限、额度：3600 秒。
- 限流：1800 秒。
- 服务异常、网络异常：900 秒。
- 探测内容为空或低信号：900 秒。
- Responses 探活形态待确认：60 秒。
- Responses 真实形态确认不兼容：1800 秒。

当前默认探测不再使用 `ping`，而是要求上游回复一句短句。普通 Chat/Responses 探测即使 HTTP 2xx 且没有 error，也会提取模型输出文本并打质量分；低于 `PROBE_MIN_QUALITY_SCORE` 时标记为 `low_signal_response` 或 `empty_response`，不进入健康候选。这个判断只应用于合成探测，不会因为真实用户请求要求“只回答 ok”而污染健康状态。

如果某上游只支持 Claude Code / Anthropic Messages / Chat 形态，但 `/responses` 返回 `not implemented`，不能因为加了客户端 header 就把 Responses 标健康。该上游应按实际可用接口展示。

## 自适应格式路由

健康矩阵仍按 `chat` 和 `responses` 独立记录上游原生能力，但运行时路由不再把客户端入口和上游入口硬绑定。

当前规则：

1. 客户端请求格式保持不变；返回格式也保持客户端请求的格式。
2. 原生健康路径优先，例如 `/v1/responses` 优先选择 Responses 健康上游。
3. 网关会先把客户端请求规范化为可比较的形态，再把所有可安全映射的上游接口都放进候选：
   - Responses 客户端请求可转成 Chat 上游请求，再把 Chat 响应转回 Responses。
   - Chat 客户端请求可转成 Responses 上游请求，再把 Responses 响应转回 Chat Completions。
   - Chat 客户端请求即使仍走 Chat 上游，也会先规范化顶层 `system`、Claude/Codex 工具定义、工具调用历史和图片内容，避免把 Anthropic/Codex 形态原样丢给 OpenAI Chat 上游。
4. 当前支持的通用输入形态包括 OpenAI Chat `tools[].function`、Responses/Codex `{type,name,parameters}` function tools、Claude/Anthropic `{name,input_schema}` tools、assistant `tool_calls`、Claude `tool_use`、Claude `tool_result`、OpenAI `image_url`、Responses `input_image` 和 Anthropic base64/url image。
5. 无法无损映射的 hosted tool、Responses `include`、`prompt_cache_key`、`previous_response_id`、Codex encrypted reasoning 等高级字段不会强行降级到 Chat；这类请求只会进入能原生承载的上游候选。
6. 转换路径带 `ADAPTER_LATENCY_PENALTY_MS`，默认 250ms；路由日志会记录 `upstream_kind`、`format_adapter`、`message_content_types`、`tool_types` 和 `tool_key_sets`，便于判断是否发生了跨格式转换以及工具协议来源。
7. Chat stream + tools 的路由判断按单个 health item 执行：同一请求可同时拥有规范化 Chat 候选、普通 Responses 候选和 Codex-compatible Responses 候选；最终按路由组、优先级、权重、延迟和 adapter penalty 选择，并在失败时继续尝试下一个候选。
8. 图片输入被上游判为 `param=input / invalid_value`，或工具 schema 被上游判为 `missing tools.function` 这类请求形态错误时，按客户端输入/形态不兼容处理，不写坏 provider 健康，也不进入运行时冷却。

## 应急写入

Smart Gateway 直接写 provider 配置的接口默认应保持禁用。正常情况下，所有上游都应从 New API 渠道同步而来。

## 相关文档

- `docs/NEWAPI.md`：当前 New API、Sub2API、AI Smart Gateway 关系和运维说明。
- `docs/retrospective-routing-review.zh-CN.md`：最近路由、健康检测、anyrouter、`invalid_request` 问题回顾。
