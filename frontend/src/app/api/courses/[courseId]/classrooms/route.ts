import { proxyAuthenticatedJson } from "@/lib/server/backend";

type RouteContext = {
  params: Promise<{ courseId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { courseId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/courses/${encodeURIComponent(courseId)}/classrooms`,
  );
}

export async function POST(request: Request, context: RouteContext) {
  const { courseId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/courses/${encodeURIComponent(courseId)}/classrooms`,
  );
}
