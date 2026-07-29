// src/components/evidence/TranscriptTimeline.tsx

interface TranscriptItem {
  time: string;
  speaker: string;
  text: string;
}

interface TranscriptTimelineProps {
  items?: TranscriptItem[]; 
  // 👇 我们在这里接收父组件传来的当前视频秒数
  currentTime?: number; 
}

// 辅助函数：把 "00:05" 格式的时间转化为秒数（例如 5）
function parseTimeToSeconds(timeStr: string): number {
  const parts = timeStr.split(':');
  if (parts.length === 2) {
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
  }
  return 0;
}

export function TranscriptTimeline({ items = [], currentTime = 0 }: TranscriptTimelineProps) {
  return (
    <div style={{ marginTop: '15px', padding: '10px', background: '#f9f9f9', borderRadius: '6px' }}>
      <div style={{ fontWeight: 'bold', marginBottom: '10px', fontSize: '15px' }}>📝 课堂实时转录 (字幕)</div>
      
      {items.length === 0 && (
        <div style={{ color: '#999', fontSize: '14px' }}>暂无字幕数据</div>
      )}

      {items.map((item, index) => {
        // 将字幕的时间转化为秒数
        const itemSeconds = parseTimeToSeconds(item.time);
        // 判断当前视频时间是否刚刚经过这条字幕所在的时间
        // 设定一个区间：比如当前在 05~09 秒，就算高亮 00:05
        const isActive = Math.abs(currentTime - itemSeconds) < 5; 

        return (
          <div 
            key={index} 
            style={{ 
              marginBottom: '6px', 
              padding: '6px 8px',
              borderRadius: '4px',
              transition: 'all 0.2s ease',
              // 👇 如果当前时间匹配，背景色变成淡黄色，否则保持透明
              backgroundColor: isActive ? '#fef3c7' : 'transparent', 
              borderBottom: '1px solid #eee',
              fontSize: '14px'
            }}
          >
            <span style={{ color: '#666', marginRight: '15px', fontFamily: 'monospace' }}>
              {item.time}
            </span>
            <span style={{ 
              color: '#2563eb', 
              fontWeight: '500', 
              marginRight: '10px', 
              background: '#eef2ff', 
              padding: '0 6px', 
              borderRadius: '4px' 
            }}>
              {item.speaker}
            </span>
            <span>{item.text}</span>
          </div>
        );
      })}
    </div>
  );
}