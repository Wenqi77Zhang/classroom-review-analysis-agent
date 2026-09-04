import { proxyAuthenticatedJson } from "@/lib/server/backend";
import {
  consumeAttempt,
  requestCameFromSameOrigin,
} from "@/lib/server/request-guard";

function guardedError(status: number, code: string, message: string, retryAfter?: number) {
  return Response.json(
    {
      error: {
        code,
        message,
        details: retryAfter ? { retry_after_seconds: retryAfter } : {},
        trace_id: `frontend-${crypto.randomUUID()}`,
      },
    },
    {
      status,
      headers: retryAfter ? { "Retry-After": String(retryAfter) } : undefined,
    },
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ classroomId: string }> },
) {
  if (!requestCameFromSameOrigin(request)) {
    return guardedError(403, "PERMISSION_DENIED", "跨站请求已被拒绝。");
  }
  const attempt = consumeAttempt(request, "review-dialogue", 20, 60_000);
  if (!attempt.allowed) {
    return guardedError(
      429,
      "RATE_LIMITED",
      "复盘 Agent 请求过于频繁，请稍后重试。",
      attempt.retryAfterSeconds,
    );
  }
  const { classroomId } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/classrooms/${encodeURIComponent(classroomId)}/review-dialogue`,
  );
}
