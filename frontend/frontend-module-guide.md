# 前端模块交接说明

## 当前状态

成员 1 与 Codex 已把经人工确认的“雾境竹影”临时原型迁入 Next.js，形成 `UI Baseline v1`。首页、创建课堂和复盘任务均可交互；成员 2 的证据组件已在成员 1 审核后整合到“待教师复核”演示状态。前端可通过同源代理检查后端基础健康状态，但业务数据仍使用 Mock，真实上传、媒体处理、视频授权地址、复核持久化和 Agent 均尚未接通。

## 目录职责

- `src/components/baseline/`：成员 1 负责的产品流程与视觉基准，成员 2 可复用，不应无记录地整体改写。
- `src/components/upload/UploadPanel.tsx`：成员 1 已实现本地文件选择、格式/大小/重复校验与隐私提示；资料类型和大小限制已与后端冻结契约统一。真实上传路由尚未实现，所以按钮保持禁用并明确标注。
- `src/app/api/backend-health/route.ts`：Next.js 服务端同源代理，只调用后端真实 `/health`，默认目标为 `http://localhost:8000`，可用 `BACKEND_URL` 覆盖。它只证明基础服务可达，不代表上传等业务接口已经实现；异常响应不会向浏览器暴露后端地址或堆栈。
- `src/lib/api.ts`、`src/types/contracts.ts`：目前只封装健康检查和本阶段使用的共享前端类型；完整业务 API 客户端仍是 TODO（成员 2 / 成员 3）。
- `src/components/evidence/`：成员 2 原始实现的播放器、时间轴、证据卡和复核交互，经成员 1 与 Codex 审核后补齐类型、安全降级、Mock 标识、可访问性与静态契约测试。当前播放器不绑定假视频地址；只有取得后端短期授权地址后才能播放真实视频。复核状态仅保存在页面内，不得描述为已写入后端。
- `src/app/tasks/[taskId]/page.tsx`：当前承载成员 1 的复盘目标页；成员 2 应在契约确认后的下一阶段接入证据工作台。
- `src/app/globals.css`：共享设计令牌和第一版样式。若修改字体、字号下限、色板或玻璃材质，请在 PR 中说明原因并附前后截图。
- `public/assets/mist-bamboo-glass-v2.png`：已确认的背景资产；不要再提交旧版背景或 QA 截图。

## 本地运行

```powershell
npm ci
npm run dev
```

同时启动后端后，上传区会显示“后端基础服务可达 · 上传接口待实现”；后端未启动时，本地文件校验仍可使用。

提交前至少运行：`npm test`、`npm run typecheck`、`npm run build`。`tests/evidence-workbench.test.mjs` 负责守住证据定位、教师复核和 Mock 边界；详细视觉基准见 `docs/ui-baseline-v1.md`。
