// frontend/src/components/evidence/ReviewControls.tsx
import { useState } from "react";

// 定义状态类型
export type ReviewStatus = "pending" | "accepted" | "modified" | "rejected";

export function ReviewControls() {
  // 1. 定义一个状态，记录当前的操作结果，默认是 "pending"（待复核）
  const [status, setStatus] = useState<ReviewStatus>("pending");

  // 2. 定义一个函数，用来重置状态
  const handleReset = () => setStatus("pending");

  // 3. 根据状态，决定按钮显示什么颜色
  const getButtonStyle = (type: "accept" | "modify" | "reject") => {
    // 如果当前状态是点击过的状态，则变灰
    const isActive = 
      (type === "accept" && status === "accepted") ||
      (type === "modify" && status === "modified") ||
      (type === "reject" && status === "rejected");

    return {
      padding: "8px 16px",
      border: "none",
      borderRadius: "6px",
      cursor: "pointer",
      backgroundColor: isActive ? "#e5e7eb" : "#f3f4f6",
      color: isActive ? "#9ca3af" : "#374151",
      transition: "all 0.2s ease",
    };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "12px" }}>
      {/* 按钮组 */}
      <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
        {/* 接受按钮 */}
        <button 
          style={getButtonStyle("accept")} 
          onClick={() => setStatus("accepted")}
        >
          ✅ 接受
        </button>

        {/* 修改按钮 */}
        <button 
          style={getButtonStyle("modify")} 
          onClick={() => setStatus("modified")}
        >
          ✏️ 修改
        </button>

        {/* 驳回按钮 */}
        <button 
          style={getButtonStyle("reject")} 
          onClick={() => setStatus("rejected")}
        >
          ❌ 驳回
        </button>

        {/* 重置按钮 */}
        <button 
          style={{ 
            padding: "8px 12px", 
            background: "#f1f5f9", 
            border: "1px solid #cbd5e1", 
            borderRadius: "6px", 
            fontSize: "12px", 
            color: "#475569",
            cursor: "pointer" 
          }}
          onClick={handleReset}
        >
          ↻ 重置状态
        </button>
      </div>

      {/* 状态提示文本 */}
      <div style={{ fontSize: '13px', color: '#64748b', paddingLeft: '4px' }}>
        当前操作状态：<span style={{ fontWeight: 'bold', color: status === 'pending' ? '#64748b' : '#0f172a' }}>
          {status === 'pending' && '等待复核...'}
          {status === 'accepted' && '已接受 ✅'}
          {status === 'modified' && '已修改 ✏️'}
          {status === 'rejected' && '已驳回 ❌'}
        </span>
      </div>
    </div>
  );
}