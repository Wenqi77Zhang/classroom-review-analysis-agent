# 成员 4 生产级媒体、翻译、课件与证据链设计

日期：2026-07-30  
负责人：成员 4  
协作审核：成员 1、成员 3、成员 5  
基线：`main@f2349d6`，并保留成员 4 安全修复 `1b2fcbf`

## 1. 目标

本设计完成 Issue #4 在 PR #14、PR #20 之后的剩余职责：

1. 将单次领取入口扩展为可停止的常驻轮询服务，提供退避、指标、租约隔离和部署编排。
2. 完成英文/中英混合检测、英文原文保留、逐句中文译文和明确的人工编辑边界。
3. 解析 PDF/PPTX 课件，保留页码、页面文字和可定位页面图像引用。
4. 建立视频、逐字稿、译文、课件页和画面证据的任务级索引。
5. 只补计算机/AI、人文社科专业 Skill 与专业证据校验，不覆盖成员 5 的通用实现。
6. 使用第二段非预置远程视频复验完整 Worker 链路，并真实复验 ASR/清理失败后的重试。
7. 向成员 2 提供真实播放器、逐字稿、译文和课件证据；向成员 5 提供证据索引、
   专业规则和稳定失败码。

真实本地翻译模型的选择和下载延后到组长确认之后。除真实模型适配器和真实翻译验收外，
本设计中的接口、阶段编排、测试替身和其他功能不受该确认阻塞。

## 2. 已确认边界

- `worker/` 加工媒体与证据，不生成教学判断。
- 翻译复用现有 `TranscriptSegment.translation`、`translation_language` 和
  `POST /api/internal/tasks/{id}/transcript`，不新增翻译后端接口。
- `agent/skills/common.py`、通用证据检索、冻结 `EvidenceReference` 校验和协调器的通用
  引用检查保持不动。
- 成员 4 只实现 `computer_ai`、`humanities` 和专业 `evidence_gate`。
- 新增接口只服务于当前确实缺失的证据持久化、派生页面图像和 Worker 到 Agent 的阶段交接。
- 视频、完整逐字稿、课件原件、页面图像、模型权重、密钥和预签名 URL 不进入 Git 历史。
- 跨模块 Schema 先更新 `docs/interface-contracts.md`，并在 PR 中请求成员 1、3、5 审核。

## 3. 方案比较

### 方案 A：阶段化常驻 Worker、持久化证据和可替换适配器（采用）

Worker 在一个有效租约内按冻结阶段推进，使用现有 transcript 接口保存原文和译文，使用
最小证据接口保存证据索引，并在完成后由专用交接操作原子切换到 `analyze / queued`。
本地模型、课件解析器和存储客户端均位于适配器边界后。

优点：

- 满足常驻运行、真实状态、失败重试、证据交付和后续模型替换要求。
- 后端继续作为持久化与权限边界，Worker/Agent 不直连 PostgreSQL。
- 每个阶段可单独测试；模型未确认时仍可用确定性测试适配器验证完整契约。

代价：

- 需要新增证据持久化与阶段交接契约，并由跨模块负责人审核。
- 生产级租约 fencing 需要一个每次领取都变化的租约标识。

### 方案 B：单次进程生成本地 JSON，再由成员 2、5 手工读取（不采用）

改动少，但结果不能由账号隔离 API 持久化，进程重启后不可恢复，也不能证明上传不同视频会
产生对应的新证据。它不能满足 GitHub Issue 的真实服务交付条件。

### 方案 C：把翻译、课件和证据全部交给 Agent（不采用）

这会违反 `AGENTS.md` 中“Worker 加工媒体与证据，Agent 只基于证据分析”的边界，也会让
成员 5 在模型调用前拿不到可验证证据。

## 4. 总体架构

```text
ProductionWorker
  ├─ PollLoop：领取、空闲等待、错误退避、优雅停止
  ├─ HeartbeatLease：续租、租约丢失通知、fencing
  ├─ MediaPipeline：下载、FFmpeg、ASR
  ├─ TranslationStage：语言检测、TranslationAdapter、整批 transcript 写回
  ├─ CoursewareStage：PDF/PPTX 解析、页面定位、页面图像派生
  ├─ EvidenceIndexStage：生成并整批写入任务证据
  └─ AnalyzeHandoff：原子交给 analyze 阶段
```

外部边界：

- 后端：任务领取/心跳/状态、transcript、证据、派生资源和阶段交接。
- B2：原始视频/课件和派生页面图像；Worker 只使用限时 URL。
- Agent：读取当前任务证据，应用通用规则和成员 4 专业规则。
- 前端：使用教师 JWT 读取视频限时地址、transcript 和证据索引。

## 5. 常驻轮询、退避、停止和指标

### 5.1 轮询

`run_forever()` 在进程生命周期内重复调用单次领取逻辑：

- `204` 或空响应代表正常空闲，等待 `WORKER_POLL_INTERVAL_SECONDS` 后再领取。
- 成功领取并完成任务后立即继续下一次领取。
- 后端连接、超时和 5xx 使用 `1、2、4、8……60` 秒的上限指数退避，并加入可注入的
  随机抖动；下一次成功 HTTP 响应后重置退避。
- 401/403 视为不可自行恢复的部署配置错误，停止进程并返回非零。

时钟、等待和随机源都可注入，单元测试不真实睡眠。

### 5.2 优雅停止

SIGINT/SIGTERM 触发全局停止事件：

- 不再领取新任务。
- 已领取任务在下一个安全检查点停止。
- 停止或租约丢失后不再写状态、transcript、证据或派生资源。
- 任务保持可由租约过期机制重新领取；不把部署滚动更新伪造成业务处理失败。

### 5.3 指标

Worker 暴露独立指标端口和健康状态，指标只使用固定标签：

- claim 总数、空闲轮询数、claim 失败数；
- 各阶段成功/失败数和处理秒数；
- heartbeat 成功/失败数；
- 租约丢失、业务重试和清理失败数；
- 当前是否就绪、是否正在处理任务。

标签只允许阶段和稳定错误码，不包含任务 ID、账号 ID、原文、文件名、路径、URL 或令牌，
防止高基数和隐私泄漏。

## 6. 租约 fencing 与安全重试

仅有 `worker_id + lease_expires_at` 不能防止旧 Worker 在同名实例重新领取后写回。后端在
每次领取时生成新的 `lease_id: UUID`，并保存到任务：

- `InternalTaskClaim` 返回 `lease_id`。
- heartbeat、Worker 状态写入、transcript 写入、证据写入、派生资源登记和 handoff
  均携带 `worker_id + lease_id`。
- 后端同时校验任务仍为 `running`、worker 匹配、lease_id 匹配且未过期。
- 任一条件失败返回 `STATE_CONFLICT`；Worker 立即停止，不再尝试补写失败状态。
- Agent 写 `analyze` 状态不使用 Worker 租约。

业务阶段失败在仍持有有效租约时写 `FAILED` 和稳定错误码。教师调用现有 retry 接口后，
任务回到相同阶段的 `QUEUED`。由于现有内部 API 没有 Worker transcript 读取接口，后段
重试会从当前原始资产重新构建所需中间结果，但只回写当前及后续阶段，绝不把数据库阶段
倒退。这一取舍避免为翻译新增后端接口，代价是后段重试会重新执行必要的 FFmpeg/ASR。

## 7. 翻译设计

### 7.1 接口

`TranslationAdapter` 只接收原文批次和明确语言方向，返回与输入等长的译文批次及模型版本。
阶段层负责超时、停止检查、长度一致性和 Schema 校验，适配器不接触数据库或任务状态。

实现分两层：

- `FakeTranslationAdapter`：只用于单元/集成测试，输出明确可识别的确定性译文。
- `LocalTranslationAdapter`：在组长确认模型后实现；模型 ID 和 revision 必须固定，
  模型缓存不入 Git。

### 7.2 语言与逐句边界

每个 ASR 片段按 Unicode 字符和英文词边界分类为 `zh`、`en`、`mixed` 或 `other`：

- `zh`：保留原文，`translation=None`。
- `en`：保留英文原文，生成逐句中文译文。
- `mixed`：保留完整原文；翻译器处理该句英文语义，返回与原片段一一对应的中文译文。
- `other`：不伪装为英文；若任务明确要求双语而无法处理，则稳定失败。

任何译文都不覆盖 `text`、`start_ms`、`end_ms` 或 `speaker`。整批写回仍使用
`InternalTranscriptWrite`；写回响应由 Worker 校验后才推进阶段。

### 7.3 编辑边界

Worker 只在任务处于媒体处理阶段时生成机器译文。任务交给 `analyze` 后，教师通过现有
逐字稿编辑接口修改内容；常驻 Worker 不再领取该任务，因此不会覆盖人工编辑。新视频必须
创建新任务，不复用旧任务的译文。

### 7.4 模型确认门禁

组长确认前不下载权重、不加入真实模型运行依赖、不声称真实翻译通过。候选顺序：

1. `Helsinki-NLP/opus-mt-en-zh@408d9bc410a388e1d9aef112a2daba955b945255`
   （Apache-2.0，PyTorch 权重约 312 MB，推荐）。
2. `facebook/m2m100_418M@55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`
   （MIT，PyTorch 权重约 1.94 GB）。
3. `facebook/nllb-200-distilled-600M@f8d333a098d19b4fd9a8b18f94170487ad3f821d`
   （CC-BY-NC-4.0，约 2.46 GB，官方不建议生产使用，本项目不推荐）。

## 8. 课件解析与页面引用

### 8.1 解析

- PDF：逐页提取文字，保留原始一基页码。
- PPTX：逐幻灯片提取文本框、表格和备注中的可见文字，幻灯片序号作为一基页码。
- 加密、损坏、超页数、超解压比例或不受支持文件稳定失败，不返回部分成功。
- 页面没有可提取文字时仍保留页码，并仅在真实页面图像生成成功时提供图像引用。

解析器通过 `CoursewareParser` 协议隔离。生产依赖放入 Worker 可选依赖，不拖入纯后端 CI。

### 8.2 页面图像

为满足页码/截图引用：

- PDF 页面通过受控渲染器生成限制尺寸的 PNG。
- PPTX 先由无界面 LibreOffice 转为 PDF，再使用同一受控渲染器生成 PNG。
- 每个外部进程都有超时、输出目录限制和文件大小上限。
- Worker 使用新的“派生资源预签名 → 无鉴权 PUT → 后端 HEAD complete”最小接口把 PNG
  存入私有 B2；不持有长期存储密钥。
- 后端保存派生资源归属和 object key；证据只保存派生资源 ID，不保存预签名 URL。
- 成员 2 使用现有下载 URL 能力取得短期页面图像地址。

如果部署缺少渲染器，课件阶段以稳定错误码失败；不得伪造 `image_ref`。

## 9. 证据索引

### 9.1 数据

任务级证据项包含：

- `id`：由任务、来源、定位信息和内容摘要确定性生成；
- `task_id`、`owner_id`：由后端依据任务填写，Worker 不能自报归属；
- `asset_id` 和可选 `transcript_segment_id`；
- 冻结的 `EvidenceReference`；
- 必要的 `text`、可选 `translation`；
- 仅含非敏感处理版本和领域标签的 `metadata`。

来源规则：

- 视频：`asset_id + start_ms + end_ms`；
- 逐字稿：持久化 segment ID、同一时间范围、原文和可选译文；
- 课件：`asset_id + page_no`，可选页面图像派生资源 ID；
- 画面：真实帧时间或真实图像资源 ID，二者至少一个。

### 9.2 API 与持久化

新增三个最小端点：

- Worker 整批替换：`POST /api/internal/tasks/{id}/evidence`；
- Agent 按当前任务读取：`GET /api/internal/tasks/{id}/evidence`；
- 教师按当前账号读取：`GET /api/tasks/{id}/evidence`。

写入在单个事务中先校验全批次，再替换旧批次。任一项越权、未知资源、时间越界、页码非法
或 Schema 无效时整批拒绝，不留下半批结果。读取按 `owner_id + task_id` 隔离，跨账号统一
返回 404。

不同任务使用不同证据 ID；相同任务、相同输入和相同处理版本重跑保持幂等。

## 10. Worker 到 Agent 的交接

新增固定目标的 handoff 操作，不允许 Worker 自由指定任意阶段：

`POST /api/internal/tasks/{id}/handoff-to-analysis`

后端仅在以下条件全部满足时原子执行：

- 调用者持有当前有效 Worker 租约；
- 当前阶段为 `build_evidence_index / running` 且进度完成；
- 当前任务已有至少一条合法证据；
- 双语任务范围内的英文/混合片段均有中文译文；
- 所有证据资源属于同一 owner 和 task。

成功后写为 `analyze / queued`，清除 Worker 租约并追加 TaskEvent。现有 claim 端点按服务身份
限制可领取阶段：Worker 不能领取 `analyze`，Agent 只能领取 `analyze`。成员 5 负责 Agent
常驻运行器；成员 4 提供并验证交接契约。

## 11. 专业 Skill 与证据门禁

### 11.1 保留通用实现

不修改通用 Skill 的课堂结构、提问、等待、例证和总结规则；不削弱 Schema 至少一条证据、
证据 ID 存在、账号/任务范围、时间范围和双语范围校验。

### 11.2 计算机/AI

`computer_ai` 规则要求：

- 区分概念定义、算法步骤、代码/公式讲解、演示结果和教学建议。
- 声称代码执行、界面操作或模型输出时必须引用真实视频/画面或课件页；仅凭术语出现不能
  推断演示成功。
- 对概念准确性或步骤完整性的判断必须同时给出原文/课件证据和明确判断条件。
- 不从识别出的技术词汇推测教师水平或学生掌握程度。

### 11.3 人文社科

`humanities` 规则要求：

- 区分原文事实、文本解释、论证结构、价值判断和教学建议。
- 解释观点、修辞或论证关系时必须引用课堂原文或课件页，不把模型常识当课堂证据。
- 不推测教师/学生立场、动机、情绪或身份。
- 争议性内容保持原文语境和时间/页码定位，不把截断片段扩写为确定结论。

### 11.4 专业 evidence gate

专业门禁在通用校验之后执行：

- 没有时间、原文、课件页或真实画面来源的候选结论拒绝。
- 引用类型与专业主张不匹配时拒绝。
- 需要英文原文的候选引用缺少原文或逐句译文时拒绝。
- 失败使用稳定专业错误码，不修改通用错误码语义。

## 12. 稳定错误码

在现有 Worker 错误码基础上增加：

- `TRANSLATION_UNAVAILABLE`
- `TRANSLATION_TIMEOUT`
- `TRANSLATION_SCHEMA_INVALID`
- `UNSUPPORTED_LANGUAGE`
- `COURSEWARE_UNSUPPORTED`
- `COURSEWARE_PARSE_FAILED`
- `COURSEWARE_RENDERER_NOT_FOUND`
- `COURSEWARE_RENDER_FAILED`
- `DERIVED_ASSET_UPLOAD_FAILED`
- `EVIDENCE_INDEX_INVALID`
- `EVIDENCE_WRITE_FAILED`
- `LEASE_CONFLICT`
- `HANDOFF_REJECTED`

每个错误映射到冻结平台 `ErrorCode` 和不含路径、URL、原文或上游异常的公开消息。原始诊断
只允许进入本地受控调试日志，默认日志仍须脱敏。

## 13. 部署编排

- 新增独立 Worker 容器定义和 compose profile，不把 Worker 塞进后端进程。
- Worker 镜像使用 Python 3.13，安装 FFmpeg、受控课件渲染器和 Worker 可选依赖。
- 服务令牌只来自环境/部署密钥；命令行不接受令牌。
- 模型缓存使用独立卷并被 Git 忽略；模型未确认时不预取权重。
- 配置 poll interval、backoff 上限、lease、heartbeat、阶段超时、工作目录、指标端口和
  最大课件页数。
- 健康检查证明进程和轮询线程存活；就绪检查在鉴权配置缺失时失败。
- `restart: unless-stopped` 只负责进程恢复，任务正确性由租约 fencing 和幂等写入保证。

## 14. 测试与验收

### 14.1 单元测试

- 轮询：204、立即继续、退避、抖动上限、恢复重置、SIGTERM。
- 租约：周期 heartbeat、旧 lease_id 拒写、停止后零持久化。
- 翻译：中/英/混合检测、逐句对齐、原文保留、批次长度错误、超时和稳定错误码。
- 课件：运行时生成的合规/损坏 PDF 与 PPTX、页码、文字、渲染超时和清理。
- 证据：所有来源类型、确定性 ID、越界/未知资源、整批原子拒绝和跨任务隔离。
- 专业规则：计算机/AI 与人文社科正反例；通用 Skill 结果保持不变。
- 指标：只出现固定标签，不泄漏任务、文本、路径或 URL。

### 14.2 集成测试

- PostgreSQL 真实迁移和账号隔离。
- Worker claim → heartbeat → transcript → evidence → handoff。
- B2/MinIO 派生页面图像预签名、PUT、HEAD complete、下载与清理。
- 相同任务幂等重跑；不同任务产生不同逐字稿和证据。
- 旧租约、过期租约和两个 Worker 竞争时只有当前持有者能写。

### 14.3 真实验收

- 使用第二段非预置、来源和许可已记录的视频执行完整远程链路。
- 与第一段比较任务 ID、逐字稿摘要、证据摘要和状态事件，证明未复用结果。
- 人为使 ASR 适配器失败一次，经现有 retry API 恢复并成功。
- 人为使清理失败一次，确认任务失败、错误可见、重试后零残留。
- 使用许可清楚的公开课件验证 PDF/PPTX；若课件不对应两段视频，文档明确标为解析能力
  样例，不冒充原视频配套课件。
- 模型确认后使用获授权英文样例运行真实逐句翻译；在此之前只记录测试适配器结果，
  不声称真实翻译通过。

## 15. 交付

向成员 2：

- 视频 asset ID 和取得限时下载 URL 的现有接口；
- 真实 `TranscriptRead`，含时间戳、英文原文和逐句译文；
- `GET /api/tasks/{id}/evidence` 契约与脱敏示例；
- 课件 asset/page 和页面图像派生资源定位方式。

向成员 5：

- 内部证据读取接口；
- `computer_ai`、`humanities` SkillSpec；
- 专业 evidence gate、稳定错误码和 handoff 契约；
- 一组通过/拒绝样例，不包含完整课堂原文。

仓库记录：

- `docs/interface-contracts.md`、Worker/Agent 模块指南和当前进度；
- `tests/fixtures/fixture-catalog.md` 的来源、许可、访问日期、参数和脱敏摘要；
- `tests/manual/failure-and-retry-record.md` 的真实失败与恢复；
- `reports/contributions/member-4.md` 和 `docs/ai-collaboration-log.md`；
- PR 描述中的真实测试命令、结果、限制和跨成员审核请求。

## 16. 完成判断

本轮只有同时满足以下条件才可声明成员 4 完成：

1. 常驻 Worker 在空闲、服务异常、停止和租约丢失情况下行为可复验。
2. 两段不同远程视频产生不同任务、逐字稿、证据和状态记录。
3. 英文样例保留英文原文，并在模型确认后具有真实逐句中文译文。
4. PDF/PPTX 产生真实页码、文字和页面图像引用。
5. 每条交给 Agent 的证据都能回到视频时间、原文、课件页或真实画面。
6. 无合法来源的专业结论被拒，通用 Skill 与通用门禁没有被覆盖。
7. ASR 和清理失败均留下稳定错误、可执行重试记录和成功恢复证据。
8. 原始媒体、完整逐字稿、模型、密钥、预签名 URL 和私人信息均未进入 Git。

