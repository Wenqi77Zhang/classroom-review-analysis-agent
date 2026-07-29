import { NextResponse } from "next/server";

import {
  AUTH_COOKIE_NAME,
  callBackend,
  forwardBackendResponse,
} from "@/lib/server/backend";

type DemoSession = {
  access_token: string;
  expires_in_seconds: number;
  user: {
    id: string;
    display_name: string;
  };
};

export async function POST() {
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
