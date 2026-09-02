import { NextRequest, NextResponse } from "next/server";
import {
  getConfiguredTeamAccessCode,
  matchesTeamAccessCookie,
  TEAM_ACCESS_COOKIE_NAME,
} from "@/lib/server/team-access";

const PUBLIC_PATHS = new Set([
  "/team-access",
  "/api/team-access",
  "/api/backend-health",
]);

export function proxy(request: NextRequest) {
  const expectedAccessCode = getConfiguredTeamAccessCode();
  if (!expectedAccessCode || PUBLIC_PATHS.has(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const cookieValue = request.cookies.get(TEAM_ACCESS_COOKIE_NAME)?.value;
  if (matchesTeamAccessCookie(cookieValue, expectedAccessCode)) {
    return NextResponse.next();
  }

  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json(
      { detail: "团队联调访问会话无效，请重新输入访问码。" },
      {
        status: 401,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  const accessUrl = new URL("/team-access", request.url);
  accessUrl.searchParams.set(
    "next",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );
  return NextResponse.redirect(accessUrl);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|assets/).*)",
  ],
};
