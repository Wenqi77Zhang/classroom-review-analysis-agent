import { proxyAuthenticatedJson } from "@/lib/server/backend";

export async function GET(request: Request) {
  const source = new URL(request.url).searchParams;
  const target = new URLSearchParams();
  const classroomId = source.get("classroom_id");
  if (classroomId) target.set("classroom_id", classroomId);
  target.set("limit", source.get("limit") ?? "1");
  target.set("offset", source.get("offset") ?? "0");
  return proxyAuthenticatedJson(request, `/api/tasks?${target.toString()}`);
}
