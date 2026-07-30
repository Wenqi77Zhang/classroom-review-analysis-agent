import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ conclusionId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { conclusionId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/conclusions/${encodeURIComponent(conclusionId)}/history`,
  );
}
