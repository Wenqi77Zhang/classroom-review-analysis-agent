import { NextRequest, NextResponse } from "next/server";
import {
  digestTeamAccessCode,
  getConfiguredTeamAccessCode,
  matchesTeamAccessCode,
  TEAM_ACCESS_COOKIE_NAME,
  TEAM_ACCESS_MAX_AGE_SECONDS,
} from "@/lib/server/team-access";
import {
  consumeAttempt,
  requestCameFromSameOrigin,
} from "@/lib/server/request-guard";

const MAXIMUM_ACCESS_CODE_LENGTH = 256;

export function GET() {
  const accessCode = getConfiguredTeamAccessCode();
  const instanceId = process.env.TEAM_TUNNEL_INSTANCE_ID?.trim();
  if (!accessCode || !instanceId) {
    return NextResponse.json(
      { enabled: false },
      {
        status: 404,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
  return NextResponse.json(
    { enabled: true, instanceId },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: NextRequest) {
  if (!requestCameFromSameOrigin(request)) {
    return NextResponse.json({ detail: "请求来源无效。" }, { status: 403 });
  }

  const expectedAccessCode = getConfiguredTeamAccessCode();
  if (!expectedAccessCode) {
    return NextResponse.json(
      { detail: "当前没有启用团队联调门禁。" },
      { status: 404 },
    );
  }

  const rateLimit = consumeAttempt(request, "team-access", 8, 10 * 60 * 1000);
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { detail: "尝试次数过多，请稍后再试。" },
      {
        status: 429,
        headers: {
          "Cache-Control": "no-store",
          "Retry-After": String(rateLimit.retryAfterSeconds),
        },
      },
    );
  }

  const body = (await request.json().catch(() => null)) as {
    accessCode?: unknown;
  } | null;
  const candidate =
    typeof body?.accessCode === "string" ? body.accessCode.trim() : "";
  const validLength =
    candidate.length >= 1 && candidate.length <= MAXIMUM_ACCESS_CODE_LENGTH;

  if (!validLength || !matchesTeamAccessCode(candidate, expectedAccessCode)) {
    await new Promise((resolve) => setTimeout(resolve, 350));
    return NextResponse.json(
      { detail: "访问码不正确，请向组长确认本次联调访问码。" },
      {
        status: 401,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: TEAM_ACCESS_COOKIE_NAME,
    value: digestTeamAccessCode(expectedAccessCode),
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: TEAM_ACCESS_MAX_AGE_SECONDS,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
