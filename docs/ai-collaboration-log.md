# AI 协作记录

| 日期 | 成员 | 任务 | 关键提示词 | AI 输出摘要 | 人工核验 | 修改原因 | 最终处理 | 证据链接 |
|---|---|---|---|---|---|---|---|---|
| 2026-07-26 | 成员 3 | 通读仓库、确定成员 3 责任范围与四天节奏 | "我现在作为成员三参与到这个多 Agent 项目中，请你完整地阅读这个初步的 GitHub 仓库，告诉我我具体的任务内容以及要用到哪些东西" | 责任边界、主责文件清单、技术选型与依据、四天逐日计划 | 结论逐条对回 `project-plan-v5.md` §4「成员 3」、§6、§8、§9 与 Issue #3 原文 | 无 | 采纳 | Issue #3、`docs/project-plan-v5.md` |
| 2026-07-26 | 成员 3 | 冻结跨模块 Schema 契约 v1 | 承接上一条已确认的计划，要求"契约优先，先写 schemas 再写路由" | 4 个 Schema 文件、枚举表、错误码表、任务状态机、端点契约、内部接口族 | 自动化：52 项测试全过；契约条款逐条对回 `interface-contracts.md` 原有强制字段 | 4 项偏离阶段 0 草案之处未擅自定稿 | 采纳，并在 `interface-contracts.md` 变更节列出待成员 1/2/4/5 确认 | `backend/app/schemas/`、`docs/interface-contracts.md` |
| 2026-07-26 | 成员 3 | 配置校验、异步数据库、领域异常、FastAPI 应用 | 同上计划的 Day 1「基础设施」与「认证权限骨架」时间块 | `config.py`、`database.py`、`errors.py`、`main.py` | 自动化：`/health` 与 `/health/ready` 实连 PostgreSQL 17.10 通过；CORS 允许/拒绝、错误外层、trace_id 透传均有测试 | 见下方「被修改或推翻的 AI 输出」第 3、4 条 | 修改后采纳 | `backend/app/`、`tests/unit/test_backend.py` |
| 2026-07-26 | 成员 3 | 后端测试 | 要求把临时验证脚本转成仓库内可复现测试 | `tests/unit/test_backend.py`，初版 52 项 | 自动化：`pytest -q` → 52 passed | 无 | 采纳 | `tests/unit/test_backend.py` |
| 2026-07-26 | 成员 3 | 按 PR #6 审查意见修正 | "这次 PR 被审查之后没有被合并，其中给出了一些审查意见，请你看一下，然后给出解决方案" | 逐条修正状态集合语义、内部逐字稿校验、`modified` 状态闭合、服务令牌拆分、上传核对契约、trace_id 约束、文档数字同步 | 自动化：`pytest -q` → 85 passed；`ruff` 通过 | 均为 AI 先前实现中的真实缺陷，由成员 1 独立审查发现 | 8 项全部采纳并补回归测试。第 6 项一度因 Docker 引擎崩溃而阻塞，未按猜测填写版本号；排查出僵尸 socket 后读到真实版本才固定 | `reports/contributions/member-3.md` 第四节 |
| 2026-07-26 | 成员 3 | 本地环境与基础设施 | "帮我装"、"我的储存空间已经严重不足了，你能不能把 Docker 安装在 D 盘上？"、"已重启" | Python 3.13 安装、C 盘清理、Docker Desktop 装到 D 盘、WSL2 修复、compose 加入 MinIO | 自动化：`wsl --status` 退出码 0、`docker info` 可用、两容器 healthy、桶已建、`D:\Docker\wsl` 已生成 | 见下方第 5 条：AI 原先归因 UAC 未批准，实测证伪 | 修改后采纳 | `docker-compose.yml`、`backend/backend-module-guide.md` |
| 2026-07-26 | 成员 3 | 合并 `main` 并对齐 B2 对象存储方案 | "推送"、"合并对齐 + 按 B2 调整" | 识别出远端 main 已定 B2 方案且与本分支 5 个文件重叠；统一变量名、修正 path-style 默认值、MinIO 降级为离线替代品 | 自动化：56 项测试全过、`setup.ps1` 端到端退出 0、无残留冲突标记 | AI 原方案基于本地 MinIO，与团队已定的 B2 方案冲突，以 `main` 为准 | 修改后采纳；Provider 抽象层与 B2 凭据列入已知限制 | `backend/app/config.py`、`docs/interface-contracts.md` |
| 2026-07-26 | 成员 3 | 缺陷修复（4 个） | 无专门提示词；均在执行上述计划过程中由实际运行或自建测试暴露 | `.ps1` 编码修复、`verify` README 检查改用 `git ls-files`、日志脱敏两处修正 | 自动化：`setup.ps1` 跑通、`verify.ps1`/`verify.sh` 在 `.pytest_cache/README.md` 存在时退出 0、脱敏回归用例通过 | 见下方第 1、2 条 | 修改后采纳；涉及成员 5 主责文件的部分标注待确认 | `reports/contributions/member-3.md` 第 5 项 |

禁止把未经人工核验的 AI 内容直接写成事实、引用、测试结果或个人独立成果。

---

## 2026-07-26 成员 3 补充说明

### 使用的 AI 工具

Claude Code（Anthropic，模型 Opus 5），在本机以命令行 Agent 方式运行，可读写仓库文件、
执行 PowerShell/Bash 命令与容器命令。

### 核验方式与当前核验状态

**必须如实区分两件事：**

- **已完成的自动化核验**：85 项 pytest 断言、`ruff check`、`verify.ps1` / `verify.sh` /
  `check-secrets` 退出码、`docker compose ps` 健康状态、`psql` 版本输出、
  `/health/ready` 实连数据库。这些是可复现的机器验证，命令与输出记录在
  `reports/contributions/member-3.md` 第 4 项。
- **尚未完成的人工核验**：成员 3 本人对代码与文档的逐行阅读复核**尚未进行**。
  契约 v1 中 4 项偏离阶段 0 草案之处也**尚未取得**成员 1、2、4、5 确认。

因此本轮成果目前只能声明为"自动化验证通过、待人工复核"，不得写成"已由人工核验"。

TODO(成员 3)：完成逐行阅读复核后更新本节，并在小组报告中如实描述该核验过程。

### 被修改或推翻的 AI 输出

1. **日志脱敏破坏了数值格式串**（AI 引入的缺陷）。首版 `RedactingFilter` 把
   `record.args` 全部 `str()` 化，第三方库的 `%d` 收到字符串后抛 `TypeError`，
   httpx 的 `'HTTP Request: %s %s "%s %d %s"'` 每条都会报错。**改为**只脱敏字符串类型参数、
   保留其余类型，并补回归用例覆盖 `%d`、`%.2f` 与多参数。

2. **日志脱敏漏遮登录令牌**（AI 引入的缺陷，且命中发布门禁阻断项）。首版
   `Authorization` 正则 `(\S+)` 只匹配到 `Bearer` 一词，真正的令牌原样留在日志里。
   **改为**显式吃掉 `Bearer`/`Basic`/`Token` 前缀，并覆盖三种 `Authorization` 形态。

3. **泛型写法过时**。AI 首版 `class Page(OrmModel, Generic[T])` 被 `ruff` 判为
   应改用类型参数语法。**改为** PEP 695 的 `class Page[T](OrmModel)`，与项目
   Python 3.13 基线一致。

4. **`main.py` 结尾出现绕弯写法**。AI 首版写了
   `app = create_app() if False else None` 来"占位"模块级 `app`，语义混乱。
   **改为**完全不提供模块级实例，并用注释说明启动方式为 `uvicorn --factory`。

5. **AI 的一项技术判断被实测证伪**。AI 在计划中断言：因 `backend/` 缺少
   `__init__.py`，`pip install -e` 可能失败，需补该文件。实测 `pip install -e ".[dev]"`
   正常，`backend` 以 namespace package 形式可导入，**该假设不成立，未添加该文件**。
   同类情况：AI 最初把 Docker Desktop 安装失败归因于"UAC 未批准"，实测发现
   `ConsentPromptBehaviorAdmin=0`（管理员静默提权），真实原因是 C 盘仅剩 0.3 GB。

6. **依赖版本不凭推测书写**。AI 计划中建议直接给依赖写上下界。改为先不带版本安装、
   由 `pip freeze` 读出真实解析结果，再回填下界与主版本上界，并把已验证版本记录在
   `backend/backend-module-guide.md`，避免凭猜测写出不存在或过紧的版本约束。

### 由人工审查发现的 AI 缺陷（PR #6，成员 1 提出）

以下 5 项都是 AI 已写完、自测通过、且自己没有发现的真实缺陷，由成员 1 的独立审查揪出。
它们说明自动化测试通过**不等于**设计正确——测试只能验证"我想到的情况"。

7. **状态集合自相矛盾**：`FAILED` 同时被列为可重试和终态。AI 写了两处定义却没做交叉检查。
   修正后增加**不变量测试**（终态集合中每个状态的迁移集合必须为空），把"交叉检查"这件事
   交给测试而不是记性。
8. **内部接口绕过校验**：AI 只在对外 Schema 上加了时间区间校验，忘了同一约束在内部写入
   接口同样必要，等于给 Worker 留了写入坏数据的口子。
9. **状态与内容不闭合**：`modified` 允许缺教师改写内容，且 `reportable_content()` 静默回退
   模型原文——AI 当初把"回退"当成健壮性，实际是把"教师已确认"变成了假象。
10. **权限拆分不到位**：AI 设计了单一 `WORKER_SERVICE_TOKEN` 给 Worker 和 Agent 共用，
    违反最小权限。修正为双令牌 + 端点权限表 + 阶段范围。
11. **信任了客户端自报**：AI 设计的 `/assets/{id}/complete` 直接依据浏览器回调标记上传完成，
    未要求后端独立核对对象。修正为必须 HEAD 核对后以服务端结果为准。
