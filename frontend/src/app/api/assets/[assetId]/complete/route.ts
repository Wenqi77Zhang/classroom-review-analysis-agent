import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ assetId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { assetId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/assets/${encodeURIComponent(assetId)}/complete`,
  );
}
