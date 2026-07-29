# 媒体处理 Worker 说明

负责人：成员 4；接口协作：成员 3、成员 5。

目的：把对象存储中的视频和课件加工成可检索证据。Worker 不生成教学判断。

当前最短闭环已经实现：

`真实视频 → FFmpeg 16 kHz 单声道 WAV → 本地 Whisper → 带毫秒时间戳逐字稿 → JobStore`

## 本地运行

项目要求 Python 3.13，并要求系统能直接运行 `ffmpeg`。Whisper 模型在第一次运行时
下载到本机缓存，不得提交模型目录。

```bash
python -m worker.runner "/绝对路径/课堂.mp4" \
  --output "/本地私有目录/transcript.json" \
  --model tiny
```

可用 `--language zh` 固定中文；不传则自动检测。`tiny` 适合快速联调，验收质量建议
使用 `small`，代价是下载和推理时间更长。

## 两段真实视频测试

```bash
CLASSROOM_TEST_VIDEOS="/路径/a.mp4:/路径/b.mp4" \
WHISPER_MODEL=tiny \
pytest tests/integration/test_video_pipeline.py
```

测试要求两段结果都非空、每段时间区间合法，且更换输入后逐字稿不同。

## 接入后端

`LocalJobStore` 用于本地验证；成员 3 的内部接口上线后使用 `HttpJobStore`。它已经按冻结
契约实现任务领取、续租、状态回写和逐字稿写入。服务令牌只能通过环境变量或部署密钥注入。

## 当前边界

- 已实现：真实视频读取、音频抽取、带时间戳 ASR、状态回写、失败记录、临时文件清理。
- 待实现：对象存储下载、长音频切片、逐句翻译、课件解析和证据索引。
- 未实现说话人分离，因此 `speaker` 为 `null`，不伪造教师或学生身份。
