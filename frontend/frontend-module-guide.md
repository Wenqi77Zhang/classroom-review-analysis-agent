# 前端模块交接说明

## 当前状态

截至 `main@1e52c9c`，首页、课程/课堂创建、复盘任务和报告页面均可交互。
前端通过同源 BFF 使用 HttpOnly Cookie 保存短期演示会话，并已接通课程/课堂、
真实 B2 预签名上传、上传完成核验、任务创建和任务状态查询。成员 2 的证据组件
已经合并，但逐字稿、证据卡和结论仍使用醒目标注的演示数据；教师复核没有写入
后端，报告草稿只保存在当前浏览器会话。

## 目录职责

- `src/components/baseline/`：成员 1 负责的产品流程与视觉基准，成员 2 可复用，不应无记录地整体改写。
- `src/components/upload/UploadPanel.tsx`：负责本地选择、格式/大小/重复校验、隐私提示和真实上传编排；视频上传成功并通过后端 HEAD 核验后才可创建任务。
- `src/app/api/`：同源 BFF，覆盖演示会话、健康检查、课程/课堂、资源上传完成和任务创建/查询。BFF 不把服务令牌、长期对象存储密钥或后端内部地址返回浏览器。
- `src/lib/api.ts`、`src/types/contracts.ts`：封装已接通的业务请求和共享类型；逐字稿、真实结论、复核历史和报告 API 客户端尚未完成。
- `src/components/evidence/`：成员 2 原始实现的播放器、时间轴、证据卡和复核交互，经成员 1 与 Codex 审核后补齐类型、安全降级、Mock 标识、可访问性与静态契约测试。当前播放器不绑定假视频地址；只有取得后端短期授权地址后才能播放真实视频。复核状态仅保存在页面内，不得描述为已写入后端。
- `src/app/tasks/[taskId]/page.tsx`：承载复盘目标、分析契约、上传、任务状态和证据工作台；真实上传/任务数据与演示证据必须保持清晰区分。
- `src/app/globals.css`：共享设计令牌和第一版样式。若修改字体、字号下限、色板或玻璃材质，请在 PR 中说明原因并附前后截图。
- `public/assets/mist-bamboo-glass-v2.png`：已确认的背景资产；不要再提交旧版背景或 QA 截图。

## 本地运行

```powershell
npm ci
npm run dev
```

同时启动已正确配置 PostgreSQL 与 B2 的后端后，可执行真实上传和任务创建。任务创建
后的媒体处理依赖 Worker；当前 Worker/B2 集成仍在其他对话实现，尚未合并验收。

提交前至少运行：`npm test`、`npm run typecheck`、`npm run build`。`tests/evidence-workbench.test.mjs` 负责守住证据定位、教师复核和 Mock 边界；详细视觉基准见 `docs/ui-baseline-v1.md`。
