# 成员 1（组长）贡献

## 当前已完成

- 主持需求、范围、产品边界和四天五人分工确认，维护 v5 方案、验收矩阵与责任边界。
- 多轮人工评审并确认 UI Baseline v1；AI 参与原型、素材和代码生成，成员 1 负责审美判断、交互取舍、文案与最终采用决定。
- 完成课堂资料入口的产品规则与流程前端：本地文件分类、格式/大小校验、视频证据门禁和真实服务未接通提示；未把 Mock 上传写成真实能力。
- 在成员 3 的后端基础契约合并后，复核并修正前端资料类型与容量限制漂移；接入只读 `/health` 同源代理，让页面能区分“后端不可达”和“基础服务可达但上传接口未实现”，不越权实现成员 3 的业务路由。
- 主持第一次跨模块集成验收，如实记录后端、Worker、Agent 与证据工作台尚未接通的阻塞项。
- 复核 PR #6 的后端契约和安全边界，发现异常 traceback 绕过日志脱敏；协作补充最终文本脱敏、回归测试和后端 CI，并保留成员 3 的原始实现归属。
- 完成 Day 2 流程前端审查：补充 Agent 必要追问、真实视频前置门禁、五阶段任务状态与失败重试预览、复核结果的会话级报告交接，以及报告编辑、预览、复核过滤和浏览器 PDF 导出；所有本地演示、未持久化和待后端能力均醒目标注。
- 在成员 3 已完成的 Schema、ORM、迁移、认证与课堂 API 基础上，协作补齐对象存储上传核验、任务创建/查询/事件/重试、Worker/Agent 最小权限写入，以及课堂—上传—任务—逐字稿—证据化结论的最短后端链路；原平台后端责任归属仍为成员 3。
- 从成员 2 的 `aba-evidence-v2` 派生独立修复分支，保留证据定位和状态重置功能，同时修复受控状态接口、修改/驳回说明及报告门禁回归；新增同源 BFF 与 HttpOnly 演示会话，接通真实课程/课堂、预签名 B2 上传、后端 HEAD 核验、失败对象清理、任务创建和状态轮询。成员 2 原提交与成员 1 后续修复分别保留。
- 在成员 4 已完成的本地媒体流水线基础上，协作补齐新任务的 `uploaded` 阶段领取、后端限时只读地址签发、B2 流式下载、服务令牌隔离、下载大小与已验证 ETag 核对及临时文件清理；同时修正 Whisper 日期版本上界。媒体流水线主责仍归成员 4，本项仅记录成员 1 的跨模块集成贡献。
- 暂代成员 5 完成 Agent 运行时的跨模块集成：在独立分支实现 Worker→Agent 原子交接、Agent 最小权限领取与续租、结构化结论写回、任务完成和安全失败处理，并让分析契约从前端任务创建贯通到 Agent。Agent 编排原始实现与长期主责仍归成员 5，本项只记录成员 1 的补位集成和人工决策。
- 复验成员 3 的 PR #24 修复：使用隔离 PostgreSQL 17 实例确认旧契约毒任务隔离和跨任务 `event_id` 并发冲突；PR #27 合入 `main` 后，在独立 worktree 组合保留应用重建租约恢复与 transcribe 阶段不倒退测试，完成冲突整合并通过全仓 Ruff、`265 passed, 1 skipped`。Trace 与审计功能实现仍归成员 3。
- Day 3 真实试用暂时延期；先完成静态流程审查，将核心内容改为默认可见、显现动画改为可选增强，并验证关闭 JavaScript 后任务页仍可阅读。此项不冒充真实用户试用或同任务复测。
- 在 PR #34 的真实证据工作台基础上完成报告前端集成：坚持正文只能由后端按教师复核状态生成，前端仅修改标题；补充真实报告读取/首次创建/预览、Markdown/HTML/PDF 导出及短时下载链接，并保留 `/reports/demo` 的独立 Mock 边界。
- 主持单输入真实数据技术 E2E：识别并保留旧契约隔离与旧 B2 对象 404 两类失败证据，
  重新走预签名上传与 HEAD 核验，启动 Worker/Agent，让真实时间戳逐字稿驱动本地
  `qwen3.5:4b` 生成三类证据结论；随后验证接受、修改、驳回、复核历史、报告过滤及
  Markdown/HTML/PDF 真实下载。该项属于跨模块集成与验收，不改变成员 4/5 的原始主责。
- 发现旧 Worker 进程抢占新任务后未执行新增译文导入逻辑；在不记录字幕正文、签名地址或
  密钥的前提下，核对进程启动时间与对象大小/ETag，清理经确认的旧进程并重试。随后通过
  浏览器同时上传视频与教师 UTF-8 VTT，验证 B2、ASR、4/4 片段译文对齐及 Agent 成功；
  同时为 `start.ps1` 增加命名互斥锁和 PID/启动时间双校验清理，降低重复服务抢占风险。
- 在成员 2 证据工作台基础上迭代逐条复核：实现待审队列、保存后自动进入下一条、全部审核
  完成提示，以及未完成前禁用报告入口；该协作不改变证据工作台的成员 2 主责。

## 可核验证据

- `docs/ui-baseline-v1.md`
- `frontend/src/components/baseline/`
- `frontend/src/components/upload/UploadPanel.tsx`
- `frontend/src/app/api/backend-health/route.ts`
- `frontend/tests/backend-health.test.mjs`
- `tests/manual/day1-integration-acceptance.md`
- `tests/manual/day2-member1-flow-audit.md`
- `tests/manual/day3-member1-static-audit.md`
- `tests/manual/failure-and-retry-record.md`
- `frontend/tests/task-status-panel.test.mjs`
- `frontend/tests/report-flow.test.mjs`
- `frontend/src/components/reports/RealReportEditor.tsx`
- `frontend/src/app/api/reports/`
- `frontend/tests/complete-flow.test.mjs`
- `backend/app/api/uploads.py`
- `backend/app/api/tasks.py`
- `backend/app/api/transcripts.py`
- `backend/app/api/analyses.py`
- `tests/integration/test_processing_api.py`
- `worker/job_store.py`
- `worker/runner.py`
- `tests/unit/test_worker.py`
- `agent/job_store.py`
- `agent/runner.py`
- `tests/unit/test_agent.py`
- PR #6、#7、#8、#9、#15、#17、#18、#19、#20 及 `docs/ai-collaboration-log.md`

## 当前限制

- 成员 1 未独立完成平台后端、Worker、Agent 编排原始实现或证据工作台；跨模块修复与暂代集成均按协作贡献记录。
- 前端已接入课程、课堂、上传、任务、真实证据复核与服务端报告；单输入真实数据技术 E2E
  已通过；视频与教师定时译文同时上传也已真实复验，但浏览器全程点击、非开发教师试用、
  第二段不同视频、自动翻译 Provider 和课件证据仍未验收。
- PostgreSQL 17.10、Alembic head、后端认证/课堂以及真实 B2
  `presign → PUT → HEAD complete → task → download → FFmpeg → Whisper → transcript`
  已在协作验收中通过；后续新任务已完成 `succeeded / analyze / 1.0` 并形成三条证据结论。
  该单输入结果不得扩大表述为第二输入、翻译、课件或完整 M1 已完成。
- `/reports/demo` 仍是明确标注的本地演示；真实课堂报告已改走服务端持久化和 Markdown/HTML/PDF 导出，但本分支合并后的人工下载与跨设备恢复尚未验收。
- Day 3 尚未执行非开发同学独立试用、反馈驱动修改和同任务复测，因此退出条件尚未通过。
