import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ taskId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { taskId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
  );
}
