import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const AUTH_COOKIE_NAME = "classroom_review_access_token";

export function setAuthCookie(
  response: NextResponse,
  accessToken: string,
  expiresInSeconds: number,
) {
  response.cookies.set(AUTH_COOKIE_NAME, accessToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: expiresInSeconds,
  });
}

export function clearAuthCookie(response: NextResponse) {
  response.cookies.set(AUTH_COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8100";

function backendUrl(path: string) {
  const base = (process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL).replace(
    /\/+$/,
    "",
  );
  return `${base}${path}`;
}

function frontendError(
  status: number,
  code: string,
  message: string,
): Response {
  return Response.json(
    {
      error: {
        code,
        message,
        details: {},
        trace_id: `frontend-${crypto.randomUUID()}`,
      },
    },
    { status },
  );
}

export async function callBackend(
  path: string,
  init: RequestInit,
): Promise<Response> {
  try {
    return await fetch(backendUrl(path), {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });
  } catch {
    return frontendError(
      503,
      "UPSTREAM_UNAVAILABLE",
      "后端服务暂时不可用，请确认服务已启动后重试。",
    );
  }
}

export async function forwardBackendResponse(
  response: Response,
): Promise<Response> {
  const contentType = response.headers.get("content-type") ?? "application/json";
  const headers = new Headers({ "Content-Type": contentType });
  const traceId = response.headers.get("X-Trace-Id");
  if (traceId) {
    headers.set("X-Trace-Id", traceId);
  }
  if ([204, 205, 304].includes(response.status)) {
    headers.delete("Content-Type");
    return new Response(null, { status: response.status, headers });
  }
  const body = await response.text();
  return new Response(body, { status: response.status, headers });
}

export async function proxyAuthenticatedJson(
  request: Request,
  path: string,
): Promise<Response> {
  const token = (await cookies()).get(AUTH_COOKIE_NAME)?.value;
  if (!token) {
    return frontendError(401, "UNAUTHENTICATED", "请先建立安全演示会话。");
  }

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();
  const response = await callBackend(path, {
    method: request.method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body,
  });
  return forwardBackendResponse(response);
}
