# 报告组合规则

版本：`report-v1`

报告组合是确定性步骤，不交由模型决定：

- 只接收 `accepted` 或 `modified` 结论；
- `modified` 必须使用教师的 `reviewed_content`，不能退回模型原文；
- `pending`、`rejected` 和无有效证据的内容必须过滤；
- 每条内容保留证据定位、复核状态、内容版本与 Trace ID；
- 所有结论完成复核前不得生成最终报告。
