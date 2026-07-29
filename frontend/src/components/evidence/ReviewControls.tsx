export type ReviewStatus =
  | "pending"
  | "accepted"
  | "modified"
  | "rejected";

type ReviewControlsProps = {
  status: ReviewStatus;
  note: string;
  onStatusChange: (status: ReviewStatus) => void;
  onNoteChange: (note: string) => void;
};

const actions: Array<{
  status: Exclude<ReviewStatus, "pending">;
  label: string;
}> = [
  { status: "accepted", label: "接受" },
  { status: "modified", label: "修改" },
  { status: "rejected", label: "驳回" },
];

export function ReviewControls({
  status,
  note,
  onStatusChange,
  onNoteChange,
}: ReviewControlsProps) {
  return (
    <section className="review-controls" aria-labelledby="review-controls-title">
      <div>
        <span className="evidence-kicker">TEACHER GATE</span>
        <h3 id="review-controls-title">教师人工复核</h3>
        <p>Mock 复核 · 仅保存在当前页面，尚未写入后端。</p>
      </div>

      <div className="review-actions" role="group" aria-label="复核结论">
        {actions.map((action) => (
          <button
            type="button"
            key={action.status}
            className={status === action.status ? "active" : ""}
            aria-pressed={status === action.status}
            onClick={() => onStatusChange(action.status)}
          >
            {action.label}
          </button>
        ))}
      </div>

      {(status === "modified" || status === "rejected") && (
        <label className="review-note">
          {status === "modified" ? "教师修改说明" : "驳回原因"}
          <textarea
            rows={3}
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="请记录修改内容或驳回原因；真实版本提交前必须填写。"
          />
        </label>
      )}
    </section>
  );
}
