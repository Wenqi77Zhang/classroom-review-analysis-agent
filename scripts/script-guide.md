# 辅助脚本说明

根目录的 `setup/start/verify` 是用户入口；本目录保存辅助检查脚本。

脚本必须支持重复执行、清晰退出码和脱敏输出，不得自动写入真实密钥或静默申请管理员权限。

## `start-team-tunnel.ps1`

这是成员 1 在最终部署尚未完成前使用的 Windows 临时团队联调脚本，不是生产部署入口。
它要求本机 PostgreSQL、后端和 B2 配置已就绪，随后：

- 生成不落盘的一次性高强度访问码；
- 构建并启动生产版 Next.js；
- 只通过 Cloudflare Quick Tunnel 暴露 `127.0.0.1:3000`；
- 在退出时停止由脚本启动的前端进程。

脚本不会开放 8000、5432、MinIO 控制台或其他内部端口，也不会安装软件、修改 B2 CORS
或读取并打印 `.env` 秘密。安装方式、运行顺序、B2 CORS 和安全边界统一见
`../docs/local-development-setup.md` 第 6 节。

## `runtime_preflight.py` 与 `run_service_loop.py`

统一启动入口先用 `runtime_preflight.py` 检查项目内 `.venv`、本机 `.env`、必需配置与
Worker/Agent 令牌隔离，再由 `run_service_loop.py` 以环境变量传递服务令牌并常驻轮询。
两者不会把令牌写入命令行；停止统一入口时会向当前子进程转发终止信号并清理进程。

## `configure-team-tunnel-cors.py`

该脚本使用持有者本机 `.env` 中的受限 B2 Application Key，为本次
`https://<随机名称>.trycloudflare.com` 添加精确的专用 CORS 规则；它不会输出 Bucket、
端点或密钥，也会保留原有其他规则。入口关闭后必须执行 `remove` 清理专用规则。
