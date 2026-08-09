import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ reportId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { reportId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/reports/${encodeURIComponent(reportId)}/export`,
  );
}
