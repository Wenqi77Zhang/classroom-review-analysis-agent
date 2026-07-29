import { proxyAuthenticatedJson } from "@/lib/server/backend";

export async function GET(request: Request) {
  return proxyAuthenticatedJson(request, "/api/courses");
}

export async function POST(request: Request) {
  return proxyAuthenticatedJson(request, "/api/courses");
}
