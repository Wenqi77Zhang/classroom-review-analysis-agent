import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = { params: Promise<{ segmentId: string }> };

export async function PATCH(request: Request, context: RouteContext) {
  const { segmentId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/transcript-segments/${encodeURIComponent(segmentId)}`,
  );
}
