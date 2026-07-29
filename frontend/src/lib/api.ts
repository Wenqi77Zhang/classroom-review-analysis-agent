import type { BackendHealthResponse } from "@/types/contracts";

// 当前唯一接通的是不带鉴权的真实健康检查。业务 API 仍由成员 2 在成员 3
// 完成路由后补鉴权、统一错误转换和重试；不得因为健康检查可用就启用上传按钮。
export const BUSINESS_API_NOT_IMPLEMENTED = true;

export async function getBackendHealth(
  signal?: AbortSignal,
): Promise<BackendHealthResponse> {
  const response = await fetch("/api/backend-health", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error("后端健康检查代理返回异常状态。");
  }

  return (await response.json()) as BackendHealthResponse;
}
