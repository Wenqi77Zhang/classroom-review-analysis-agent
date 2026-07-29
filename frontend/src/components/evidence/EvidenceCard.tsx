// frontend/src/components/evidence/EvidenceCard.tsx
import type { ReviewStatus } from "./ReviewControls";

type EvidenceCardProps = {
  fact: string;
  judgment: string;
  suggestion: string;
  sourceLabel: string;
  reviewStatus: ReviewStatus;
  isDemo?: boolean;
  // 👇 新增：接收一个点击跳转的回调函数
  onSeekEvidence?: () => void; 
};

const reviewCopy: Record<ReviewStatus, string> = {
  pending: "待复核",
  accepted: "已接受",
  modified: "已修改",
  rejected: "已驳回",
};

export function EvidenceCard({
  fact,
  judgment,
  suggestion,
  sourceLabel,
  reviewStatus,
  isDemo = false,
  onSeekEvidence, // 👈 接收这个函数
}: EvidenceCardProps) {
  return (
    <article className="evidence-card" aria-labelledby="evidence-card-title">
      <header className="evidence-card-header">
        <div>
          <span className="evidence-kicker">EVIDENCE CHAIN</span>
          <h3 id="evidence-card-title">证据链预览</h3>
        </div>
        <span className={`review-status ${reviewStatus}`}>
          {reviewCopy[reviewStatus]}
        </span>
      </header>

      {isDemo && (
        <p className="demo-disclaimer">
          演示证据 · 不是真实课堂分析，不会进入最终报告
        </p>
      )}

      <dl className="evidence-chain">
        <div>
          <dt>可核对事实</dt>
          <dd>{fact}</dd>
        </div>
        <div>
          <dt>分析判断</dt>
          <dd>{judgment}</dd>
        </div>
        <div>
          <dt>改进建议</dt>
          <dd>{suggestion}</dd>
        </div>
      </dl>

      {/* 👇 在 footer 区域加上了点击触发跳转的联动逻辑 👇 */}
      <footer className="evidence-source">
        <span>证据定位</span>
        {/* 如果是 demo 模式，强调查看；如果有跳转函数，变成可点击的按钮 */}
        {onSeekEvidence ? (
          <button 
            type="button"
            onClick={onSeekEvidence}
            style={{
              background: 'none',
              border: 'none',
              color: '#2563eb',
              textDecoration: 'underline',
              cursor: 'pointer',
              fontSize: 'inherit',
              fontWeight: 'bold',
              padding: 0
            }}
          >
            {sourceLabel} → 定位证据
          </button>
        ) : (
          <strong>{sourceLabel}</strong>
        )}
      </footer>
    </article>
  );
}