import { NextRequest } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/server/backend";

export async function GET(request: NextRequest) {
  return proxyAuthenticatedJson(request, "/api/auth/me");
}
