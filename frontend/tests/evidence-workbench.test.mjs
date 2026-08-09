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

assert.match(task, /realTask\?\.status === "succeeded"/, "真实证据只能在真实任务成功后显示");
assert.match(task, /router\.replace\(`\/tasks\/\$\{task\.id\}`\)/, "创建任务后 URL 必须切换为可恢复的真实任务 ID");
for (const boundary of [
  "getTaskAssets(task.id)",
  "getTranscript(task.id)",
  "getConclusions(task.classroom_id)",
  "getAssetDownloadUrl(video.id)",
  "updateTranscriptSegment",
  "reviewConclusion",
]) {
  assert.ok(realWorkbench.includes(boundary), `真实工作台缺少调用：${boundary}`);
}
assert.match(realWorkbench, /classroomConclusions\.filter/, "课堂结论必须再次按 task_id 隔离");
assert.match(realWorkbench, /action === "reject" && !note\.trim\(\)/, "驳回必须在界面要求原因");
assert.match(realWorkbench, /视频地址为限时授权/, "必须向教师说明视频授权的短期边界");
assert.doesNotMatch(realWorkbench, /localStorage|sessionStorage/, "真实证据和预签名地址不得进入浏览器持久化存储");

console.log("EVIDENCE_WORKBENCH_CONTRACT_OK");
