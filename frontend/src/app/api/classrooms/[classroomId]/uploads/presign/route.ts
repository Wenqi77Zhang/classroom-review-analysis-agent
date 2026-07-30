import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ classroomId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/classrooms/${encodeURIComponent(classroomId)}/uploads/presign`,
  );
}
