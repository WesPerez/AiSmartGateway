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

- 固定探活仍不能证明真实 Codex 请求是否可用。
- curl 伪造的请求不等于真实 Codex CLI 请求。
- 真正应该使用实际用户请求形态做 bounded verification。

建议下一步实现：

1. 当 Responses 上游在真实请求上返回 `invalid_request`，且失败发生在 stream 第一块之前，记录为 `shape_verification_needed`。
2. 对同一 provider/model/kind/endpoint/request-shape-class 做最多 3 次真实形态确认。
3. 三次可以在短时间窗口内跨真实请求累计，而不是每个用户请求都立即打三次。
4. 如果三次都返回同类 `invalid_request`，标记为 `real_shape_invalid` 并短冷却。
5. 如果任一次成功，立即标记健康并清除该 shape 的失败计数。
6. 对非幂等或已经开始 stream 的请求不重放。
7. 对失败前没有任何 token 输出的 400，可以尝试同 provider 的备用 base URL。

这比“固定探活失败就判死”和“永远不判死”都更合理。

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

- 真实 Codex 客户端请求经过 New API 后，Gateway 日志里是否能看到完整 body 和 headers。
- anyrouter 在真实 Codex 请求形态下是否恢复成功。
- 如果仍失败，是否需要请求体字段级 diff，而不是继续靠固定探活。

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

- 添加过多个新上游和 key，包括共享类、Volcengine Coding、anyrouter、muyuan、付费兜底等。
- 清理过重复 Volcengine 配置、无用 key、重复或多余上游。
- 确认付费上游应作为兜底。
- 确认 anyrouter 和 muyuan 可作为主力或高优先级候选。
- 结论：真实上游不再直接写死到公开文档，统一在 New API 渠道中管理，Smart Gateway 通过 `gateway-source` 同步。

### Volcengine Coding

- 官方说明有两个 base URL：一个兼容 Anthropic 协议，一个兼容 OpenAI 协议。
- 曾经出现官方有 GLM 新版本但系统只识别旧 GLM 的问题。
- 结论：Volcengine 不能只信 `/models`，应通过官方声明模型族和过滤规则选择最新 deepseek flash、deepseek pro、GLM。
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
- UI 显示优化。
- 测试覆盖。

## 后续优化清单

优先级最高：

1. 将 `probe_retry` 改造成 provider 主状态的 verification budget，而不是单独 route bucket。
2. 在路由日志列表中增加“真实请求确认计数、shape fingerprint、确认状态”。
3. 增加管理员手动清除某个 provider/model/kind 冷却和验证计数的按钮。
4. 用真实 Codex 请求日志继续验证 anyrouter 通过 New API + Gateway 的完整链路。

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

但它还不是最终最优：

- 仍需要把 request-shape verification 从 route bucket 抽象成健康子状态。
- 仍需要用真实 Codex 请求日志验证 anyrouter 通过 New API + Gateway 的完整链路。
