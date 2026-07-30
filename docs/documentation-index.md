# 项目文档索引

`docs/` 是需求、产品、架构、Agent、数据安全和验收结论的统一事实源。文档按“背景与需求 → 产品方案 → 技术实现 → 验证迭代 → 报告交付”维护。

## 建议阅读顺序

1. `current-progress.md`：当前已合并事实、进行中任务、未完成项和 M1 判断。
2. `requirements-baseline.md`：网页要求、核心功能和使用边界。
3. `background-and-needs.md`：任务背景、目标用户、痛点和成功标准。
4. `product-spec.md`：产品定位、核心流程、页面和交互取舍。
5. `ui-baseline-v1.md`：成员 1 已确认的第一版视觉与流程基准，以及成员 2 接入规则。
6. `interface-contracts.md`：前端、后端、Worker 与 Agent 的接口契约。
7. `architecture.md`：系统架构、存储、任务状态和部署关系。
8. `agent-design.md`：Agent 编排、模型、Prompt、Skill、工具和证据门禁。
9. `data-security.md`：隐私、权限、密钥、保留和删除策略。
10. `acceptance-matrix.md`：要求、负责人、实现位置和验收证据映射。
11. `validation-plan.md`：真实输入、失败场景、测试和迭代方法。
12. `scorecard.md`：按官方评分结构进行提交前自检。

## 项目管理与报告

- `project-plan-v5.md`：四天五人执行规划、文件级责任和目标骨架。
- `report-outline.md`：小组报告章节、作者和证据要求。
- `ai-collaboration-log.md`：AI 参与、人工核验和修改原因记录。
- 最终报告正文与个人贡献材料位于 `../reports/`。

## 维护规则

- 第一负责人修改结论时，必须同步更新受影响的接口、验收和报告材料。
- “当前进度”以合并到 `main` 的代码和可核验证据为准；分支或其他对话中的实现
  只能标为“进行中”，合并与复测前不得计入完成范围。
- 同一个事实只设一个权威来源，其他文件使用路径引用，避免复制后产生冲突。
- 模拟、部分实现和未实现内容必须明确标注，不能写成已经完成。
- 本仓库只有根目录使用通用文件名 `README.md`；其他说明文件使用能表达职责的唯一名称。
