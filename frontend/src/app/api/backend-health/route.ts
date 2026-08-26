import type { BackendHealthResponse } from "@/types/contracts";

export const dynamic = "force-dynamic";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8100";
const HEALTH_TIMEOUT_MS = 2000;

export async function GET() {
  const backendUrl = (
    process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL
  ).replace(/\/+$/, "");

  try {
    const livenessResponse = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    if (!livenessResponse.ok) {
      throw new Error("backend liveness unavailable");
    }
    const liveness = (await livenessResponse.json()) as { app_env?: unknown };

    try {
      const response = await fetch(`${backendUrl}/health/ready`, {
        cache: "no-store",
        signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
      });

      const payload = (await response.json()) as {
        status?: unknown;
        dependencies?: unknown;
      };

      const dependencies =
        payload.dependencies && typeof payload.dependencies === "object"
          ? (payload.dependencies as Record<string, unknown>)
          : {};

      return Response.json({
        reachable: true,
        status: response.ok && payload.status === "ready" ? "ok" : "unavailable",
        dependencies: {
          database: dependencies.database === "ok" ? "ok" : "unavailable",
          object_storage:
            dependencies.object_storage === "ok" ? "ok" : "unavailable",
        },
        traceId: response.headers.get("X-Trace-Id") ?? undefined,
      } satisfies BackendHealthResponse);
    } catch {
      // 后端进程在线但依赖检查超时：产品可打开并展示降级状态，上传仍保持禁用。
      return Response.json({
        reachable: true,
        status: "unavailable",
        appEnv:
          liveness.app_env === "development" ||
          liveness.app_env === "test" ||
          liveness.app_env === "production"
            ? liveness.app_env
            : undefined,
      } satisfies BackendHealthResponse);
    }
  } catch {
    // 不把内部地址、堆栈或连接错误暴露给浏览器；不可达属于可预期运行状态。
    return Response.json({
      reachable: false,
      status: "unavailable",
    } satisfies BackendHealthResponse);
  }
}
