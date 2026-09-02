import { NextRequest, NextResponse } from "next/server";

import { clearAuthCookie } from "@/lib/server/backend";
import { requestCameFromSameOrigin } from "@/lib/server/request-guard";

export async function POST(request: NextRequest) {
  if (!requestCameFromSameOrigin(request)) {
    return NextResponse.json({ detail: "请求来源无效。" }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  clearAuthCookie(response);
  return response;
}
