import { cpSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const standalone = join(root, ".next", "standalone");
if (!existsSync(join(standalone, "server.js"))) {
  throw new Error("尚未生成生产版本，请先运行 npm run build。");
}
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i += 2) {
  const name = args[i];
  const value = args[i + 1];
  if ((name === "--port" || name === "-p") && value && /^\d+$/.test(value) && Number(value) > 0 && Number(value) < 65536) process.env.PORT = value;
  else if ((name === "--hostname" || name === "-H") && value) process.env.HOSTNAME = value;
  else throw new Error("启动参数仅支持 --port 端口号、--hostname 主机名。");
}
process.env.HOSTNAME ??= "127.0.0.1";
process.env.PORT ??= "3000";
for (const relative of ["public", ".next/static"]) {
  const source = join(root, relative);
  if (existsSync(source)) cpSync(source, join(standalone, relative), { recursive: true });
}
await import(pathToFileURL(join(standalone, "server.js")).href);
