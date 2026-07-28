# 前端模块交接说明

## 当前状态

成员 1 与 Codex 已把经人工确认的“雾境竹影”临时原型迁入 Next.js，形成 `UI Baseline v1`。首页、创建课堂和复盘任务均可交互，但仍使用 Mock 数据，尚未连接后端、媒体处理或真实 Agent。

## 目录职责

- `src/components/baseline/`：成员 1 负责的产品流程与视觉基准，成员 2 可复用，不应无记录地整体改写。
- `src/components/upload/UploadPanel.tsx`：成员 1 已实现本地文件选择、格式/大小/重复校验与隐私提示；预签名接口尚未冻结，所以真实上传按钮保持禁用并明确标注。
- `src/components/evidence/`：成员 2 的证据工作台组件，继续实现播放器、时间轴、逐字稿和复核。
- `src/app/tasks/[taskId]/page.tsx`：当前承载成员 1 的复盘目标页；成员 2 应在契约确认后的下一阶段接入证据工作台。
- `src/app/globals.css`：共享设计令牌和第一版样式。若修改字体、字号下限、色板或玻璃材质，请在 PR 中说明原因并附前后截图。
- `public/assets/mist-bamboo-glass-v2.png`：已确认的背景资产；不要再提交旧版背景或 QA 截图。

## 本地运行

```powershell
npm ci
npm run dev
```

提交前至少运行：`npm test`、`npm run typecheck`、`npm run build`。详细基准见 `docs/ui-baseline-v1.md`。
