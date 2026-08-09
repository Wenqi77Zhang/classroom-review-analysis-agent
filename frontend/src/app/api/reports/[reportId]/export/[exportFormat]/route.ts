import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ reportId: string; exportFormat: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { reportId, exportFormat } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/reports/${encodeURIComponent(reportId)}/export/${encodeURIComponent(exportFormat)}`,
  );
}
