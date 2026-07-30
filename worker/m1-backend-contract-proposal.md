# M1 Worker 证据写入、交接与重试契约提案

状态：**提案，尚未冻结**
提案方：成员 4
Schema、迁移、权限、路由与事务实现负责人：成员 3

本文只描述 Worker 联调所需的后端保证，不是已冻结接口，也不授权成员 4 修改
`backend/`。成员 3 审核并冻结前，Worker 只保留内存证据草稿，不执行证据持久化或
Worker → Agent 交接。

## 1. 当前实现与缺口

当前 `main` 已有：

- `POST /api/internal/tasks/claim`
- `POST /api/internal/tasks/{task_id}/heartbeat`
- `PATCH /api/internal/tasks/{task_id}/state`
- `POST /api/internal/tasks/{task_id}/transcript`
- 教师侧 `POST /api/tasks/{task_id}/retry`

当前领取响应只有租约到期时间，没有可 fencing 的 `lease_id`。状态与逐字稿写入也没有
携带租约代次，因此同一 `worker_id` 的旧进程可能在任务被重新领取后继续写入。当前重试
只把 `status` 改回 `queued`，不把阶段显式回退；如果 Worker 在后段失败后偷偷重跑
FFmpeg/ASR，事件记录会与真实执行不一致。当前也没有独立证据草稿的持久化与交接接口。

## 2. 必须冻结的不变量

1. Worker 的状态、逐字稿、证据和交接写入都必须同时满足：任务为 `running`、租约未过期、
   `worker_id` 匹配且 `lease_id` 匹配。
2. 每次首次领取或过期重领都生成新的不可预测 `lease_id`；旧 `lease_id` 永久失效。
3. Worker → Agent 交接成功后，Worker 不得替换逐字稿或证据。
4. 证据整批重写必须产生新版本或 append-only 审计事件；不得静默覆盖。
5. 已被 Agent 结论引用的证据版本不得静默删除或改变定位信息。
6. 交接必须在一个事务中验证证据定位、原文和双语完整性，再把任务置为
   `analyze / queued` 并释放 Worker 租约。
7. 任何 transcript 相关失败的教师重试都显式回到 `transcribe / queued`，并记录旧阶段、
   新阶段、旧证据版本和重试次数；不得保持后段阶段却重跑 FFmpeg/ASR。
8. owner/task 隔离沿用现有约束；跨账号读取统一表现为 404，内部服务也不能把另一个任务的
   asset、segment 或 evidence 绑定进当前任务。
9. `lease_id` 冻结前 M1 只部署一个 Worker，不宣称多 Worker 并发安全。

## 3. 非权威示例结构

以下字段名和路由仅供成员 3 评审，均为“提案—未冻结”。

### 3.1 领取与续租

领取响应建议增加：

```json
{
  "task_id": "uuid",
  "stage": "transcribe",
  "lease_id": "opaque-random-token",
  "lease_expires_at": "2026-07-30T12:00:00Z"
}
```

heartbeat、state、transcript、evidence 和 handoff 请求建议统一携带
`worker_id + lease_id`。`lease_id` 不进入日志、任务事件、错误详情或浏览器响应。

### 3.2 证据草稿整批写入

建议路由：

```text
PUT /api/internal/tasks/{task_id}/evidence-draft
```

示例请求：

```json
{
  "worker_id": "media-worker-1",
  "lease_id": "opaque-random-token",
  "base_version": 0,
  "items": [
    {
      "source_type": "transcript",
      "asset_id": "video-asset-uuid",
      "source_index": 0,
      "start_ms": 0,
      "end_ms": 800,
      "page_no": null,
      "image_ref": null,
      "text": "original text",
      "translation": "逐句译文",
      "evidence_key": "deterministic-worker-uuid"
    }
  ]
}
```

示例响应：

```json
{
  "task_id": "uuid",
  "evidence_version": 1,
  "item_count": 1
}
```

后端应以 `task_id + source_index` 解析真实 `segment_id`，不能信任 Worker 自造
`segment_id`。`base_version` 必须做乐观并发检查。落库后返回的证据 ID/版本才是 Agent
可引用身份；Worker 的确定性 UUID 只用于同一批次幂等，不替代数据库主键与版本审计。

### 3.3 Worker → Agent 交接

建议路由：

```text
POST /api/internal/tasks/{task_id}/worker-handoff
```

示例请求：

```json
{
  "worker_id": "media-worker-1",
  "lease_id": "opaque-random-token",
  "evidence_version": 1
}
```

成功响应必须代表同一事务已经完成：

- 当前 lease 校验成功；
- 每条证据都有合法时间、原文、课件页或画面定位；
- `analysis_contract.bilingual_required=true` 时，所有要求双语的逐字稿证据都有译文；
- 证据版本被冻结供本次 Agent 使用；
- task 变为 `analyze / queued`；
- Worker lease 被释放。

## 4. 写入与重试结果表

| 场景 | 预期 HTTP/错误码 | 数据结果 |
|---|---|---|
| 有效 lease 首次写证据 | 200/201 | 创建版本 1，保留写入事件 |
| 同一 lease、同一幂等键重放 | 200 | 返回原版本，不重复创建 |
| lease 已过期或 `lease_id` 不匹配 | 409 `STATE_CONFLICT` | 零状态、逐字稿、证据写入 |
| 交接后 Worker 再覆盖 | 409 `STATE_CONFLICT` | 冻结版本不变 |
| `base_version` 过期 | 409 `STATE_CONFLICT` | 不覆盖新版本 |
| 删除已被结论引用的证据 | 409 `STATE_CONFLICT` | 引用和证据均保留 |
| transcript 相关失败后重试 | 200 | 显式改为 `transcribe / queued`，追加旧/新阶段事件 |
| 跨账号绑定 asset/segment/evidence | 404 `RESOURCE_NOT_FOUND` | 不泄露资源是否存在 |
| 交接时缺原文、定位或必要译文 | 422 `SCHEMA_INVALID` | 保持 Worker 阶段，不进入 analyze |

## 5. 成员 3 验收测试请求

- 两个并发领取者中，只有最新 `lease_id` 可以 heartbeat 和写入。
- 旧租约对 state、transcript、evidence、handoff 四类写入全部返回 409。
- evidence 版本冲突不会部分覆盖；事务回滚后旧版本完整可读。
- handoff 的校验、版本冻结、阶段迁移和租约释放具备原子性。
- 教师重试事件同时记录 `from_stage`、`to_stage=transcribe`、`retry_count` 和旧证据版本。
- 已引用证据的删除/替换被拒绝，历史结论仍可回放到原证据版本。
- 两账号测试覆盖读取 404 与跨任务引用拒绝。

成员 3 冻结后，成员 4 再补 `HttpJobStore` 客户端契约测试、真实证据写入、交接、第二段
远程视频与失败重试复验。
