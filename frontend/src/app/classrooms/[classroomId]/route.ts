import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ classroomId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/classrooms/${encodeURIComponent(classroomId)}/conclusions`,
  );
}