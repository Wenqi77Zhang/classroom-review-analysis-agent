import { proxyAuthenticatedJson } from "@/lib/server/backend";

export async function POST(request: Request, context: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await context.params;
  return proxyAuthenticatedJson(request, `/api/tasks/${encodeURIComponent(taskId)}/retry`);
}
