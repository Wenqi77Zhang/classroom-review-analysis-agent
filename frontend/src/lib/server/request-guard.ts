import { createHash } from "node:crypto";

type AttemptWindow = { count: number; resetAt: number };

const attempts = new Map<string, AttemptWindow>();
const MAX_TRACKED_KEYS = 2_000;

function clientFingerprint(request: Request, scope: string): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || request.headers.get("x-real-ip")?.trim() || "unknown";
  return createHash("sha256")
    .update(`classroom-review:${scope}:${address}`, "utf8")
    .digest("hex");
}

/**
 * Small single-instance guard for public authentication edges.
 *
 * It stores only a one-way client fingerprint, never logs an IP, and bounds
 * memory. Multi-instance production deployments should additionally enforce
 * an edge/WAF rate limit; this guard remains a safe last line of defence.
 */
export function consumeAttempt(
  request: Request,
  scope: string,
  limit: number,
  windowMs: number,
): { allowed: boolean; retryAfterSeconds: number } {
  const now = Date.now();
  const key = clientFingerprint(request, scope);
  const current = attempts.get(key);
  if (!current || current.resetAt <= now) {
    if (attempts.size >= MAX_TRACKED_KEYS) {
      for (const [candidate, value] of attempts) {
        if (value.resetAt <= now) attempts.delete(candidate);
      }
      if (attempts.size >= MAX_TRACKED_KEYS) attempts.clear();
    }
    attempts.set(key, { count: 1, resetAt: now + windowMs });
    return { allowed: true, retryAfterSeconds: 0 };
  }
  current.count += 1;
  return {
    allowed: current.count <= limit,
    retryAfterSeconds: Math.max(1, Math.ceil((current.resetAt - now) / 1000)),
  };
}

export function requestCameFromSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  if (!origin) return true;
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const requestHost = forwardedHost || request.headers.get("host");
  try {
    return Boolean(requestHost) && new URL(origin).host === requestHost;
  } catch {
    return false;
  }
}
