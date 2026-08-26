import { NextRequest, NextResponse } from "next/server";

import {
  AUTH_COOKIE_NAME,
  callBackend,
  forwardBackendResponse,
} from "@/lib/server/backend";
import {
  consumeAttempt,
  requestCameFromSameOrigin,
} from "@/lib/server/request-guard";

type DemoSession = {
  access_token: string;
  expires_in_seconds: number;
  user: {
    id: string;
    display_name: string;
  };
};

export async function POST(request: NextRequest) {
  if (!requestCameFromSameOrigin(request)) {
    return NextResponse.json({ detail: "请求来源无效。" }, { status: 403 });
  }
  const rateLimit = consumeAttempt(request, "demo-session", 20, 10 * 60 * 1000);
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { detail: "演示会话请求过多，请稍后再试。" },
      {
        status: 429,
        headers: {
          "Cache-Control": "no-store",
          "Retry-After": String(rateLimit.retryAfterSeconds),
        },
      },
    );
  }
  const backendResponse = await callBackend("/api/auth/demo", {
    method: "POST",
  });
  if (!backendResponse.ok) {
    return forwardBackendResponse(backendResponse);
  }

  const payload = (await backendResponse.json()) as DemoSession;
  const response = NextResponse.json({ user: payload.user });
  response.cookies.set(AUTH_COOKIE_NAME, payload.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: payload.expires_in_seconds,
  });
  return response;
}
