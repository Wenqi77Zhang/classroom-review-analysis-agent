# 报告组合规则

版本：`report-v1`

报告组合是确定性步骤，不交由模型决定：只接收 `accepted` 或 `modified` 结论；`modified` 必须使用教师的 `reviewed_content`；`pending` 和 `rejected` 必须过滤；每条内容保留证据定位与 Trace ID。
