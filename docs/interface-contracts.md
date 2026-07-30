# 跨模块接口契约

**版本：v1（Day 1 冻结）｜冻结日期：2026-07-26｜维护人：成员 3**

## 实现状态（如实标注）

| 内容 | 状态 |
|---|---|
| Pydantic Schema（`backend/app/schemas/`） | **已实现**，可导入、含校验器并纳入后端/Agent/Worker 测试 |
| 端点路由（`backend/app/api/`） | **部分实现**：认证、课程/课堂、上传、任务、逐字稿、分析、教师复核/历史与报告读取/保存可调用；报告导出尚未实现 |
| ORM 模型与迁移 | **已实现基础持久化**：15 张业务/关联表、Alembic 首迁移与 PostgreSQL 隔离测试 |
| TypeScript 类型（`frontend/src/types/contracts.ts`） | **部分实现**：已覆盖前端当前上传和任务链路；逐字稿、真实结论、复核历史和报告仍待同步 |

权威来源是代码而不是本文件的散文：字段级细节以 `backend/app/schemas/` 为准，本文件负责
说明约定、枚举取值和跨模块责任。两者不一致时以代码为准，并由成员 3 立即回写本文件。

## 核心实体

- `User`、`Course`、`Classroom` → `backend/app/models/identity.py`
- `Asset`、`ProcessingTask`、`TaskEvent`、`TranscriptSegment` → `backend/app/models/processing.py`
- `EvidenceReference`、`AnalysisConclusion`、`ReviewDecision`、`Report`、`AuditEvent`
  → `backend/app/models/review_report.py`

## 通用约定

- **主键统一 `UUID`**。ID 会出现在前端 URL 与对象存储 key 中，自增整数会泄漏数据总量，
  也让跨账号猜 ID 变容易。
- **时间统一 UTC `datetime`**；音视频位置统一**毫秒整数**（`start_ms` / `end_ms`），
  不用浮点秒——前端要从结论精确跳回播放器，浮点累加会漂移。
- **每张业务表带 `owner_id`**，不靠 `classroom_id` 间接推导归属。账号隔离由仓储层
  无条件拼 `WHERE owner_id = :current_user` 保证，而不是靠每个路由自己记得检查。
- 请求体 Schema 一律 `extra="forbid"`：前端字段名拼错要立即报错，不能静默丢弃。
- 分页参数统一 `limit`（默认 50，上限 200）+ `offset`。上限是硬要求，否则一次
  `?limit=1000000` 就能把数据库和内存拖死。

## 枚举取值（跨模块必须逐字一致）

| 枚举 | 取值 |
|---|---|
| `AssetKind` | `video` \| `courseware` \| `transcript` |
| `UploadStatus` | `pending` \| `uploaded` \| `failed` |
| `PrivacyMode` | `local` \| `cloud` |
| `TaskStatus` | `pending` \| `queued` \| `running` \| `succeeded` \| `failed` \| `cancelled` |
| `TaskStage` | `uploaded` \| `extract_audio` \| `segment` \| `transcribe` \| `translate` \| `parse_courseware` \| `build_evidence_index` \| `analyze` |
| `ConclusionType` | `fact` \| `judgment` \| `suggestion` |
| `ReviewStatus` | `pending` \| `accepted` \| `modified` \| `rejected` |
| `ReviewAction` | `accept` \| `modify` \| `reject` |
| `EvidenceSourceType` | `video` \| `transcript` \| `courseware` \| `frame` |
| `ReportExportFormat` | `markdown` \| `html` \| `pdf` |

`TaskStage` 的取值与成员 4 的 `worker/stages/` 文件名一一对应，改名要两边同步。

## 强制字段

所有分析结论至少包含：`id`、`type`、`content`、`evidence_refs`、`review_status`、
`created_at`、`trace_id`。

证据引用至少包含来源类型和可定位信息，并由 Schema 校验器强制：

| `source_type` | 必需定位信息 |
|---|---|
| `video`、`transcript` | `start_ms` **且** `end_ms`（且 `end_ms > start_ms`） |
| `frame` | `start_ms` 或 `image_ref` 之一 |
| `courseware` | `page_no` 或 `image_ref` 之一 |

`evidence_refs` 最少 1 条。无证据结论在 Schema 层就被拒（HTTP 422），Agent 无法绕过。

## 统一错误格式

所有非 2xx 响应：

```json
{ "error": { "code": "PERMISSION_DENIED", "message": "…", "details": {}, "trace_id": "…" } }
```

前端按 `code` 分支处理，**不解析 `message`**（`message` 面向教师、会改文案）。

| HTTP | `code` | 用途 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 参数不合法 |
| 401 | `UNAUTHENTICATED` | 未登录或令牌失效 |
| 403 | `PERMISSION_DENIED` | 资源属于你，但当前状态不允许该操作 |
| 404 | `RESOURCE_NOT_FOUND` | 不存在，**或不属于当前账号** |
| 409 | `STATE_CONFLICT` | 状态机不允许，如对 `running` 任务重试 |
| 413 | `PAYLOAD_TOO_LARGE` | 超出文件或请求体上限 |
| 422 | `SCHEMA_INVALID` | 结构校验失败，含无证据结论被拦 |
| 429 | `RATE_LIMITED` | 限流 |
| 500 | `INTERNAL_ERROR` | 未预期错误 |
| 503 | `UPSTREAM_UNAVAILABLE` | 对象存储 / ASR / 模型不可用 |

**安全取舍**：跨账号访问已存在资源返回 **404 而不是 403**，避免用状态码泄漏"该 ID 存在"。
403 仅用于"资源是你的但状态不允许"。

`trace_id` 与成员 5 的 `agent/observability/tracing.py` 共用同一 ID，可把前端提示、
后端日志与 Agent Trace 串成一条链。

**上游可通过 `X-Trace-Id` 请求头透传，但该值是不可信输入**，会进日志、错误响应体与审计
记录。后端强制约束：字符集 `[A-Za-z0-9_-]`、长度 1–128。不满足时**静默生成新 ID**，
而不是返回 400——一个可选头部格式错误不应打断业务链路，且此时尚无可用的 trace_id 去
构造错误响应。无约束会让外部请求塞入超长字符串撑爆日志，或用换行与控制字符伪造日志行
（日志注入）。响应头 `X-Trace-Id` 返回的始终是规范化后的值。

## 任务状态机

```
pending → queued → running → succeeded | failed | cancelled
failed  → queued（重试，retry_count += 1）
succeeded / cancelled 为终态
```

阶段顺序：`uploaded → extract_audio → segment → transcribe → translate →
parse_courseware → build_evidence_index → analyze`

- 非法迁移返回 `STATE_CONFLICT`，不静默改库；允许的迁移表见
  `backend/app/schemas/task.py::ALLOWED_STATUS_TRANSITIONS`。
- **`failed` 不是终态。** 代码中三个集合各有分工，不可混用：
  `TERMINAL_STATUSES = {succeeded, cancelled}`（不可再迁移）、
  `RETRYABLE_STATUSES = {failed}`（可回到 `queued`）、
  `INACTIVE_STATUSES`（两者之并，用于判断"是否还在跑"）。
  一致性由 `test_backend.py` 的不变量测试守住：终态集合中的每个状态，其允许迁移集合必须为空。
- 每次 `(stage, status)` 变更由**后端**追加一条 `TaskEvent`（含 `progress`、`message`、
  `trace_id`）。Worker 不直接写事件表。前端进度条读事件流，因此不需要模拟计时器。
- `lease_expires_at` 到期任务可被重新领取，Worker 进程被杀不会让任务永久卡在 `running`。

## 端点契约

统一前缀 `/api`；`GET /health` 不鉴权，供 `verify.*` 与部署探针使用。

### 对外（教师带 JWT）

| 模块 | 端点 |
|---|---|
| `auth` | `POST /auth/login`、`POST /auth/demo`、`GET /auth/me` |
| `classrooms` | `POST\|GET /courses`、`POST\|GET /courses/{id}/classrooms`、`GET\|PATCH\|DELETE /classrooms/{id}` |
| `uploads` | `POST /classrooms/{id}/uploads/presign`、`POST /assets/{id}/complete`、`GET /assets/{id}/download-url`、`DELETE /assets/{id}` |
| `tasks` | `POST /classrooms/{id}/tasks`、`GET /tasks/{id}`、`GET /tasks?classroom_id=`、`GET /tasks/{id}/events`、`POST /tasks/{id}/retry`、`POST /tasks/{id}/cancel` |
| `transcripts` | `GET /tasks/{id}/transcript`、`PATCH /transcript-segments/{id}` |
| `analyses` | `GET /classrooms/{id}/conclusions`、`POST /conclusions/{id}/review`、`GET /conclusions/{id}/history` |
| `reports` | `GET\|PUT /classrooms/{id}/report`、`POST /reports/{id}/export`、`GET /reports/{id}/export/{fmt}` |

实现边界：`analyses` 已提供结论读取、Agent 内部批量写入、教师复核写入和历史读取。
`reports` 已提供 `GET|PUT /classrooms/{id}/report`；PUT 请求只接受 `title`，报告 Markdown
正文由服务端从当前状态为 `accepted` / `modified` 的本课堂结论生成，客户端不能提交或覆盖
正文。`modified` 结论使用教师的 `reviewed_content`，其余可报告结论使用模型原文。每次保存
或复核状态变化都会重新计算正文和关联，已驳回的结论不得保留在报告中。
`included_conclusion_ids` 按结论创建时间、ID 稳定排序，不依赖数据库关联表的返回顺序。
`POST /reports/{id}/export` 和 `GET /reports/{id}/export/{fmt}` 仍未实现。端点列入冻结
契约不等于已经可以调用。

### 认证、课程与课堂字段（Day 3）

| 端点 | 请求 | 响应 |
|---|---|---|
| `POST /auth/login` | `{email, password}` | `{access_token, token_type, expires_in_seconds, user}` |
| `POST /auth/demo` | 无请求体；仅在服务端配置演示口令时可用 | 同登录响应 |
| `GET /auth/me` | Bearer token | `{id, display_name}` |
| `POST /courses` | `{name, description?}` | `CourseRead` |
| `GET /courses` | 无 | 当前账号的 `CourseRead[]` |
| `POST /courses/{id}/classrooms` | `{title, description?, analysis_contract?}` | `ClassroomRead` |
| `GET /courses/{id}/classrooms` | 无 | 当前账号和课程下的 `ClassroomRead[]` |
| `GET /classrooms/{id}` | 无 | `ClassroomRead` |
| `PATCH /classrooms/{id}` | `title`、`description`、`analysis_contract` 至少一个 | `ClassroomRead` |
| `DELETE /classrooms/{id}` | 无 | 当前返回 `STATE_CONFLICT`；对象清理与删除审计实现后才启用 |

课程名称和课堂名称来自成员 1 已确认的创建课堂页面。授课语言和课堂日期当前仍是可选页面字段，
尚未纳入冻结数据库契约；成员 1 确认其持久化语义后再扩展，不在本轮静默加字段。

登录失败统一返回 `UNAUTHENTICATED`，不区分“邮箱不存在”和“密码错误”。演示账号密码仅从
`DEMO_ACCOUNT_PASSWORD` 读取；未配置时 `/auth/demo` 返回 `PERMISSION_DENIED`，不得使用
硬编码默认密码。

课程当前仅实现创建和列表；课堂实现创建、列表、读取和修改。课堂删除在对象存储清理及
不含敏感值的删除审计完成前明确返回 `STATE_CONFLICT`，不得直接依赖数据库级联删除。
本轮课程/课堂写操作尚未写入 `AuditEvent`，不能描述为已完成审计链路。

### 内部（服务令牌鉴权，**Worker 与 Agent 各持一个，不共用**）

| 端点 | 请求 Schema | 允许身份 | 使用方 |
|---|---|---|---|
| `POST /internal/tasks/claim` | `InternalTaskClaimRequest` → `InternalTaskClaim` | `worker` | 成员 4 |
| `POST /internal/tasks/{id}/heartbeat` | `InternalTaskHeartbeat` | `worker` | 成员 4 |
| `PATCH /internal/tasks/{id}/state` | `InternalTaskStateUpdate` | `worker`、`agent` | 成员 4、5 |
| `POST /internal/tasks/{id}/transcript` | `InternalTranscriptWrite` | `worker` | 成员 4 |
| `POST /internal/tasks/{id}/conclusions` | `InternalConclusionBatchWrite` | `agent` | 成员 5 |

`InternalTaskClaim.assets` 使用 `InternalAssetRead`：在对外 `AssetRead` 字段之外，仅增加后端
即时签发的 `download_url`。该地址限时、限当前对象、只允许 GET，不持久化也不进入日志。
Worker 必须使用不携带 `Authorization` 默认头的独立客户端访问它，严禁把
`WORKER_SERVICE_TOKEN` 转发给对象存储。Worker 下载后核对实际字节数与 `size_bytes`，
并把响应 ETag 与后端上传完成时 HEAD 保存的 `verified_etag` 对照，防止限时 PUT 地址
过期前发生同大小对象替换；无论成功、失败或租约停止都清理本地临时文件。

身份由令牌区分：`WORKER_SERVICE_TOKEN` → `worker`，`AGENT_SERVICE_TOKEN` → `agent`。
两者**必须配置为不同的值**。共用一个令牌意味着 Agent 也能覆盖逐字稿、Worker 也能写入
教学结论，违反最小权限。权威定义见 `backend/app/schemas/task.py::INTERNAL_ENDPOINT_SCOPES`。
服务令牌只能通过部署环境变量或密钥管理器注入，Worker CLI 不提供令牌参数，避免密钥进入
Shell 历史、进程命令行、录屏或报错截图。

`PATCH /internal/tasks/{id}/state` 两个身份都能调，但**可写的阶段不同**：

| 身份 | 可回写的 `stage` |
|---|---|
| `agent` | 仅 `analyze`（`AGENT_WRITABLE_STAGES`） |
| `worker` | 其余全部媒体处理阶段（`WORKER_WRITABLE_STAGES`） |

越界回写返回 `PERMISSION_DENIED`。

**租约隔离门禁**：Heartbeat 只能减少过期概率，不能独立阻止旧 Worker 回写。服务端
`state` 与 `transcript` 写入端点已经合并，但写入请求目前没有携带 `worker_id`，
尚不能完整证明写入者仍是当前租约持有人。PR #14 的 Worker 会在 heartbeat 失败后停止
写入，但跨 Worker 的服务端 fencing（旧租约过期或任务被重新领取后拒绝旧 Worker）
仍须补契约、实现与并发测试，不能宣称已经完成。

这组接口是 `worker/job_store.py` 与 Agent 回写的**唯一**落库入口；Worker 与 Agent
不直连数据库。

**整批替换语义**：`InternalTranscriptWrite` 与 `InternalConclusionBatchWrite` 都是替换而非
追加。换输入或重跑必须产生与新输入对应的结果，追加会让两次运行的内容混在一起
（发布门禁："更换输入后仍出现固定结论"）。已复核的结论不被覆盖。

## 上传链路

「后端签名 → 浏览器直传对象存储 → 后端确认」三步：

1. `POST /classrooms/{id}/uploads/presign` → `PresignResponse`（限时、限对象、限方法）
2. 浏览器 `PUT upload_url`，必须原样带上 `headers`，否则签名不匹配
3. `POST /assets/{id}/complete` → **后端核对通过后**才把 `upload_status` 落为 `uploaded`

**第 3 步不得信任浏览器自报。** 该请求只是"浏览器认为自己传完了"的信号，手工构造即可
发出，对象可能根本不存在或只有 0 字节。标记 `uploaded` 之前，后端必须对对象存储执行
`HEAD` 并核对：

| 核对项 | 拦住什么 |
|---|---|
| object key 存在 | 压根没上传 |
| `size_bytes` 与预签名时登记的一致 | 空上传、截断上传 |
| `content_type` 与登记的一致 | 传了别的类型的文件 |
| 校验值（若对象存储返回）与登记的一致 | 内容被替换 |

**以 HEAD 结果为准写库**，请求体中的 `etag` / `checksum` 只作交叉比对线索。核对不通过返回
`VALIDATION_ERROR`，并把 `upload_status` 落为 `failed`。

视频二进制不经过 FastAPI、不进数据库；数据库只存 `object_key` 与归属。
预签名 URL 属敏感数据：不写日志、不进前端持久化存储、不进仓库。

**对象存储侧必须配置 CORS，否则浏览器直传会被拦**——这是成员 1、2 上传功能的隐性前提。
M1 使用 Backblaze B2，需在其 Bucket 上允许来自 `FRONTEND_ORIGIN` 的 `PUT`；本地 MinIO
替代方案由 compose 的 `MINIO_API_CORS_ALLOW_ORIGIN` 自动处理。

两家供应商的寻址方式不同（MinIO 需 path-style，B2 用 virtual-host），差异必须由后端的
统一 S3 Provider 抽象层吸收；业务层不得直接依赖任一供应商（`main` 的后端完成定义要求）。

## Agent 边界

`InternalConclusionBatchWrite` 中**没有** `review_status` 字段：新结论一律 `pending`。
Agent 不得绕过证据门禁，也不得直接修改教师确认状态。

只有 `review_status ∈ {accepted, modified}` 的结论可进入报告
（`REPORTABLE_REVIEW_STATUSES`）。成员 5 在 Agent 侧过滤，后端在数据层再拦一道——
"未复核或已驳回结论进入报告"是发布门禁的阻断项，值得双重保险。
`review_status=modified` 时报告采用 `reviewed_content`，不是原始 `content`。

## v1 相对阶段 0 草案的变更（**需成员 1、2、4、5 确认**）

1. **`TranslationSegment` 不再是独立实体**，译文合并为 `TranscriptSegment` 上的
   `translation` / `translation_language` 字段。理由：逐句对齐是硬要求，两份独立列表在
   教师插入或删除句子后会错位。影响成员 2（双语列渲染）、成员 4（Worker 写入）。
2. **新增内部接口族 `/api/internal/*`，并配 `WORKER_SERVICE_TOKEN` 与 `AGENT_SERVICE_TOKEN`
   两个独立令牌**。草案未定义 Worker/Agent 的回写入口，不定会导致成员 4、5 各写一套。
   令牌按身份拆分（成员 1 审查意见 4）：Worker 不得写结论，Agent 不得覆盖逐字稿，
   且 Agent 只能回写 `analyze` 阶段的状态。影响成员 4、5。
3. **`.env.example` 新增** `ACCESS_TOKEN_EXPIRE_MINUTES`、`DEMO_ACCOUNT_PASSWORD`、
   `WORKER_SERVICE_TOKEN`、`AGENT_SERVICE_TOKEN`、`OBJECT_STORAGE_USE_PATH_STYLE`。
   预签名有效期统一采用 `main` 已定的 `OBJECT_STORAGE_PRESIGNED_URL_TTL_SECONDS`
   （本分支原用 `PRESIGN_EXPIRE_SECONDS`，同义重名，已废弃）。
4. **`AnalysisConclusion` 增加证据账本字段** `model_name` / `skill` / `prompt_version`
   与教师改写字段 `reviewed_content`。前者服务于"证据账本"亮点，后者用于保留教师成果。
   影响成员 5（写入时提供）、成员 2（展示）。

## 变更规则

任何 Schema 变更必须由成员 3 更新本文件，并由受影响的前端、Worker 和 Agent 负责人确认
（`AGENTS.md` 第 7 条）。变更同时要在本节追加记录，不允许静默改字段。
