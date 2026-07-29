export type TranscriptItem = {
  id: string;
  startMs: number;
  endMs: number;
  speaker: string;
  originalText: string;
  translatedText: string;
};

type TranscriptTimelineProps = {
  items: TranscriptItem[];
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
};

function formatTimestamp(timeMs: number) {
  const totalSeconds = Math.max(0, Math.floor(timeMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function TranscriptTimeline({
  items,
  currentTimeMs,
  onSeek,
}: TranscriptTimelineProps) {
  return (
    <section
      className="transcript-timeline"
      aria-labelledby="transcript-timeline-title"
    >
      <header>
        <div>
          <span className="evidence-kicker">TIMESTAMPED TRANSCRIPT</span>
          <h3 id="transcript-timeline-title">双语逐字稿</h3>
        </div>
        <small>点击片段可请求播放器定位</small>
      </header>

      <div className="transcript-items">
        {items.map((item) => {
          const isActive =
            currentTimeMs >= item.startMs && currentTimeMs < item.endMs;
          return (
            <button
              type="button"
              key={item.id}
              className={`transcript-item ${isActive ? "active" : ""}`}
              aria-pressed={isActive}
              onClick={() => onSeek(item.startMs)}
            >
              <span className="transcript-meta">
                <time>{formatTimestamp(item.startMs)}</time>
                <strong>{item.speaker}</strong>
              </span>
              <span className="transcript-copy">
                <span lang="en">{item.originalText}</span>
                <span>{item.translatedText}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
