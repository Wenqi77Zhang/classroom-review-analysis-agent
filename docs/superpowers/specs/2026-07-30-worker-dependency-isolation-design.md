# Worker ASR 依赖隔离修复设计

## 问题

PR #14 的 GitHub Actions 在 `backend-check` 的依赖安装阶段失败。该 PR 把
`openai-whisper` 加入项目通用依赖，导致只需运行后端测试的 CI 也必须解析并安装
Whisper、PyTorch 及相关平台包。媒体运行时依赖与后端基础依赖因此发生了不必要的耦合。

## 目标

- 后端 CI 执行 `pip install -e ".[dev]"` 时不安装 Whisper 或模型运行时。
- 成员 4 本地开发可通过一个明确的额外依赖组安装 Whisper。
- 不修改 Worker API、Schema、流水线逻辑或识别结果。
- 现有无真实视频的单元测试仍可在未安装 Whisper 时运行。

## 方案

将 `openai-whisper` 从 `[project].dependencies` 移入
`[project.optional-dependencies].worker`：

```toml
worker = [
  "openai-whisper>=20250625,<2027",
]
```

后端与通用开发环境继续安装 `.[dev]`。需要运行真实 ASR 的成员安装
`.[dev,worker]`。`LocalWhisperAdapter` 已使用延迟导入，因此未安装可选依赖不会影响
模块导入和假 ASR 单元测试；真正调用本地 Whisper 时仍返回现有的
`ASR_UNAVAILABLE` 可操作错误。

## 备选方案

1. 在 CI 中继续安装 Whisper：改动少，但后端检查仍慢且受 PyTorch 平台包影响，不采用。
2. 完全移除依赖声明，只在文档中手工安装：CI 可恢复，但环境不可复现，不采用。
3. 拆成独立 Worker 包：长期边界更清楚，但超出本次 CI 修复范围，不采用。

## 验证

- 创建不含 Worker 额外依赖的新 Python 3.13 环境，安装 `.[dev]`。
- 运行全部常规测试与 Ruff。
- 在现有包含 Whisper 的环境中运行 Worker 单元测试，确保媒体功能不回退。
- 推送修复提交并确认 PR #14 的 `backend-check` 重新运行。

## 非目标

- 不在 GitHub Actions 下载 Whisper 模型或运行两段课程视频。
- 不更改 ASR 模型选择、时间戳格式或 JobStore 契约。
- 不处理与本次失败无关的 Node.js Actions 弃用警告。
