export function ReviewControls() {
  return (
    <div style={{ 
      display: 'flex', 
      gap: '10px', 
      padding: '10px 0', 
      borderBottom: '1px solid #eee', 
      marginBottom: '10px' 
    }}>
      <button style={{ 
        padding: '8px 16px', 
        backgroundColor: '#e6f7e6', 
        color: '#2e7d32', 
        border: 'none', 
        borderRadius: '6px', 
        cursor: 'pointer' 
      }}>
         接受
      </button>
      <button style={{ 
        padding: '8px 16px', 
        backgroundColor: '#fff3e0', 
        color: '#e65100', 
        border: 'none', 
        borderRadius: '6px', 
        cursor: 'pointer' 
      }}>
         修改
      </button>
      <button style={{ 
        padding: '8px 16px', 
        backgroundColor: '#fce4ec', 
        color: '#c62828', 
        border: 'none', 
        borderRadius: '6px', 
        cursor: 'pointer' 
      }}>
         驳回
      </button>
    </div>
  );
}