import { proxyAuthenticatedJson } from "@/lib/server/backend";

export async function GET(
  request: Request,
  context: { params: Promise<{ classroomId: string }> },
) {
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(request, `/api/classrooms/${encodeURIComponent(classroomId)}`);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ classroomId: string }> },
) {
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/classrooms/${encodeURIComponent(classroomId)}`,
  );
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ classroomId: string }> },
) {
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/classrooms/${encodeURIComponent(classroomId)}`,
  );
}
