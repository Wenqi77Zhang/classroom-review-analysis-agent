// src/components/evidence/EvidenceCard.tsx

interface EvidenceCardProps {
  fact?: string;
  judgment?: string;
  suggestion?: string;
}

export function EvidenceCard({ fact, judgment, suggestion }: EvidenceCardProps) {
  return (
    <div style={{ marginTop: '15px', padding: '15px', border: '1px solid #e5e7eb', borderRadius: '6px', background: '#f9fafb' }}>
      <h4 style={{ margin: '0 0 10px 0', fontSize: '15px', fontWeight: 'bold' }}>📋 课堂观察证据</h4>
      
      <div style={{ marginBottom: '8px' }}>
        <strong style={{ color: '#2563eb' }}>事实：</strong> 
        {fact || "暂无事实描述"}
      </div>
      
      <div style={{ marginBottom: '8px' }}>
        <strong style={{ color: '#ca8a04' }}>判断：</strong> 
        {judgment || "暂无判断分析"}
      </div>
      
      <div>
        <strong style={{ color: '#16a34a' }}>建议：</strong> 
        {suggestion || "暂无改进建议"}
      </div>
    </div>
  );
}