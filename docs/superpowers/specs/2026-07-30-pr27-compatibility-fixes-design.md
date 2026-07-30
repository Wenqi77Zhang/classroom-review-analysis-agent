# PR #27 兼容优先最小修复设计

日期：2026-07-30  
状态：已获成员 4 确认，待实施  
范围：PR #27 的远程 Worker 兼容性、租约恢复、双语门禁和状态机组合测试

## 1. 目标

在不下载真实翻译模型、不新增后端接口、不接管成员 5 通用 Agent 编排的前提下，恢复
现有 `视频 → 转写 → Worker/Agent 交接` 远程主链，并保留已经测试通过的翻译、课件解析
和证据索引内部能力。

本轮完成后：

- 未配置 `TranslationAdapter` 的远程 Worker 只执行到 `transcribe`，保存原文逐字稿后
  立即使用现有 `handoff-agent` 交给 Agent；
- 配置测试或未来真实 Adapter 时，`run_pipeline` 仍可执行 `translate` 内部阶段；
- `transcribe` 阶段租约过期后重新领取不会回写更早的 `extract_audio` 阶段；
- 双语门禁只要求逐字稿证据具备逐句译文，不因课件、视频或画面证据没有
  `translation` 字段而拒绝；
- PostgreSQL 支撑的 FastAPI 组合测试覆盖租约过期重领、同阶段恢复、逐字稿写入和
  Agent 交接。

## 2. 不在本轮范围

- 不实现或下载真实翻译模型；
- 不把翻译、课件解析或独立证据索引接入远程领取链；
- 不新增证据表、数据库迁移、证据写入 API、`lease_id` 或证据版本接口；
- 不注册成员 4 的专业 Skill 到成员 5 的通用 Agent 运行入口；
- 不声称多 Worker 并发安全、完整生产部署或真实双语验收通过；
- 不改变教师失败重试的阶段回退契约。租约过期恢复不是教师重试。

## 3. 远程主链兼容策略

`run_pipeline` 以 `translation_adapter is not None` 作为进入翻译内部阶段的唯一条件。

未配置 Adapter：

```text
extract_audio → transcribe → 保存原文逐字稿
             → transcribe / running / 1.0
             → handoff-agent
```

配置 Adapter：

```text
extract_audio → transcribe → 保存原文逐字稿
             → translate → 保存逐句译文
```

远程 `worker.runner` 当前不构造真实 Adapter，因此使用第一条兼容路径。它不会调用
`translate_transcript(..., None)`，也不会产生 `TRANSLATION_UNAVAILABLE`。翻译函数本身
继续 fail-closed：调用者显式要求翻译却没有 Adapter 时仍返回稳定失败码。

## 4. 租约过期后的同阶段恢复

远程领取响应中的 `claim.stage` 是后端当前已记录阶段。Worker 重新下载视频并准备临时
音频是恢复处理所需的本地动作，不等于数据库阶段回退。

`run_pipeline` 接收当前领取阶段：

- `uploaded` 或 `extract_audio`：正常回写 `extract_audio` 进度，再进入 `transcribe`；
- `transcribe`：仍在本地重新准备音频，但不回写 `extract_audio`；失败和后续进度均记在
  `transcribe`；
- 其他阶段不由当前远程 Worker 领取，本轮不扩展。

这样既不会触发后端“阶段不能倒退”，也不会把租约恢复伪装成教师重试。后段失败是否回退
到更早阶段仍等待成员 3 冻结契约。

## 5. 双语门禁

`translation` 是逐字稿句子的派生字段。课件页、视频和画面证据没有逐句译文字段，不能
因为 `bilingual_required=true` 被统一拒绝。

本轮统一以下规则：

- 只有 `source_type=transcript` 的证据参与“译文是否完整”检查；
- 逐字稿证据缺译文时继续 fail-closed；
- `courseware`、`video`、`frame` 证据只接受其各自已有的页码、时间或画面定位校验；
- 通用 Agent 门禁与成员 4 专业门禁使用相同范围，避免一层通过、另一层拒绝。

本轮不增加课件语言识别或课件翻译字段。英文课件翻译属于后续契约设计，不在最小修复内。

## 6. 测试设计

### 6.1 Worker 单元测试

- 无 Adapter 的英文逐字稿不会进入 `translate`，最终状态保持
  `transcribe / running / 1.0`；
- 有 Adapter 时仍保存原文和逐句译文；
- `claim.stage=transcribe` 时不会向后端发送 `extract_audio` 状态；
- 无 Adapter 的远程处理完成后调用现有 `handoff-agent`。

### 6.2 Agent 门禁单元测试

- 双语分析中的中文课件证据没有译文也可通过双语完整性检查；
- 双语分析中的逐字稿证据缺译文仍在模型调用前被拒绝；
- 专业 evidence gate 与通用门禁遵循同一规则。

### 6.3 FastAPI + PostgreSQL 组合测试

在现有 `TEST_DATABASE_URL` 集成测试体系中新增真实 ASGI 请求序列：

1. 创建并领取视频任务；
2. 将任务推进到 `transcribe / running`；
3. 直接把数据库租约调整为已过期，模拟 Worker 进程中断；
4. 用新的 Worker 在 `transcribe` 阶段重新领取；
5. 确认向更早阶段回写仍被 API 拒绝；
6. 确认同一 `transcribe` 阶段可继续写入状态和逐字稿；
7. 使用新 Worker 身份完成 `handoff-agent`；
8. 确认任务进入 `analyze / queued` 且 Worker 租约释放。

该测试使用真实 FastAPI 路由、依赖、SQLAlchemy 仓储和 PostgreSQL 状态，不以 Mock
替代状态机。没有 `TEST_DATABASE_URL` 的普通本地环境继续按现有约定跳过，CI 的
PostgreSQL job 必须执行。

## 7. 文档与验收口径

更新 Worker 和 Agent 指南：

- 常驻轮询只代表单 Worker 兼容运行，不代表多 Worker 生产并发；
- 远程纵向链路目前只接通原文转写和基础 Agent 交接；
- 翻译、课件解析、独立证据索引为经过自动测试的内部能力；
- 真实翻译 Adapter、课件/独立证据后端持久化和第二段完整远程复验仍未完成；
- 不把 fake Adapter、单元测试或本地解析冒充真实双语/证据纵向验收。

## 8. 完成条件

- 新增测试先失败、实现后通过；
- Python 全仓、Ruff、前端回归、生产构建、敏感检查和 `git diff --check` 通过；
- PR #27 CI 全部通过；
- PR 描述或评论准确记录本轮修复及未完成边界；
- 不提交 `.agents/`、`skills-lock.json`、视频、完整逐字稿、模型或密钥；
- 使用普通提交和普通推送，不改写或强制覆盖现有历史。
