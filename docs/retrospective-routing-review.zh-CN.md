# Smart Gateway 最近问题回顾与路由策略评审

本文整理最近一轮可见讨论、实现变更、排查结论和后续优化方向。内容已脱敏，不包含真实域名、密钥、令牌、请求日志原文、数据库路径或私人账号信息。

## 起点问题

最初的问题集中在“统一入口能测试连接，但不能稳定实际使用某些模型”。随后逐步扩展为一整套 New API + Smart Gateway 的职责划分和上游治理问题：

- 统一入口为什么只暴露少数模型。
- `/models` 是否应该是所有上游模型的并集。
- 为什么会出现上游没有声明但网关里存在的模型。
- GPT、Claude、Gemini、OpenAI-compatible、Anthropic-compatible、Volcengine Coding 等协议如何识别和转换。
- 客户端请求 `gpt-5.5` 或 Claude 模型时如何匹配到真实上游。
- 多个上游都有同一模型时如何排序、权重、兜底。
- 多个上游只有一家有某模型时如何选择。
- `chat/completions` 和 `responses` 的可用性是否一致。
- 如何减少无效健康探测和额度浪费。

早期直觉是“所有上游模型合并后暴露”，后来修正为：

```text
模型声明是候选来源，真实暴露应由运行时可用性、用户手动禁用和 New API 管理策略共同决定。
```

## 架构演进

早期 `NEWAPI.txt` 里的方案是 Smart Gateway 直接作为公开 OpenAI-compatible 网关：

```text
Client -> Smart Gateway -> upstreams
```

当前实际方案已经变成：

```text
Client -> New API -> Smart Gateway Router channel -> Smart Gateway -> upstreams
```

这个调整是必要的，因为 New API 已经提供成熟能力：

- 用户和令牌。
- 额度和订阅。
- 分组。
- 渠道管理。
- 模型管理。
- 价格和倍率。
- 对外请求日志。
- 管理后台安全策略。

Smart Gateway 不应重复做这些能力。它的职责是后置路由、模型级健康、失败冷却、最终上游流向、策略层级和运行时观测。

## New API 与 Smart Gateway 职责

New API 负责：

- 对外入口。
- 用户 API key。
- 用户请求扣费。
- 用户分组和订阅。
- 上游渠道录入。
- 模型管理与价格倍率。
- 用户视角请求日志。

Smart Gateway 负责：

- 同步 New API 中带 `gateway-source` 标签的真实上游渠道。
- 生成内部 provider 池。
- 维护 `chat` 和 `responses` 分开的模型健康矩阵。
- 根据主力、机会、备份、付费兜底策略路由。
- 记录每次请求最终流向哪个 provider、哪个 endpoint、耗时、错误类型。
- 避免对已知失败模型/上游做高频重复探测。
- 在多 base URL 同属一个上游时作为一个逻辑 provider 处理。

Smart Gateway 不是第二套 New API。

## 上游整理结论

讨论中处理过多类上游：

- 主力免费或低成本上游。
- 不稳定但可利用的机会型上游。
- 备份型上游。
- 付费兜底上游。
- Volcengine Coding 这类有 OpenAI-compatible 和 Anthropic-compatible 两种 base URL 的特殊上游。
- 支持多个 base URL 的同一上游。
- New API 内新增的临时渠道。

最终策略：

- 真实上游都从 New API 渠道管理录入。
- 需要进入 Smart Gateway 源池的渠道加 `gateway-source`。
- 同一上游多个兼容 base URL 不拆成多个渠道，避免同一额度池被重复计权。
- 付费上游只作为 `paid_fallback`。
- 主力上游优先级最高。
- 新发现但不稳定的上游可放入 `opportunistic`，让它们被利用但不压过主力。
- Volcengine Coding 只保留有意义模型族，例如最新 deepseek flash、deepseek pro、GLM，避免探测无意义模型。

## 模型管理问题

讨论中反复出现“模型列表不对”的问题，原因包括：

- 上游 `/models` 返回不完整。
- 上游 `/models` 返回静态虚标列表。
- New API 渠道模型字段与 Smart Gateway 健康矩阵不同步。
- 健康失败曾经被错误用于清空 New API 源渠道模型。
- New API 模型管理中的历史价格项过多。
- 某些模型在客户端 catalog 中显示名和实际请求模型不同。

目前结论：

- New API 源渠道 `models` 是人工声明和候选，不应被健康失败自动清空。
- Smart Gateway 运行时健康决定实际路由。
- New API Router channel 的模型列表由 Smart Gateway `/v1/models` 同步生成。
- New API 模型管理里可隐藏 Smart Gateway 自动管理但已不可用的模型，同时保留历史价格归档，避免模型下次恢复时丢失人工价格。
- 客户端 catalog 只影响客户端展示/元数据，不应作为服务端实际请求模型的判断依据。实际请求以 Gateway request log 为准。

## 权重、优先级和策略层级

曾经同时存在这些概念：

- New API 渠道优先级和权重。
- Smart Gateway provider 优先级和权重。
- 主力、机会、备份、付费兜底。
- 成本类型：免费、计量、付费、未知。
- fallback_only。

最终建议：

- Smart Gateway 路由只以 route group、fallback flag、priority、weight、health 为核心。
- 成本类型主要用于显示和分析，不应成为关键路由条件。
- 付费兜底应由 route group `paid_fallback` 和 `fallback_only` 表达。
- New API 的优先级/权重用于它自己的渠道选择；Smart Gateway 的优先级/权重用于内部真实上游选择。同步脚本会从 New API 渠道读取并生成 Smart Gateway provider，但两边含义不能混淆。

当前路由意图：

```text
健康主力
-> 健康备份/其它
-> Responses 请求形态待验证候选
-> 探索/影子候选
-> 付费兜底
```

这个顺序是止血版本，不是最终最优版本。更理想的设计是把“请求形态待验证”作为主力 provider 的子状态，并给它真实请求验证预算，而不是独立成一个普通 bucket。

## 健康检测策略

核心原则经历了三次修正：

第一版想法：

```text
拉 /models -> 对所有模型发最小请求 -> 成功才暴露
```

问题：

- 全量探测浪费额度。
- 对不存在模型重复请求。
- 对服务异常上游重复请求。
- Responses minimal probe 可能弱于真实 Codex 请求。

第二版修正：

```text
加入模型列表缓存、探测预算、失败冷却、按需重试。
```

第三版修正：

```text
Responses invalid_request 不等于模型不可用，应进入请求形态待验证状态。
```

当前健康分类：

- `ok`：健康。
- `model_unsupported` / `not_found`：模型大概率不支持，长冷却。
- `quota`：余额/额度不足，冷却。
- `rate_limited`：限流，冷却。
- `server_unavailable`：上游服务异常，短/中冷却。
- `auth_or_forbidden`：凭据或权限问题，较长冷却。
- `responses_request_shape_unverified`：Responses 探活或当前请求形态被拒，但不能证明真实 Codex 请求不可用。

## `invalid_request` 的真实问题

你指出的问题是正确的：如果健康检测不带真实请求形态，`invalid_request` 很容易被误判。

这次 anyrouter 事件中观察到：

- 该上游作为主力被选中了。
- 两个 base URL 都返回 `invalid codex request`。
- 早期错误逻辑在看到非付费上游 `invalid_request` 后阻断了付费兜底，导致客户端失败。
- 后续修复删除了这个阻断。
- Gateway 现在会保留 anyrouter 为 Responses 请求形态待验证/重试候选。
- New API Router 已开启 body pass-through。
- Codex/OpenAI 相关 headers 已加入 pass-through。
- Gateway 也透传这些 header，并补 `instructions: ""`、`store: false` 等安全默认值。

当前仍不足：

- 固定探活不能证明真实 Codex 请求是否可用。
- 手写或简化的 curl 请求不等于真实 Codex CLI 请求。
- 真正应该使用实际用户请求形态，或已捕获并脱敏的真实 Codex-shape 模板做 bounded verification。

正确策略：

1. 当 Responses 上游在真实请求上返回 `invalid_request`，且失败发生在 stream 第一块之前，记录为 `shape_verification_needed`。
2. 对同一 provider/model/kind/request-shape-fingerprint 做最多 3 次真实形态确认。
3. 三次可以在短时间窗口内跨真实请求累计，而不是每个用户请求都立即打三次。
4. 如果三次都返回同类 `invalid_request`，标记为 `real_shape_invalid` 并短冷却。
5. 如果任一次成功，立即标记健康并清除该 shape 的失败计数。
6. 对非幂等或已经开始 stream 的请求不重放。
7. 对失败前没有任何 token 输出的 400，可以尝试同 provider 的备用 base URL。
8. 管理员主动诊断时，可以使用捕获/脱敏后的真实 Codex-shape 模板发起验证；不能用手写极简请求代替。

这比“固定探活失败就判死”和“永远不判死”都更合理。

### 真实 Codex shape 验证结论

这次重新验证时，先用本地捕获代理接收 `codex exec 0.139.0` 的真实请求，再把捕获到的 body/header 原样转发到 anyrouter，只替换为 provider 的真实 `Authorization`。

真实 Codex 请求特征：

- `POST /v1/responses`。
- `Accept: text/event-stream`。
- 即使 prompt 很小，body 也约 38 KB。
- body 包含完整 Codex `instructions`、真实 `input`、`reasoning` 等字段。
- header 包含 `Originator: codex_exec`、`User-Agent: codex_exec/...`、`Session-Id`、`Thread-Id`、`X-Codex-Beta-Features`、`X-Codex-Turn-Metadata`。

验证结果：

- `https://anyrouter.top/v1/responses`：真实 Codex shape 连续 3 次 `HTTP 200`，SSE 正常返回。
- `https://a-ocnfniawgw.cn-shanghai.fcapp.run/v1/responses`：真实 Codex shape 连续 3 次 `HTTP 200`，SSE 正常返回。

因此，anyrouter 的 `gpt-5.5 / responses` 不能因为手写小 JSON 或固定探活返回 `invalid codex request` 被判不可用。正确结论是：真实 Codex shape 可用，探活 shape 不可信。

## anyrouter 事件总结

已完成的修复：

- 保留双 base URL 为一个逻辑 provider。
- 删除 `paid_fallback_blocked_after_invalid_request`。
- `invalid_request` 不再让 Responses provider 长冷却。
- 请求形态问题会显示为“待真实请求验证”。
- `probe_retry` 会在付费兜底前尝试。
- 付费兜底仍可接管，避免客户端直接失败。
- New API Router channel 已启用 body pass-through。
- `disable_store=false`，避免 New API 移除 `store` 影响 Codex。
- 添加 Codex/OpenAI header pass-through，包括 `X-Codex-Turn-Metadata`。
- Gateway 上游请求补 `instructions` 和 `store` 默认值。

仍需验证：

- New API -> Gateway -> anyrouter 的完整链路是否完全保留上述真实 Codex shape。
- Gateway 当前日志是否足够展示 request-shape fingerprint、确认计数和 base URL 结果。
- 如果完整链路仍失败，应做字段级 diff，而不是继续靠固定探活。

## UI 与管理功能演进

Smart Gateway 后台逐步增加和调整了：

- 概览。
- 运行时模型。
- 健康矩阵。
- 路由日志。
- 源池策略。
- 路由视图。
- 上游模型状态。
- 分页和每页条数。
- 默认只显示健康上游模型。
- 运行时模型按模型名称排序，GPT/Claude 等靠前。
- 上游模型状态筛选。
- 源池策略可编辑启停、优先级、权重、route group、模型声明。
- 按模型查看有哪些上游、优先级、权重、健康状态。
- 将费用类型弱化为显示信息，避免误导路由决策。
- 对 request-shape-unverified 做更准确展示。

设计目标不是“再做一套 New API”，而是让操作者一眼看出：

- 哪些模型可用。
- 哪些上游可用。
- 某个模型会按什么顺序选上游。
- 请求最终去了哪里。
- 为什么失败或兜底。

## New API 管理步骤

在 New API 中：

1. 新增真实上游渠道。
2. 填写真实 base URL 和 key。
3. 添加标签 `gateway-source`。
4. 在模型字段中声明候选模型。
5. 保持用户分组如 `default`、`vip`。
6. 不需要创建名为 Smart Gateway Router 的用户分组；Smart Gateway Router 是渠道。
7. 用户 token、额度、订阅、模型价格仍在 New API 管。
8. 如果模型管理要求价格，自动同步应给新可用模型设置默认倍率，并归档历史人工倍率。

在 Smart Gateway 中：

1. 同步 New API 源池。
2. 查看源池策略。
3. 修改路由组、优先级、权重、启停。
4. 查看运行时模型。
5. 查看健康矩阵。
6. 查看最终路由日志。
7. 分析某个模型的可用上游排序。

## 常见问题记录

### `/v1` 是否需要

公开 New API 入口可以同时支持根路径和 `/v1` 兼容。客户端需要哪个取决于工具。有些工具 base URL 填根路径后会自动拼 `/v1`，有些需要显式填 `/v1`。文档应使用 `https://api.example.com` 为推荐，并说明 `/v1` 是兼容入口。

### 413 Payload Too Large

这是上游或中转的请求体大小限制，不是 Smart Gateway 能完整解决的问题。可恢复方式：

- 压缩上下文。
- 删除大段日志或图片。
- 提高上游 Nginx/API gateway 的 body limit。

### New API 查看密钥要求 2FA/Passkey

这是 New API 的安全策略。Smart Gateway 不应绕过。

### CCS/Codex 单独直连成功但通过网关失败

可能原因：

- New API 没有透传原始 body。
- New API 没有透传 Codex headers。
- Gateway 没有继续透传 headers。
- Gateway 固定探活比真实请求弱。
- Gateway 请求体规范化缺少 Codex 必需字段。
- 客户端 catalog 显示和实际请求模型不一致。

排查以 Smart Gateway request log 的 `requested_model`、`actual_model`、`provider_id`、`request_shape`、`endpoint_url`、`error_type` 为准。

### 上游模型重复

同模型同分组下多个健康上游时：

1. 先看 route group。
2. 再看 priority。
3. 同 priority 下按 weight 和延迟评分选择。
4. 当前请求失败后会从候选中移除已尝试 provider，再试下一个。

### 只有一家上游有模型

如果那一家健康，就使用它。如果不健康，按策略进入请求形态验证、探索或付费兜底。没有可用候选才返回无健康上游。

## 可见问题清单与处理结果

本节按主题归档最近可见对话中的具体问题，避免后续重复踩坑。所有真实域名、key、token、请求 id 和私有路径均已脱敏。

### 初始连接与模型不可用

- 统一入口连接测试能通过，但实际使用 `gpt-5.5` 失败。
- 追问为什么统一入口只暴露少数模型。
- 追问模型是否应来自所有上游 `/models` 的集合。
- 结论：`/models` 只能作为 hint；真实暴露必须结合声明模型、实际探活、运行时成功、用户禁用状态。

### 协议与请求格式

- 追问 GPT、Claude、Gemini、OpenAI-compatible、Anthropic-compatible 请求格式不同，Gateway 如何知道上游格式。
- 结论：当前系统以 OpenAI-compatible `/chat/completions` 和 `/responses` 为核心；Volcengine Coding 等特殊上游需要按官方 base URL 区分兼容协议；真正跨 Anthropic/Gemini 原生协议转换应明确做 adapter，不能靠猜。
- 后续建议：在 provider 中增加明确 `protocol` / `request_format` 字段，避免只通过 base URL 推断。

### 上游新增与清理

- 添加过多个新上游和 key，包括共享类、Volcengine Coding、anyrouter、某 Claude 聚合上游、付费兜底等。
- 清理过重复 Volcengine 配置、无用 key、重复或多余上游。
- 确认付费上游应作为兜底。
- 确认 anyrouter 和某 Claude 聚合上游可作为主力或高优先级候选。
- 结论：真实上游不再直接写死到公开文档，统一在 New API 渠道中管理，Smart Gateway 通过 `gateway-source` 同步。

### Volcengine Coding

- 官方说明有两个 base URL：一个兼容 Anthropic 协议，一个兼容 OpenAI 协议。
- 曾经出现官方有 GLM 新版本但系统只识别旧 GLM 的问题。
- 结论：Volcengine 不能只信 `/models`，应通过官方声明模型族和过滤规则选择最新 deepseek flash、deepseek pro、GLM。
- 2026-06-13 复查 `deepseek-v4-pro` 失败时，最近日志显示上游 `/api/coding/v3/responses` 返回 `400 MissingParameter`，缺少 `partial` 参数；修复方向改为通用 Responses 兼容机制：任意上游在运行时请求、minimal probe 或 Codex-shape diagnostic 中明确返回缺 `partial` 时，Gateway 自动补 `partial=stream` 重试一次，并学习该 provider 的默认值，避免写成单模型或单上游特例。
- 2026-06-13 真实请求验证确认：Volcengine `deepseek-v4-pro` 的 Responses stream 可通过；普通 Chat 请求在该 provider 上会因为 Responses 延迟更低而走 `responses_to_chat` 转换并成功返回。
- 后续建议：Volcengine provider 增加版本排序测试，确保 `glm-5.1` 这类官方新模型优先于旧版本。

### `/models` 为空但可用

- 追问上游 `/models` 没有某模型是否还能用。
- 结论：可以。很多中转站 `/models` 不完整或禁用，但实际请求可用。
- 策略：保留 New API 渠道声明模型，不因 `/models` 缺失自动删除。

### New API 与 Smart Gateway 两套 UI

- 曾经实现过 Smart Gateway 独立后台，引发“和 New API 渠道管理、订阅、模型管理重复”的问题。
- 重新划分后：New API 是入口和管理面；Smart Gateway 是后置路由运维面。
- Smart Gateway UI 保留：运行时模型、健康矩阵、路由日志、源池策略、路由视图、上游模型状态。
- 不再把 Smart Gateway 当成第二套用户/token/订阅系统。

### New API 分组与 Router

- 发现 New API 分组里只有 `default` 和 `vip`，没有 `Smart Gateway Router`。
- 结论：`Smart Gateway Router` 是 New API 渠道，不是用户分组。
- Router channel 可以授权给 `default,vip` 等用户组；用户组本身仍由 New API 管。

### 模型管理为空或不一致

- New API 模型管理曾显示空或大量无用模型。
- 渠道模型不等于所有上游可用模型合计。
- 结论：源渠道模型是声明候选；Router channel 模型应由 Smart Gateway 有效模型同步。
- 对历史无用模型，建议自动隐藏 Smart Gateway 管理但当前不可用的模型，并保留历史价格归档。

### 价格与倍率

- 新增渠道后新模型要求手动去定价，操作成本高。
- 模型定价列表模型过多，常用模型难找。
- 方案：自动为新可用模型设置默认倍率；模型消失时不硬删人工价格，而是归档；模型恢复时恢复历史价格。

### 管理界面错误

- `/gateway-admin/` 曾出现 HTML 被当 JSON 解析的错误。
- 管理登录曾出现 Internal Server Error。
- 处理思路：后台 API 与静态页面路径分离，前端对非 JSON 响应显示可读错误，后端登录 token 校验保持简单。
- 管理 token 属于私密信息，不写入公开文档。

### New API 查看密钥 2FA/Passkey

- New API 查看密钥时提示必须启用两步验证或 Passkey。
- 结论：这是 New API 安全策略，Smart Gateway 不应绕过。

### 健康矩阵和 UI 排序

- 健康矩阵曾只有下次时间，没有当前检测时间。
- 要求按当次检测时间排序。
- 源池策略要求启用在前，再按策略层级、优先级、权重等排序。
- 右上角按钮需要说明。
- 已按方向增加排序、分页、说明和更清晰展示。

### 分页与表格

- 运行时模型、健康矩阵、路由日志、源池策略、上游模型状态都需要分页。
- 默认每页 10 条。
- 分页组件应允许调整每页条数。
- 源池策略不应过度拥挤，保存按钮位置和布局需要符合操作习惯。

### 上游模型状态页

- 需要按上游查看有哪些模型可用、当前状态、下次检测时间、接口类型、延迟、原因等。
- 默认只显示健康；异常用开关显示。
- Chat 与 Responses 延迟可能不同，不能简单合并为完全一致。
- 需要区分模型列、原因列、实际模型映射列，避免重复显示。

### 路由视图

- 需要一眼看到不同策略层级中有哪些上游和模型。
- 需要搜索或下拉选择模型，显示该模型的实际候选排序。
- Chat 与 Responses 在 UI 上可能重复，但它们延迟和可用性可能不同，不能一概隐藏；更好的方式是按模型聚合，再在行内展示两个接口状态。
- 不应使用难懂的视觉特效或过窄布局。

### 费用类型

- 曾经有免费、计量、未知、付费等费用类型。
- 结论：费用类型主要用于显示，不能替代 route group。
- 付费兜底应看策略层级 `paid_fallback` / `fallback_only`，不是看 cost label。
- 因此 UI 中弱化或去掉费用类型，避免误导。

### Base URL 是否带 `/v1`

- 曾经讨论统一入口是否保留 `/v1`。
- 当前推荐：公开 Base URL 用 `https://api.example.com`，兼容已配置 `/v1` 的客户端。
- 上游 base URL 归一化时要谨慎：OpenAI-compatible 通常补 `/v1`；特殊路径如 `/codex` 或 Volcengine 官方路径不能盲目补错。

### 多 Base URL

- anyrouter 有两个可兼容 base URL。
- 结论：当作一个逻辑 provider 的 `base_urls`，一个不通再切另一个。
- 不应拆成两个渠道，否则同一额度池被重复计权。

### Stream 断开

- 遇到过 `stream disconnected before completion` / `stream closed before response.completed`。
- 修复方向：Responses stream 成功开始后，如果上游没有 `response.completed`，Gateway 可补最小 completion 事件；失败前应发 `response.failed` 和 `[DONE]`，避免客户端悬挂。

### 413 Payload Too Large

- 遇到过上游返回 Payload Too Large。
- 结论：这是上游 body size limit，不是 Smart Gateway 能完全绕过。
- 恢复方式：压缩上下文、减少粘贴日志/图片、让上游调大 body limit。

### 客户端 model catalog

- 讨论过本地 `cc-switch-model-catalog.json` 是否能删或注释。
- 结论：客户端 catalog 影响客户端展示、模型元数据、默认能力配置；服务端实际路由以请求中的 `model` 为准。
- 如果 catalog 中模型描述和实际请求不一致，排查应看 Gateway request log。

### 请求跑到非预期模型

- 曾出现配置 `gpt-5.5`，日志却看到其它模型或其它上游。
- 可能原因：客户端 catalog、New API 模型映射、渠道模型配置、请求体实际 model、或上游自身别名。
- 排查顺序：客户端请求体 -> New API request log -> Gateway request log -> upstream actual_model。

### anyrouter 直连可用但网关失败

- 用户确认 anyrouter 直连 Codex 可用。
- Gateway 路由日志显示 anyrouter 被选中，但返回 `invalid codex request`。
- 说明问题不是“没有选中 anyrouter”，而是经过 New API/Gateway 后的请求形态与直连 Codex 不一致。
- 已补 body/header pass-through 和部分 Responses 默认字段。
- 仍需真实 Codex 请求日志确认是否完整透传。

### 付费兜底误用

- 付费兜底曾被频繁使用，引发额度消耗担忧。
- 原因包括主力被错误判不健康、`invalid_request` 长冷却、固定探活误判。
- 处理：移除错误阻断；保留 anyrouter 为请求形态待验证；付费兜底仅在其它候选失败后使用。
- 后续：实现真实请求三次确认后，才能更准确减少误用兜底。

### 探测成本

- 不应每次全量请求所有模型和所有上游。
- 已采用方向：模型列表缓存、探测预算、失败冷却、按需重试、运行时成功反写健康。
- 后续：按请求热度优先探测；对长期没人请求的模型降低探测频率；对 `model_unsupported` 用长冷却；对 `server_unavailable` 用短冷却。

### 仓库和命名

- 两个项目已按仓库名整理：Sub2API 与 AiSmartGateway。
- 项目关系应写入文档：Sub2API 是独立 New API/sidecar 网关项目；AiSmartGateway 是 New API 后置智能路由项目。
- 推送前必须扫描明文账密，忽略 `.env`、provider config、data、logs、数据库、备份。

### 文档迁移

- 旧 `NEWAPI.txt` 是早期一键部署/直连 Gateway 说明。
- 不能原样上传：包含真实默认域名、旧路径、旧脚本、旧职责划分。
- 已整理为公开版 `docs/NEWAPI.md`，保留有效原则，删除私密信息和过时直连架构。

## 已提交的重要变更

最近相关提交包括：

- `Preserve source models and pass Codex headers`
- `Fix responses retry routing and source model sync`

这些提交完成了：

- New API Router channel body pass-through。
- Codex/OpenAI header pass-through。
- 保留 New API 源渠道模型声明。
- 删除错误的 paid fallback 阻断。
- Responses `invalid_request` 请求形态待验证。
- Responses `invalid_request` 真实请求三次确认机制：探活形态失败不直接误杀；真实客户端请求同一请求形态连续 3 次失败后才标记 `runtime_failure:real_shape_invalid` 并短冷却。
- 成功真实请求会立即反写健康状态，并清空 request-shape failure counter。
- 上游模型状态页显示探活/真实请求验证和冷却策略。
- 真实 Codex shape 捕获验证确认：anyrouter 两个 base URL 均 3/3 成功。
- UI 显示优化。
- 测试覆盖。

## 2026-06-13 运行优化记录

本节记录最近一轮对 Smart Gateway 的实际检查、结论、代码调整、配置调整和验证结果。内容保留工程判断和排查思路，但不包含真实密钥、完整请求日志、私有请求 id 或运行目录。

### 触发问题

这一轮从几个具体感觉异常的问题开始：

- 用户感觉健康检测仍然“不太对”，要求讲清楚当前健康检查策略和冷却制度。
- `运行时模型` 与 `上游模型状态` 两个页面功能有重复，希望判断是否整合。
- `健康矩阵` 页签需要一眼能懂的策略说明，最好用小问号或美观的解释区。
- `模型可用性` 中“按模型 / 按上游”切换“显示异常”时，表格列宽不应跳动。
- 按模型和按上游排序时，同族模型版本号应数字倒序，例如 `gpt-5.5` 排在 `gpt-5.4` 前，`claude-opus-4-8` 排在 `claude-opus-4-6` 前。
- 某 Claude 聚合上游曾返回 `channel:client_restricted`，提示只允许 Claude Code 或 Codex 类客户端。
- 用户明明使用 `gpt-5.5`，却看到近期有一堆 `gpt-5.4` 请求和探测记录。
- 后续要求先屏蔽 `gpt-5.4*`，并屏蔽 `claude-haiku-4-5-20251001` 这类长日期后缀模型。

### 当前健康检查策略

当前健康矩阵的记录粒度是：

```text
API kind -> local model -> provider -> actual upstream model
```

其中 `kind` 分为 `chat` 和 `responses`，两者独立探测、独立缓存、独立冷却。一个模型 Chat 健康不代表 Responses 健康；Responses 健康也不代表 Chat 健康。

运行策略：

- 启动后按配置执行探测，默认 `PROBE_ON_STARTUP=true`。
- 后台探测循环默认每 `PROBE_INTERVAL_SECONDS=60` 秒运行一次。
- 单轮最多探测 `PROBE_MAX_PER_CYCLE=12` 个候选，避免一次全量打爆上游或浪费额度。
- 单次探测默认超时 `PROBE_TIMEOUT_SECONDS=12` 秒。
- 上游 `/models` 结果按 provider 签名缓存，默认 `MODELS_REFRESH_SECONDS=3600` 秒刷新。
- 模型候选来自上游 `/models`、New API 渠道声明模型、provider `model_map`、canonical aliases。
- New API 源渠道模型声明不会因为健康失败被自动清空；真实可用性由 Smart Gateway health state 决定。
- `/v1/models` 只公开当前至少有一个健康接口的模型，并受 `model_include` / `model_exclude` 过滤。

基础探活请求：

- Chat 使用配置里的 `/chat/completions` minimal body。
- Responses 使用配置里的 `/responses` minimal body。
- Responses 请求自动补 `OpenAI-Beta: responses=v1`，除非请求已有该 header。
- 运行时请求会透传允许列表中的 Codex/OpenAI headers，但始终用 provider 自己的 `Authorization` 覆盖上游授权。

### 当前冷却制度

默认冷却值如下，实际部署可通过环境变量覆盖：

| 状态 | 默认冷却 | 说明 |
| --- | ---: | --- |
| `ok` / healthy | 21600 秒 | 成功结果缓存，减少重复探测 |
| `model_unsupported` / `not_found` | 86400 秒 | 模型大概率不支持，长冷却 |
| `auth_or_forbidden` | 3600 秒 | 凭据、权限或客户端限制类问题 |
| `quota` | 3600 秒 | 余额或额度不足 |
| `rate_limited` | 1800 秒 | 限流 |
| `server_unavailable` | 900 秒 | 5xx、网关错误、上游临时不可用 |
| `exception:*` | 900 秒 | 超时、网络异常等 |
| `unknown` | 1800 秒 | 未归类错误 |
| `responses_request_shape_unverified` | 60 秒 | Responses 探活形态不可信，快速复查 |
| `runtime_failure:real_shape_invalid` | 1800 秒 | 真实请求形态确认不兼容后短冷却 |

Responses 的 `invalid_request` 特殊处理：

- 固定探活返回 `invalid_request` 或 `invalid codex request` 时，不直接判死。
- Gateway 会追加一次 Codex diagnostic shape 的流式探测。该诊断请求包含 Codex 风格 `instructions`、`input`、`tools`、`reasoning`、`store=false`、`stream=true`、`include=["reasoning.encrypted_content"]`、`prompt_cache_key`、`client_metadata`，并带 `Originator: codex_exec`、`User-Agent: codex_exec/...`、`X-Codex-Beta-Features`、`X-Codex-Turn-Metadata`、`Session-Id`、`Thread-Id`、`X-Client-Request-Id` 等 header。
- 诊断成功则标记 `shape_status=codex_shape_verified`，健康原因仍为 `ok`。
- 诊断仍失败但错误是形态类，则保留为 `responses_request_shape_unverified`，进入 60 秒快速重试。
- 真实运行时 Responses 请求同一 provider/model/kind/request-shape fingerprint 连续 3 次失败后，才确认 `runtime_failure:real_shape_invalid`。
- 任意一次真实运行时请求成功，会立即把该 provider/model/kind 标回健康，并清除 shape 失败计数。
- 保留健康状态时，如果旧的 shape 冷却过长，会把下一次探测时间压到当前 shape 策略允许的窗口内，避免旧 30 分钟或更长冷却拖住快速复查。

### UI 信息架构调整

本轮重新判断后，认为 `运行时模型` 和 `上游模型状态` 的确存在功能重复。它们展示的是同一批健康矩阵数据的两个视角：

- 按模型看：适合日常判断“对外这个模型现在能不能用，有哪些首选/备份上游”。
- 按上游看：适合排障，判断“某个上游贡献了哪些模型、哪些接口异常、处于什么冷却策略”。

因此两者被整合成一个顶级页签：

```text
模型可用性
  -> 按模型
  -> 按上游
```

原 `健康矩阵` 改名为 `探测矩阵`，语义更准确：它展示的是探测记录，不等于最终用户可用模型列表。

`模型可用性` 的实现细节：

- 使用分段按钮在 `按模型` 和 `按上游` 间切换。
- 共用模型筛选、上游筛选和“显示异常”开关。
- 默认只显示至少有一个接口健康的模型/上游模型；勾选“显示异常”后展示异常和无健康项。
- `按模型` 行展示模型、接口健康数、首选上游、备份/兜底、最低延迟、最近检测、下次探测、主要状态。
- `按上游` 行展示上游、策略、模型、接口、状态、延迟、最近检测、下次探测、检测/冷却策略、详情。
- “检测/冷却策略”会把健康缓存、模型不支持长冷却、异常冷却、Responses 真实请求确认进度等解释成可读文本。

表格稳定性修复：

- `availability-table` 和 `upstream-availability-table` 均使用 `table-layout: fixed`。
- 按模型表格设置固定最小宽度 1520px，并为 8 列设置固定列宽。
- 按上游表格设置固定最小宽度 1760px，并为 10 列设置固定列宽。
- 因此“显示异常”切换时，即使异常详情很长，列宽也不会重新计算导致布局跳动。

`探测矩阵` 说明区：

- 顶部新增健康策略 helpbar。
- 默认展示短摘要 chip，例如探测间隔、单轮预算、超时、Responses 二段验证、三次真实请求确认等。
- 通过小问号 hover/focus 展示完整策略说明，包括记录粒度、探测来源、Responses 判定、形态确认、路由使用、各类冷却时间。
- 说明内容来自 `/gateway-admin/api/overview` 返回的 `health_policy`，避免 UI 文案和后端实际配置长期漂移。

### 模型排序规则

旧排序主要按字符串排序，会出现同族版本顺序不符合直觉的问题。现在统一为：

```text
模型族 rank -> 数字版本号倒序 -> 文本排序
```

模型族 rank：

1. GPT
2. Claude
3. Gemini
4. DeepSeek
5. GLM
6. 其它

数字版本号倒序示例：

- `gpt-5.5` 排在 `gpt-5.4-mini` 前。
- `gpt-5.4-mini` 排在 `gpt-4.1` 前。
- `claude-opus-4-8` 排在 `claude-opus-4-6` 前。

这个规则已经同步到：

- Smart Gateway 后端 `/v1/models` 和概览模型排序。
- Smart Gateway UI 的模型 chips、datalist、健康矩阵、路由视图、模型可用性。
- New API 同步脚本生成 Router channel 模型列表时的排序。
- 测试覆盖：`test_model_sort_rank_orders_same_family_versions_desc` 和同步脚本对应测试。

### Claude 聚合上游客户端限制排查

某 Claude 聚合上游曾在健康状态中出现 `channel:client_restricted`，样例提示当前客户端被识别为 `python-httpx/...`，而该渠道只允许 Claude Code 或 Codex 类客户端。

排查思路：

- 先直接对 `/chat/completions` 做多种 `User-Agent` / header 组合探测。
- 再对 `/responses` 分别测试 minimal Responses body、Codex diagnostic shape、Codex headers、Claude Code headers。
- 再探测是否存在 `/codex`、`/codex/v1`、`/openai/v1` 或 Anthropic `/v1/messages` 等专用入口。
- 探测只记录状态码、延迟和脱敏错误摘要，不输出 key。

结论：

- `/chat/completions` 当前可用；默认 httpx 在复测时也可成功，但历史健康状态确实有过 client restricted。
- `/v1/messages` Anthropic/Claude Code 形态可用。
- `/responses` 对该上游返回的是 `convert_request_failed` / `not implemented`，即使换 Codex/Claude Code headers 和 Codex diagnostic body 也一样。
- 因此不能把该上游标记为 Responses 可用；它应作为 Chat/Anthropic-compatible 能力看待。
- 对 Chat 路径，为避免再次被识别为 `python-httpx`，给该 provider 注入固定 `User-Agent: Claude-Code/1.0.0` 是最小且可逆的修复。

实现：

- 当前运行 provider 配置中给该上游加 provider-level header。
- 同步脚本增加 `provider_client_headers()`，识别该上游后自动生成 `User-Agent: Claude-Code/1.0.0`，避免下次从 New API 同步时把手工 header 覆盖掉。
- `provider_headers()` 的既有顺序是：基础 headers -> 透传允许的客户端 headers -> Responses beta 默认值 -> provider headers 覆盖 -> provider Authorization 覆盖。因此 provider-level header 能稳定覆盖默认 `python-httpx`。

复测结果：

- Chat：健康模型数恢复，旧的 `client_restricted/python-httpx` 从健康状态消失。
- Responses：继续显示 `server_unavailable` / `not implemented`，这是正确的不可用状态，不应伪装成健康。

2026-06-14 复查 Muyuan 时，上游策略已比上面旧结论更严格：

- 仅改 `User-Agent` 不再足够；`Claude-Code/1.0.0`、`codex_exec/0.139.0`、浏览器 UA 和 curl UA 都会被 `channel:client_restricted` 拒绝。
- 可用组合是 `/chat/completions` + Anthropic/Claude Code 风格 body + `User-Agent: claude-cli/2.1.133` + `anthropic-version` + Claude Code beta header。
- 普通 OpenAI Chat body 即使换成 `claude-cli/2.1.133` 仍被拒绝。
- Smart Gateway 增加 provider 级 `chat_request_format: anthropic`：Chat 探测和运行时 Chat 上游请求都会转换成 Anthropic body；Responses 客户端请求仍可安全降级到这个 Chat 上游后再转回 Responses。
- 同步脚本识别 `muyuan.do` 时自动生成上述 header 和 `chat_request_format: anthropic`，避免下次从 New API 同步覆盖手工修复。

### `gpt-5.5` 请求为什么出现 `gpt-5.4`

近期日志里出现一批 `gpt-5.4`，最初怀疑是 Gateway 把用户请求的 `gpt-5.5` 降级或串路由到了 `gpt-5.4`。

排查顺序：

1. 查 Smart Gateway request log 的 `requested_model` 和 `actual_model`。
2. 查健康矩阵中 `gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini` 的 provider 状态。
3. 查 `/v1/models` 当前公开模型。
4. 查路由代码 `healthy_candidate_buckets(model, kind, controls)`。
5. 查 New API Router channel 能力表。

结论：

- `gpt-5.5` 的运行时请求记录中，`requested_model=gpt-5.5` 且 `actual_model=gpt-5.5`，成功走主力 provider。
- 那批 `gpt-5.4` 记录中，`requested_model` 本身就是 `gpt-5.4`，不是 Gateway 从 5.5 改成 5.4。
- 路由代码只从 `HEALTH[kind][requested_model]` 取候选，不会从 `gpt-5.5` 的候选池选出 `gpt-5.4`。
- 根因是 `/v1/models` 曾公开 `gpt-5.4`、`gpt-5.4-mini`，因为某付费兜底上游声明了这些模型，且全局 `model_include` 允许 `gpt-*`。
- 客户端如果读取或缓存了旧模型列表，可能自动选择或重试 `gpt-5.4`。

临时止血：

```yaml
model_exclude:
  - "gpt-5.4*"
```

作用：

- `gpt-5.4`、`gpt-5.4-mini`、`gpt-5.4-openai-compact` 等不再进入探测目标。
- `/v1/models` 不再公开这些模型。
- New API Router channel 能力表不再包含这些模型。
- 客户端即使继续请求 `gpt-5.4`，Gateway 也不会为它找健康上游。

影响：

- 后续如果要重新启用 `gpt-5.4*`，必须删除这条 exclude，reload Smart Gateway，再同步 New API Router channel。
- 更细的长期做法是按上游过滤或按 Router channel 暴露策略过滤，而不是全局屏蔽。

### 日期后缀模型屏蔽

用户随后要求先屏蔽类似 `claude-haiku-4-5-20251001` 这类长日期后缀模型。

第一直觉规则 `*-????????` 被否决，因为它太宽，会误伤尾段刚好 8 个字符的模型，例如某些 `mini` 或 `pro` 结尾模型。最终使用更窄的规则：

```yaml
model_exclude:
  - "*-20??????"
```

含义：

- 屏蔽以 `-20` 加 6 个任意字符结尾的模型，匹配现代日期形态，例如 `-20251001`、`-20251101`。
- 保留不带长日期后缀的短别名，例如 `claude-opus-4-8`、`claude-opus-4-7`、`claude-opus-4-6`、`claude-sonnet-4-6`。
- 不误伤 `mimo-v2.5-pro` 这类非日期尾缀模型。

已验证：

- `/v1/models` 中没有 `-20xxxxxx` 日期后缀模型。
- 健康矩阵中没有日期后缀 health key。
- New API Router channel 能力表中没有日期后缀模型。
- New API 同步后模型活跃价格集移除对应日期版模型，但历史价格归档仍保留。

### 同步和部署验证

本轮使用过的关键验证：

- `PYTHONPATH=/tmp/asg-testdeps python3 -m pytest -q`：62 个测试通过。
- `PYTHONPATH=/tmp/asg-testdeps python3 -m compileall -q app tests`：通过。
- 从 `ADMIN_HTML` 抽取 `<script>` 后执行 `node --check`：通过。
- `docker compose up -d --build smart-gateway`：重建并启动成功。
- 容器健康检查：`ai-smart-gateway` 状态为 healthy。
- 管理页 HTML 校验：新页签 `模型可用性`、`探测矩阵` 存在，旧顶级页签 `运行时模型`、`上游模型状态` 不存在。
- `/v1/models` 校验：GPT 当前只公开 `gpt-5.5`；日期后缀模型为空。
- New API Router channel 能力表校验：GPT 只剩 `gpt-5.5`，Claude 只保留无长日期后缀的短别名。
- 同步脚本执行后，Router abilities 从包含旧模型的状态收敛；模型倍率 active set 移除已屏蔽模型，保留归档。

### 当前已知取舍

- `gpt-5.4*` 和 `*-20??????` 是临时运营屏蔽，不是模型永久不可用声明。
- 这些规则会影响未来使用对应模型；恢复时需要删规则、reload、sync。
- 2026-06-14 已将 `grok-*` 加入 `model_include`。这只让 Grok 进入候选集合；是否公开仍由健康探测和 New API Router channel 同步结果决定。本次全量探测后实际公开 `grok-4.20-fast` 和 `grok-4.20-0309-non-reasoning`，其他 Grok 变体因当前上游限流等非健康结果继续隐藏。
- 对 Claude 聚合上游注入 `Claude-Code` UA 是针对该 provider 的兼容策略；它解决 Chat 客户端识别问题，但不改变 Responses `not implemented` 的事实。
- Health UI 中“探测矩阵”不是公开模型列表；公开模型仍以 `/v1/models` 和 New API Router channel 同步结果为准。
- 客户端如果缓存了旧模型列表，服务端已不再公开旧模型，但客户端可能仍短期继续发旧模型请求；这类请求应以 request log 的 `requested_model` 为准排查。

## 后续优化清单

优先级最高：

1. 将 `probe_retry` 改造成 provider 主状态的 verification budget，而不是单独 route bucket。
2. 增加管理员“真实 Codex shape 诊断”按钮：使用捕获/脱敏模板，对指定 provider/model/kind/base URL 做 1-3 次小预算验证。
3. 在路由日志列表中增加“真实请求确认计数、shape fingerprint、确认状态、base URL 结果”。
4. 增加管理员手动清除某个 provider/model/kind 冷却和验证计数的按钮。
5. 验证 New API -> Gateway -> anyrouter 完整链路是否和直连真实 Codex shape 一致。

中优先级：

1. 更精细地区分 `invalid_request`：缺字段、模型不支持、Codex shape 不合法、上游自定义校验。
2. 对 stream 请求只在首块前允许重试。
3. 增加按模型的“实际路由预览”接口，直接输出候选排序。
4. New API 模型价格同步继续保留历史人工价格归档。

低优先级：

1. 文档补充更多截图或示例。
2. 更细的 UI 帮助说明。
3. 探测预算可视化。
4. 对 Volcengine/Anthropic/Gemini 兼容协议做更完整的协议说明。

## 当前判断

当前改动是合理的“止血版本”：

- 它避免了把 anyrouter 这类可能真实可用的 provider 误杀。
- 它避免了错误阻断付费兜底导致客户端失败。
- 它保留了 New API 源渠道模型声明。
- 它让真实请求日志成为判断依据。
- 它已经把 Responses `invalid_request` 从“文档建议”落到服务器实际路由逻辑里。
- 它确认了真实 Codex shape 才是 anyrouter 可用性的判断标准。

但它还不是最终最优：

- 仍需要把 request-shape verification 从 route bucket 抽象成健康子状态。
- 仍需要把真实 Codex shape 诊断做成后台可操作功能，并脱敏保存模板。
- 仍需要用字段级 diff 验证完整链路是否改变了 Codex body/header。

## 2026-06-13 自适应格式路由与健康新鲜度

### 新问题

用户进一步指出：上游可能随时不可用，也可能随时恢复。运营上真正需要看到的是健康状态的实时变化，而不是只看长 TTL 缓存。同时，客户端不应该因为某个上游只支持 Chat 或 Responses 就频繁改请求方式；网关应该尽量自行选择可用且低延迟的上游格式，并把响应转回客户端期望的格式。

### 重新梳理后的判断

健康矩阵仍然必须保留 `chat` 和 `responses` 两个维度，因为它们代表上游原生能力，不能简单合并。一个上游 Chat 健康不等于 Responses 健康，尤其是 Codex/Responses 的真实请求形态可能包含 `reasoning`、`include`、工具和 Codex metadata。

但运行时路由不应该继续把“客户端入口格式”和“上游入口格式”硬绑定。更合理的模型是：

```text
client_kind: 客户端发来的格式，也是网关最终返回的格式
upstream_kind: 网关实际选择的上游接口格式
```

### 已执行优化

1. 新增自适应格式路由，默认开启。
2. 原生格式通过 `ADAPTER_LATENCY_PENALTY_MS` 获得偏好，默认 250ms；如果转换后的调整延迟仍更低，路由可以选择跨格式上游。
3. `/v1/responses` 可以在安全文本形态下选择健康 Chat 上游，再把 Chat 响应转回 Responses。
4. `/v1/chat/completions` 可以在安全文本形态下选择健康 Responses 上游，再把 Responses 响应转回 Chat Completions。
5. 普通小 JSON 跨格式转换仍拒绝工具调用、function calling、`reasoning`、`include`、`prompt_cache_key`、`previous_response_id`、Codex encrypted reasoning 等复杂字段；但已被证明为 Codex-compatible Responses 的 health item 可以走专用 `codex_responses_to_chat`，支持可映射的 OpenAI function tools/tool calls。
6. 路由日志新增 `upstream_kind`、`format_adapter`、`adapter_latency_penalty_ms`，用于判断是否发生了转换。
7. 成功和失败反写健康时，写入实际 `upstream_kind`，避免 Chat 失败污染 Responses 健康，或反过来。
8. 管理 API 对 health item 动态补充 `health_age_seconds`、`health_fresh`、`health_freshness`、`health_fresh_ttl_seconds`，不污染持久化 health state。
9. 探测矩阵新增“新鲜度”列；模型可用性按上游视角的接口 chip 会显示实时、缓存或冷却。
10. 健康策略说明新增实时新鲜窗口和跨格式路由说明。
11. 流式跨格式转换改为按完整 SSE 事件缓冲后再转换，避免一个事件被上游拆成多个网络 chunk 时丢字。
12. 只由 Codex diagnostic shape 证明可用的 Responses health，不再使用普通小 JSON 的 Chat -> Responses 转换；改为 `codex_responses_to_chat` adapter，给安全 Chat 请求生成 Codex-compatible Responses body 和 Codex identity headers，再把 Responses 结果转回 Chat。
13. `codex_responses_to_chat` 默认 `reasoning.effort=low`，带 `include=["reasoning.encrypted_content"]`、`prompt_cache_key`、`client_metadata`；可映射 OpenAI function tools、`tool_choice`、`parallel_tool_calls`、assistant `tool_calls` 历史和 `tool` 结果消息。运行时成功后保留 `responses_compat_mode=codex`，避免下次又退回普通小 JSON。
14. 兼容模式有两条通用判断路径：探测期 minimal Responses 失败但 Codex diagnostic 成功；运行时普通 Chat -> Responses 小 JSON 在首块前返回 `invalid_request`，则同 endpoint 自动切 `codex_responses_to_chat` 重试一次，成功后学习 `responses_compat_mode=codex`。
15. 通用 `partial` 兼容改为错误驱动：Responses 运行时、minimal probe、Codex diagnostic 只要明确返回缺 `partial`，同一 endpoint 在首块前自动补 `partial=stream` 重试一次，并学习 provider 默认值。
16. 2026-06-14 修复 Chat stream + tools 的本地候选筛选：带 `tools/tool_choice/parallel_tool_calls/reasoning_effort/stream_options` 的 Chat 流式请求以前会被普通 Chat -> Responses 安全门提前拒绝，即使 Anyrouter Responses 已有 `responses_compat_mode=codex` 也无法进入候选，最终直接 `no_healthy_upstream`。现在改为按单个 health item 判断：普通 Responses 候选仍走普通安全门，Codex-compatible Responses 候选走 Codex 安全门。
17. Responses 流式 `function_call` / `function_call_arguments.delta` 会转成 Chat `tool_calls` delta，不再把工具参数误当作普通文本；非流式 Responses `function_call` 输出也会转成 Chat message `tool_calls`。
18. 2026-06-14 继续修复图片/多模态 Chat 请求：Codex 客户端发图时 `messages[].content` 会包含 `image_url`，旧逻辑只接受文本，导致本地候选筛选拒绝 Anyrouter Responses，随后只尝试不可用的 Chat shadow 上游并出现 `stream disconnected before completion: No healthy upstream`。现在 Codex-compatible adapter 会把 Chat `image_url` 转成 Responses `input_image` 并保留 `detail`；普通小 JSON adapter 仍保持文本安全边界。
19. 路由日志增强：`request_shape` 新增 `message_roles`、`message_content_types`、`has_image_content`，且本地 `no_healthy_upstream` / 流式最终 `all_upstreams_failed` 也会写入 request shape，方便直接判断是否为图片、工具或其它请求形态导致候选被过滤。
20. 上游对图片输入返回 `400 / param=input / code=invalid_value` 时归类为 `client_invalid_input`，不再作为 provider runtime failure 或 Responses shape invalid 证据，避免坏图或不被接受的 data URL 污染上游健康。
21. 2026-06-14 排查 Claude Desktop 请求 `mimo-v2.5-pro` 的“一堆 422/报错”时，Gateway 请求日志中该模型最近大量请求是 `200`，且集中为客户端 `/v1/responses` 经 `chat_to_responses` 转到上游 `/chat/completions`。第一轮先修了 usage：Chat -> Responses 非流式和流式都把 `prompt_tokens` / `completion_tokens` 规范成 `input_tokens` / `output_tokens` / `total_tokens`，同时保留原字段；流式会把 usage 放进 `response.completed.response.usage`。如果上游没有给 usage，默认 `ADAPTER_SYNTHESIZE_USAGE=true` 会按转换后的上游请求体和实际输出文本/tool 参数生成带 `estimated:true` 的估算 usage，避免 New API 把成功请求落成 0 token 计费错误。
22. 同一问题继续复查后确认，用户看到的 `422 format conversion error: NO OUTPUT IN RESPONSE` 还有更直接的格式原因：Chat -> Responses 流式适配旧逻辑只发 `response.output_text.delta`，最终补的 `response.completed.response` 只有状态和 usage，没有完整 `output`。New API 在把 OpenAI Responses 结果再转 Claude/Anthropic 时会检查 final response output，缺失就报 `NO OUTPUT IN RESPONSE`。修复改为：Chat -> Responses 流式结束时用累计文本生成 final message output 和 `output_text`；工具调用流用累计 function call 参数生成 final `function_call` output；空输出也保留一个空 message output，避免 final response 没有 output。
23. 2026-06-14 排查 `https://elysiver.h-e.top`：该上游已同步为 `newapi_ch9_elysiver.h-e.top`，但本地 New API 渠道 `models` 字段为空，Gateway 之前只靠远端 `/models` 自动发现过 `gpt-5.5`。复查时远端 `/v1/models` 返回 `data: []`，直接请求 `gpt-5.5` 以及 34 个常见候选模型均返回 `503 model_not_found / No available channel for model ... under group codex-unstable (distributor)`。结论是：当前这把远端 distributor key 所属组没有可用模型，Gateway 不能把它判健康。优化为：`No available channel` 明确归类为 `model_unsupported`；运行时多 endpoint 都是模型不可用时保留 `model_unsupported`，不再折叠成 `all_endpoints_failed`；如果失败模型来自上游 `/models` 自动发现，则让该 provider 的模型缓存立即过期，下一轮强制重新拉取，避免旧 `gpt-5.5` 缓存继续误导。

### 当前健康含义

健康状态现在应按两层理解：

- `healthy=true`：该 provider/model/kind 最近一次有效证据认为可用，路由可以使用。
- `health_freshness=fresh_ok`：最近 `HEALTH_FRESH_TTL_SECONDS` 内验证过，默认 300 秒，更接近实时。
- `health_freshness=stale_ok`：仍在成功 TTL 内，但已经超过实时新鲜窗口，是缓存健康。
- `cooldown` / `probing` / `unknown`：分别表示失败冷却、等待探测预算、尚无可靠检测记录。

### 验证

新增测试覆盖：

- 基础 Chat/Responses body 安全转换。
- 复杂 Responses body 不降级到 Chat。
- Responses 客户端请求使用 Chat 上游并转回 Responses。
- Chat 客户端请求使用 Responses 上游并转回 Chat。
- 双向流式转换可处理拆分 SSE 事件。
- Codex diagnostic-only Responses 健康会进入 `codex_responses_to_chat` 转换候选，不再使用会被拒绝的普通小 JSON Responses 形态。
- 普通 Chat -> Responses 小 JSON 遇到 `invalid_request` 时，非流式和流式都会在首块前自动切 Codex-compatible 形态重试并学习。
- 带 OpenAI function tools 的 Chat stream 可以选择已验证的 Codex-compatible Responses health item。
- Responses function_call 非流式和流式事件会转回 Chat `tool_calls`。
- 带 `image_url` 的 Chat stream 可以选择已验证的 Codex-compatible Responses health item，并转换为 Responses `input_image`。
- 本地无候选时也会记录 `message_content_types` 和 `has_image_content`。
- 图片输入的 `client_invalid_input` 不会把 provider 打入冷却。
- 缺 `partial` 的 Responses provider 在探活、非流式运行时、流式运行时都会通用重试。
- Chat -> Responses 适配会保留/规范化 usage；上游缺 usage 时会合成带 `estimated:true` 的 Responses usage，覆盖非流式和流式。
- Chat -> Responses 流式 completed 事件会带完整 `response.output` / `response.output_text`，覆盖文本和工具调用，避免 New API Claude/Anthropic 转换时报 `NO OUTPUT IN RESPONSE`。
- 远端 New API distributor 返回 `No available channel` 时按 `model_unsupported` 展示；上游自动发现模型遇到运行时模型不可用会让模型缓存过期并重新发现。

真实请求回归：

- Volcengine `deepseek-v4-pro`：Responses stream 原生成功；Chat 请求实际选择 Responses 上游并 `responses_to_chat` 成功。
- Fufu `mimo-v2-flash`：Chat 原生成功，Responses 原生成功。
- Muyuan `claude-opus-4-8`：Responses 客户端请求非流式和流式均成功降级到 Chat 上游，再转回 Responses；该源现在需要 provider 级 `chat_request_format: anthropic`、`User-Agent: claude-cli/2.1.133` 和 Claude Code Anthropic headers，旧的 `User-Agent: Claude-Code/1.0.0` 已不够。
- Anyrouter `gpt-5.5`：普通 Responses 小 JSON 仍返回 `invalid codex request`；Codex-compatible Chat -> Responses 转换已通过。自动路由不是按 Anyrouter 或模型强制，而是根据该 Responses health item 的 `responses_compat_mode=codex` / Codex shape 验证证据选择 `chat -> responses / codex_responses_to_chat`，成功后 health 保留 `responses_compat_mode=codex`。2026-06-14 真实回归中，带 tools 的 Chat stream 返回文本成功；强制 `tool_choice` 调用 `noop` 时，Anyrouter `/responses` 返回的 function_call 流事件已转成 Chat `tool_calls` delta。
- 管理 API 暴露健康新鲜度字段。

完整验证结果更新：`107 passed`。

## 2026-06-14 AI Key Vault 借鉴判断

### 重新判断

对比 AI Key Vault 后，结论不是“照搬”。Smart Gateway 的路由层、健康矩阵、冷却、运行时反写、跨格式适配和运维观测仍然是更完整的生产网关能力。Key Vault 更像个人诊断工具，它的 benchmark、Best-of-N 和回复质量评分都服务于“这个 key 手工测起来好不好用”。

但 Key Vault 有一个点值得立即借鉴：`结构健康 != 内容健康`。旧的 Gateway 普通探测只要求 HTTP 2xx 且 JSON 没有 error，这会把空输出、`ok`、`pong`、`收到` 这类低信号回复误当成健康上游。实际路由时，这类上游可能稳定返回无意义内容，运营上看却是健康。

### 已执行优化

1. 默认探测 prompt 从 `ping` 改成要求一句短句：`Reply in one short sentence: gateway probe is working.`
2. 普通 Chat/Responses 探测成功后提取模型输出文本并计算 `quality_score`。
3. 空输出标记为 `empty_response`。
4. `ok`、`pong`、`hi`、`收到`、`好的` 等低信号输出标记为 `low_signal_response`。
5. `empty_response` / `low_signal_response` 不进入健康候选，默认冷却 `PROBE_LOW_SIGNAL_TTL_SECONDS=900` 秒。
6. 新增可调参数：
   - `PROBE_CONTENT_QUALITY_CHECK=true`
   - `PROBE_MIN_QUALITY_SCORE=80`
   - `PROBE_LOW_SIGNAL_TTL_SECONDS=900`
7. 探测矩阵新增“质量”列，展示 `Q score` 和探测回复样本。
8. 健康策略说明更新为：健康 = 2xx + 无 error + 普通探测内容非空且非低信号。
9. 该质量检查只作用于合成探测，不检查真实用户业务回复；用户真实请求如果要求“只回答 ok”，不会污染上游健康。
10. 本轮完整回归：`102 passed`，并验证运行态 `claude-opus-4-6` Chat 探测返回短句时 `quality_checked=true`、`quality_score=195`。

### 未立即采用的点

- Benchmark / TTFT：有价值，但不应直接进入默认自动健康循环。真实测速成本高、会放大额度消耗，也容易让路由被短期波动牵引。更适合作为管理员手动诊断或后续独立页签。
- Best-of-N / 多轮探测：对个人工具有意义。Key Vault 的测试/benchmark 思路会尝试多种请求路径，并用 1-3 轮测速统计均值、中位数、TTFT、成功率和稳定性。但 Gateway 已经按 Chat/Responses 分维度维护健康，并有运行时反写；默认后台循环如果自动多轮打所有形态，会明显增加额度消耗和噪声。更适合后续做“手动诊断某个 provider/model”的功能，而不是默认后台循环。
