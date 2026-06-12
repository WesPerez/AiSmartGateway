# New API 与 Smart Gateway 边界

本文是公开脱敏版说明，不包含真实域名、服务器路径、IP、密钥、日志或上游账号信息。

## 对外入口

公开入口应只暴露 New API：

```text
https://api.example.com/v1
```

客户端 API Key 应在 New API 的令牌页面生成。Smart Gateway 的内部访问 Key 只用于 New API 的路由渠道，不应作为公开客户端 Key 分发。

## New API 负责

1. 用户、令牌、额度、订阅、分组。
2. 渠道管理：新增、删除真实上游 Base URL 和 Key。
3. 模型管理：模型展示、权限、价格和倍率。
4. 对外请求日志：用户、token、扣费、New API channel。

真实上游通道应保持在正常用户分组中，并设置渠道标签 `gateway-source`。

## Smart Gateway 负责

1. 从 New API 同步带 `gateway-source` 标签的源池。
2. 按模型、接口类型和真实上游维护健康矩阵。
3. 按主力、机会、备份、付费兜底策略选择真实上游。
4. 对模型不存在、余额不足、限流、服务异常做冷却。
5. 记录最终真实上游、路由桶、成本层级、失败原因和耗时。

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

## 多 Base URL

同一个上游如果有多个兼容 Base URL，不应拆成多个 New API 渠道，否则同一个额度池会被权重计算成多份。应保留一个逻辑渠道，并在 Smart Gateway provider 内部配置多个 `base_urls`。

## 应急写入

Smart Gateway 直接写 provider 配置的接口默认应保持禁用。正常情况下，所有上游都应从 New API 渠道同步而来。
