import type { BackendHealthResponse } from "@/types/contracts";

export const dynamic = "force-dynamic";

const DEFAULT_BACKEND_URL = "http://localhost:8000";
const HEALTH_TIMEOUT_MS = 2000;

export async function GET() {
  const backendUrl = (
    process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL
  ).replace(/\/+$/, "");

  try {
    const response = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });

    if (!response.ok) {
      return Response.json({
        reachable: false,
        status: "unavailable",
      } satisfies BackendHealthResponse);
    }

    const payload = (await response.json()) as {
      status?: unknown;
      app_env?: unknown;
    };

    if (payload.status !== "ok") {
      return Response.json({
        reachable: false,
        status: "unavailable",
      } satisfies BackendHealthResponse);
    }

    const appEnv =
      payload.app_env === "development" ||
      payload.app_env === "test" ||
      payload.app_env === "production"
        ? payload.app_env
        : undefined;

    return Response.json({
      reachable: true,
      status: "ok",
      appEnv,
      traceId: response.headers.get("X-Trace-Id") ?? undefined,
    } satisfies BackendHealthResponse);
  } catch {
    // 不把内部地址、堆栈或连接错误暴露给浏览器；不可达属于可预期运行状态。
    return Response.json({
      reachable: false,
      status: "unavailable",
    } satisfies BackendHealthResponse);
  }
}
