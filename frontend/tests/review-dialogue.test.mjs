import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const component = readFileSync(
  resolve(root, "src/components/baseline/ReviewTaskBaseline.tsx"),
  "utf8",
);
const api = readFileSync(resolve(root, "src/lib/api.ts"), "utf8");

assert.match(component, /await clarifyReviewGoal\(/, "教师消息必须真正请求复盘 Agent");
assert.match(component, /response\.assistant_message/, "页面必须展示模型的针对性回复");
assert.match(component, /response\.analysis_contract/, "页面必须使用模型生成的契约草案");
assert.match(component, /契约已形成/, "澄清完成后按钮必须明确提示契约已经形成");
assert.match(component, /教师已确认当前契约/, "教师确认后隐私与来源状态必须同步更新");
assert.match(component, /modelName: response\.model_name/, "页面必须展示模型来源");
assert.match(component, /traceId: response\.trace_id/, "页面必须展示可追踪编号");
assert.match(component, /复盘 Agent 暂时无法连接/, "模型失败必须透明显示");
assert.doesNotMatch(
  component,
  /你希望分析整节课堂还是指定片段？哪些证据必须保留/,
  "不得继续使用与教师输入无关的固定追问",
);
assert.doesNotMatch(
  component,
  /focus_areas: \["内容组织", "讲解清晰度", "提问等待时间"\]/,
  "创建任务不得继续提交固定关注维度",
);
assert.match(api, /teacher_messages: teacherMessages/, "多轮教师输入必须进入后端请求");

console.log("REAL_REVIEW_DIALOGUE_CONTRACT_OK");
