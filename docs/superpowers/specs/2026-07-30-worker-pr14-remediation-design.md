# PR #14 Worker 阻断项修复设计

日期：2026-07-30  
分支：`member-4/media-pipeline`  
基线：先合并 `origin/main`，不变基、不强推  
依据：PR #14 最新评审、`AGENTS.md`、`docs/interface-contracts.md`

## 1. 目标与顺序

严格按评审要求逐项完成：

1. 合入最新 `main` 并解决冲突。
2. 区分“媒体阶段完成”和“整个任务成功”，实现任务领取及周期续租。
3. 拒绝非法 ASR 时间戳，不再修补或伪造区间。
4. 让课堂临时媒体清理失败可观察、可重试。
5. 补齐两段真实视频的来源、使用依据和脱敏验收摘要。
6. 对齐设计中的稳定错误码，补齐 `HttpJobStore` 契约测试。
7. 更新 PR 描述与 AI 协作记录，运行全量测试和 CI。

每项完成后先运行对应的窄测试，再进入下一项。最终运行全量测试。视频、音频、模型权重
和完整逐字稿不得进入 Git 历史。

## 2. 基线同步

使用普通 merge 将 `origin/main` 合入当前分支，保留现有提交历史。冲突处理遵循：

- 后端 Schema 和接口文档以最新 `main` 为准，不由成员 4 私自改动。
- Worker 实现和测试保留本分支的真实媒体能力，再按最新契约调整。
- 其他成员在 `agent/`、`frontend/`、认证和课堂 API 中的改动原样保留。
- 不使用 rebase、`reset --hard` 或 force push。

## 3. 阶段交接与租约

### 3.1 状态语义

`transcribe` 成功只代表该阶段完成，不能将整个任务写为终态 `SUCCEEDED`。Worker 将：

- 进入阶段时写 `RUNNING`。
- 保存整批逐字稿后仍写 `RUNNING`、进度 `1.0`，消息明确为“转写完成，等待下一阶段”。
- 只有负责最终媒体阶段的编排器才有权按冻结状态机决定是否进入后续阶段；本次最短
  Pipeline 不宣告整个任务成功。
- 失败时写当前阶段 `FAILED` 并带平台错误码。
- 收到停止信号或任务取消时停止续租，不再写成功状态。

### 3.2 HTTP Runner

保留本地单次入口用于真实视频验证，新增服务运行路径：

- 使用 `HttpJobStore.claim()` 领取 Worker 可处理阶段。
- 根据领取包构造任务输入；对象存储下载尚未实现时明确返回稳定上游错误，不能回退假数据。
- 在 ASR 运行期间以独立 heartbeat 循环续租，间隔小于租约的一半。
- heartbeat 失败会发出停止信号；主流程结束后等待 heartbeat 线程退出。
- 正常完成、失败、停止三条路径都有确定测试，线程不得泄漏。

备选方案是让 Whisper 回调驱动 heartbeat，但现有适配器没有稳定进度回调，会把租约语义
绑死在具体模型上，因此采用独立周期循环。

## 4. 时间戳严格校验

ASR 段在转换为毫秒前必须满足：

- `start_seconds`、`end_seconds` 都是有限数值。
- 起止均非负。
- `end_seconds > start_seconds`。
- 区间不超过真实音频时长。
- 片段按时间单调：后一段起点不得早于前一段起点，且不得与前一段发生倒序重叠。

毫秒舍入后若区间退化，同样拒绝，不补成 1 ms。任何违反返回
`WorkerErrorCode.INVALID_TIMESTAMP`。音频时长由 WAV 头读取；无法读取或时长无效返回
`TRANSCRIPT_SCHEMA_INVALID`，不信任 ASR 最后一个片段作为媒体时长。

备选方案是保留钳位并记录警告，但这会制造不存在的证据区间，因此不采用。

## 5. 清理失败

`cleanup_path()` 保持“目标不存在即成功”的幂等语义，但不再吞掉文件系统错误：

- 删除失败包装为 `WorkerErrorCode.CLEANUP_FAILED`，标记可重试。
- Pipeline 的 `finally` 捕获清理错误。
- 若主流程成功而清理失败：任务不得报告成功，写当前阶段 `FAILED` 后抛出清理错误。
- 若主流程已失败且清理也失败：保留原始失败为主异常，同时把清理失败作为异常链和状态
  消息中的脱敏补充，避免覆盖根因。

测试通过模拟 `Path.unlink` / `shutil.rmtree` 权限错误验证可观察性，不依赖具体操作系统的
文件占用行为。

## 6. 稳定错误码

实现与原设计逐字对齐，并只追加本轮必需错误：

- `FFMPEG_NOT_FOUND`
- `AUDIO_EXTRACTION_FAILED`
- `AUDIO_EXTRACTION_TIMEOUT`
- `ASR_UNAVAILABLE`
- `ASR_TIMEOUT`
- `INVALID_TIMESTAMP`
- `TRANSCRIPT_SCHEMA_INVALID`
- `UPSTREAM_UNAVAILABLE`
- `CLEANUP_FAILED`
- `JOB_STORE_FAILED`
- `STOPPED`

旧实现中的同义错误码统一迁移，测试不再依赖旧名称。映射到平台 `ErrorCode` 时：
输入/Schema 错误映射为 `VALIDATION_ERROR`，外部服务/续租错误映射为
`UPSTREAM_UNAVAILABLE`，清理与未预期错误映射为 `INTERNAL_ERROR`。

## 7. HttpJobStore 契约测试

使用 `httpx.MockTransport`，不访问真实网络，覆盖：

- claim `204` 返回 `None`。
- claim `200` 按冻结 `InternalTaskClaim` 解析。
- claim、heartbeat、state、transcript 的方法与路径。
- `Authorization: Bearer <token>` 鉴权头。
- heartbeat 请求体和租约参数。
- transcript 使用整批替换请求体，时间戳与 trace 完整。
- HTTP 非 2xx、连接失败和超时统一转为可重试 `JOB_STORE_FAILED`。

## 8. 真实视频证据

`fixture-catalog.md` 必须记录每段视频的：

- 可访问课程页 URL。
- 平台与课程/章节名称。
- 许可条款或本次使用依据。
- 访问日期。
- 本地文件时长、大小或 SHA-256，用于证明测试输入身份，但不泄露内容。
- 脱敏验收摘要：语言、片段数、覆盖时长、首末时间范围、两段输出不同的摘要哈希。

禁止记录完整逐字稿或足以替代课程内容的长文本。若无法从文件或公开页面可靠确认 URL 与
许可，不得猜测；必须请求视频选择者提供原始课程链接后再关闭该阻断项。

## 9. PR 与协作记录

- `docs/ai-collaboration-log.md` 追加本次 AI 协作范围、人工确认和验证结果。
- PR #14 描述写入实现范围、真实验证摘要、隐私说明、测试命令和未实现边界。
- 勾选真实完成的复选框；不能验证的项目保持未勾选并说明原因。
- 推送使用普通 `git push`，不强推。

## 10. 完成标准

- 当前分支包含最新 `main`，GitHub 显示可合并。
- 所有评审列出的 P1 都有对应失败测试和修复。
- 常规 CI 不安装 Worker ASR 可选依赖。
- 本地单元、集成、Lint、`git diff --check` 全部通过。
- PR #14 描述与 AI 协作记录反映真实状态。
- GitHub Actions 全部通过。
