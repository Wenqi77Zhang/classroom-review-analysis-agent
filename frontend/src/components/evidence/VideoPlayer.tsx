"use client";

import { useEffect, useRef, useState } from "react";

type VideoPlayerProps = {
  videoUrl?: string;
  seekToMs: number;
  onTimeUpdate: (timeMs: number) => void;
};

export function VideoPlayer({
  videoUrl,
  seekToMs,
  onTimeUpdate,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    setLoadFailed(false);
  }, [videoUrl]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(seekToMs)) {
      return;
    }
    video.currentTime = Math.max(0, seekToMs / 1000);
  }, [seekToMs, videoUrl]);

  if (!videoUrl || loadFailed) {
    return (
      <section className="video-placeholder" aria-label="视频播放器未连接">
        <span aria-hidden>▶</span>
        <strong>{loadFailed ? "视频载入失败" : "暂无真实视频可播放"}</strong>
        <p>
          {loadFailed
            ? "请检查授权地址是否有效后重试。"
            : "演示数据 · 尚未连接对象存储授权地址。"}
        </p>
      </section>
    );
  }

  return (
    <video
      ref={videoRef}
      className="evidence-video"
      controls
      playsInline
      preload="metadata"
      src={videoUrl}
      aria-label="课堂证据视频"
      onError={() => setLoadFailed(true)}
      onTimeUpdate={(event) =>
        onTimeUpdate(Math.round(event.currentTarget.currentTime * 1000))
      }
    >
      当前浏览器不支持 HTML5 视频播放。
    </video>
  );
}
