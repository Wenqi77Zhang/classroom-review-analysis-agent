// VideoPlayer.tsx
import React, { useRef, useEffect } from "react";

interface VideoPlayerProps {
  videoUrl?: string;
  onTimeUpdate?: (currentTime: number) => void;
  seekTo?: number | null; 
}

export function VideoPlayer({ videoUrl, onTimeUpdate, seekTo }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      if (onTimeUpdate) {
        onTimeUpdate(Math.floor(video.currentTime));
      }
    };

    video.addEventListener("timeupdate", handleTimeUpdate);
    return () => {
      video.removeEventListener("timeupdate", handleTimeUpdate);
    };
  }, [onTimeUpdate]);

  // === 终极跳转逻辑 ===
  useEffect(() => {
    const video = videoRef.current;
    if (video && typeof seekTo === 'number') {
      // 终极防火墙：
      // 如果视频“当前所在的秒数”和“要跳过去的秒数”完全一样，
      // 就绝对不要再进行任何操作，防止死循环！
      if (Math.floor(video.currentTime) === seekTo) {
        return; 
      }

      // 如果不一样，说明是真正的点击，执行跳转并暂停！
      video.currentTime = seekTo;
      video.pause();
    }
  }, [seekTo]);

  if (!videoUrl) {
    return <div style={{ padding: 20, border: "1px solid #ccc" }}>暂无视频可播放</div>;
  }

  return (
    <div style={{ width: "100%", maxWidth: 600 }}>
      <video
        ref={videoRef}
        src={videoUrl}
        controls
        style={{ width: "100%", borderRadius: 8 }}
      />
    </div>
  );
}