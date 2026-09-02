import { NextRequest, NextResponse } from "next/server";

import {
  callBackend,
  forwardBackendResponse,
  setAuthCookie,
} from "@/lib/server/backend";
import {
  consumeAttempt,
  requestCameFromSameOrigin,
} from "@/lib/server/request-guard";

type LoginSession = {
  access_token: string;
  expires_in_seconds: number;
  user: { id: string; display_name: string };
};

export async function POST(request: NextRequest) {
  if (!requestCameFromSameOrigin(request)) {
    return NextResponse.json({ detail: "请求来源无效。" }, { status: 403 });
  }
  const rateLimit = consumeAttempt(request, "account-login", 8, 15 * 60 * 1000);
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { detail: "登录尝试过多，请稍后再试。" },
      {
        status: 429,
        headers: {
          "Cache-Control": "no-store",
          "Retry-After": String(rateLimit.retryAfterSeconds),
        },
      },
    );
  }

  const body = (await request.json().catch(() => null)) as
    | { email?: unknown; password?: unknown }
    | null;
  if (
    typeof body?.email !== "string" ||
    typeof body.password !== "string" ||
    body.email.length > 320 ||
    body.password.length > 1024
  ) {
    return NextResponse.json({ detail: "邮箱或密码格式不正确。" }, { status: 400 });
  }

  const backendResponse = await callBackend("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: body.email.trim(), password: body.password }),
  });
  if (!backendResponse.ok) return forwardBackendResponse(backendResponse);

  const payload = (await backendResponse.json()) as LoginSession;
  const response = NextResponse.json({ user: payload.user });
  setAuthCookie(response, payload.access_token, payload.expires_in_seconds);
  return response;
}
