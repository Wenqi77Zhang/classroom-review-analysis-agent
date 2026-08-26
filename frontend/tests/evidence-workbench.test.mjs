import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const task = read("src/components/baseline/ReviewTaskBaseline.tsx");
const card = read("src/components/evidence/EvidenceCard.tsx");
const controls = read("src/components/evidence/ReviewControls.tsx");
const timeline = read("src/components/evidence/TranscriptTimeline.tsx");
const player = read("src/components/evidence/VideoPlayer.tsx");
const realWorkbench = read("src/components/evidence/RealEvidenceWorkbench.tsx");

assert.match(
  task,
  /preview === "ready"/,
  "证据工作台只能在待教师复核状态显示",
);
assert.match(
  task,
  /Mock 证据工作台/,
  "演示工作台必须显式标记为 Mock",
);
assert.match(
  task,
  /不代表真实课堂处理已经完成/,
  "演示结论不得冒充真实处理结果",
);
assert.doesNotMatch(
  task,
  /\/assets\/test\.mp4/,
  "不得引用未提交的伪测试视频",
);

assert.match(card, /可核对事实/, "证据卡必须区分事实");
assert.match(card, /分析判断/, "证据卡必须区分判断");
assert.match(card, /改进建议/, "证据卡必须区分建议");
assert.match(card, /不会进入最终报告/, "Mock 结论不得进入最终报告");

assert.match(controls, /type="button"/, "复核按钮必须声明按钮类型");
for (const status of ["accepted", "modified", "rejected"]) {
  assert.ok(controls.includes(`"${status}"`), `缺少复核状态：${status}`);
}
assert.match(
  controls,
  /尚未写入后端/,
  "本地复核状态必须明确说明没有持久化",
);
assert.match(
  controls,
  /onStatusChange/,
  "复核组件必须通过回调向上层传递状态",
);
assert.match(
  controls,
  /onStatusChange\("pending"\)/,
  "重置操作必须通过受控回调同步父页面状态",
);
assert.match(
  controls,
  /onNoteChange\(""\)/,
  "重置操作必须同时清除修改或驳回说明",
);
assert.match(
  task,
  /onSeekEvidence=\{\(\) => \{/,
  "证据卡定位入口必须由页面接通",
);
assert.match(
  task,
  /setSeekToMs\(evidenceStartMs\)/,
  "证据定位必须驱动播放器目标时间",
);

assert.match(timeline, /startMs: number/, "时间轴必须使用毫秒时间契约");
assert.match(timeline, /endMs: number/, "时间轴必须声明片段结束时间");
assert.match(timeline, /onSeek: \(timeMs: number\)/, "时间轴必须提供定位回调");
assert.match(timeline, /aria-pressed/, "当前逐字稿片段必须可被辅助技术识别");

assert.match(player, /preload="metadata"/, "播放器不得自动下载完整课堂视频");
assert.match(player, /playsInline/, "移动端播放器应支持页内播放");
assert.match(player, /暂无真实视频可播放/, "缺少视频地址时必须诚实降级");
assert.match(player, /尚未连接对象存储授权地址/, "不得伪造对象存储接入");
assert.match(realWorkbench, /className="evidence-video-frame"/, "真实视频必须由左栏边界容器约束");

assert.match(task, /realTask\.status === "succeeded"/, "真实证据只能在真实任务成功后显示");
assert.match(task, /router\.replace\(`\/tasks\/\$\{task\.id\}`\)/, "创建任务后 URL 必须切换为可恢复的真实任务 ID");
for (const boundary of [
  "getTaskAssets(task.id)",
  "getTranscript(task.id)",
  "getCoursewarePages(task.id)",
  "getConclusions(task.classroom_id)",
  "getAssetDownloadUrl(video.id)",
  "updateTranscriptSegment",
  "reviewConclusion",
]) {
  assert.ok(realWorkbench.includes(boundary), `真实工作台缺少调用：${boundary}`);
}
assert.match(realWorkbench, /classroomConclusions\.filter/, "课堂结论必须再次按 task_id 隔离");
assert.match(realWorkbench, /action === "reject" && !note\.trim\(\)/, "驳回必须在界面要求原因");
assert.match(realWorkbench, /activeConclusionIndex/, "真实结论应逐条翻页审核而非纵向平铺");
assert.match(realWorkbench, /REVIEW QUEUE · 逐条审核/, "结论审核必须展示清晰的审核队列");
assert.match(realWorkbench, /conclusion-progress-track/, "结论审核必须提供可回看的编号进度轨");
assert.match(realWorkbench, /aria-current=\{token === activeConclusionIndex \? "step"/, "当前结论必须有无障碍步骤标识");
assert.match(realWorkbench, /function buildConclusionTrack/, "大量结论必须使用动态编号窗口");
assert.match(realWorkbench, /ellipsis-start/, "动态编号窗口必须标记被折叠的前段结论");
assert.match(realWorkbench, /ellipsis-end/, "动态编号窗口必须标记被折叠的后段结论");
assert.match(realWorkbench, /下一条待审核/, "审核队列必须提供直接定位遗漏项的入口");
assert.match(realWorkbench, /查看完整清单/, "审核队列必须提供可展开的完整清单");
assert.match(realWorkbench, /按审核状态筛选/, "完整清单必须支持按审核状态筛选");
assert.match(
  realWorkbench,
  /hidden=\{index !== activeConclusionIndex\}/,
  "未显示的结论应保留组件状态，翻页不得丢失教师未提交的修改",
);
assert.match(
  realWorkbench,
  /reviewedConclusionCount === data\?\.conclusions\.length/,
  "所有结论完成审核前不得开放报告下一步",
);
assert.match(realWorkbench, /完成全部结论审核后进入报告/, "报告门禁必须解释尚缺的操作");
assert.match(
  realWorkbench,
  /allConclusionsReviewed && hasReportableConclusion/,
  "全部驳回时不得生成没有正文的报告",
);
assert.match(realWorkbench, /已进入第 \$\{nextPendingIndex \+ 1\} 条/, "保存后应自动进入下一条待审核结论");
assert.doesNotMatch(realWorkbench, /% taskConclusions\.length/, "最后一条审核后不得循环回到第一条");
assert.match(realWorkbench, /全部结论已审核完成，可以进入报告编辑与导出/, "全部审核完成后必须明确提示下一步");
assert.match(realWorkbench, /aria-live="polite"/, "自动切换提示必须能被辅助技术即时感知");
assert.match(realWorkbench, /接受并继续/, "接受按钮必须明确保存后继续审核");
assert.match(realWorkbench, /修改确认并继续/, "修改按钮必须明确保存后继续审核");
assert.match(realWorkbench, /驳回并继续/, "驳回按钮必须明确保存后继续审核");
assert.match(realWorkbench, /className="accept-review"/, "接受操作必须使用明确的按钮视觉层级");
assert.match(realWorkbench, /className="modify-review"/, "修改操作必须使用明确的按钮视觉层级");
assert.match(realWorkbench, /className="reject-review"/, "驳回操作必须使用明确的按钮视觉层级");
assert.match(realWorkbench, /视频地址为限时授权/, "必须向教师说明视频授权的短期边界");
assert.match(realWorkbench, /COURSEWARE EVIDENCE/, "真实工作台必须展示课件页级证据");
assert.match(realWorkbench, /第 \{selectedPage\.page_no\} 页/, "课件证据必须显示真实页码");
assert.match(realWorkbench, /#page=\$\{selectedPage\.page_no\}/, "PDF 原文件入口必须带页码定位");
assert.match(realWorkbench, /reference\.source_type === "courseware"/, "课件证据点击后必须走页级定位而非视频时间定位");
assert.match(realWorkbench, /scrollIntoView/, "课件证据点击后必须把教师带到核对面板");
assert.doesNotMatch(realWorkbench, /localStorage|sessionStorage/, "真实证据和预签名地址不得进入浏览器持久化存储");
assert.match(task, /taskLoadError\.status === 401/, "任务首次读取必须识别会话缺失");
assert.match(task, /await startDemoSession\(\)/, "任务页必须通过服务端会话接口恢复访问");
assert.match(task, /建立演示会话并重试/, "任务页必须提供可操作的会话恢复入口");
assert.match(realWorkbench, /error\?\.status === 401/, "证据工作台必须识别会话过期");
assert.match(realWorkbench, /await startDemoSession\(\)/, "证据工作台必须能够重建安全会话");
assert.match(realWorkbench, /建立演示会话并重试/, "证据工作台必须提供会话恢复按钮");
assert.doesNotMatch(task, /document\.cookie|localStorage/, "任务页不得直接读取或写入访问令牌");
assert.match(task, /正在恢复真实课堂任务/, "任务 URL 首次载入时必须展示状态恢复而不是重复上传");
assert.match(task, /if \(realTask\)/, "已创建任务必须进入独立的真实任务视图");
assert.match(task, /刷新或重新打开此地址都不会要求重复上传/, "真实任务视图必须明确恢复边界");
assert.match(
  task,
  /realTask\?\.status === "failed"[\s\S]*BILINGUAL_EVIDENCE_INCOMPLETE[\s\S]*TRANSLATION_SCHEMA_INVALID/,
  "双语契约提醒只应在确实缺少或无法对齐补充译文时出现",
);
assert.match(task, /\{needsBilingualRecovery && \(/, "正常处理和成功任务不得占用契约提醒空间");

console.log("EVIDENCE_WORKBENCH_CONTRACT_OK");
