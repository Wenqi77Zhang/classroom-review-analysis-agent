import { createHash, timingSafeEqual } from "node:crypto";

export const TEAM_ACCESS_COOKIE_NAME = "__Host-team_tunnel_access";
export const TEAM_ACCESS_MAX_AGE_SECONDS = 8 * 60 * 60;

const MINIMUM_ACCESS_CODE_LENGTH = 16;

export function getConfiguredTeamAccessCode(): string | null {
  const accessCode = process.env.TEAM_TUNNEL_ACCESS_CODE?.trim();
  if (!accessCode) {
    return null;
  }
  if (accessCode.length < MINIMUM_ACCESS_CODE_LENGTH) {
    throw new Error("TEAM_TUNNEL_ACCESS_CODE must contain at least 16 characters.");
  }
  return accessCode;
}

export function digestTeamAccessCode(accessCode: string): string {
  return createHash("sha256")
    .update(`classroom-review-team-tunnel:${accessCode}`, "utf8")
    .digest("hex");
}

export function matchesTeamAccessCode(candidate: string, expected: string): boolean {
  const candidateDigest = Buffer.from(digestTeamAccessCode(candidate), "hex");
  const expectedDigest = Buffer.from(digestTeamAccessCode(expected), "hex");
  return timingSafeEqual(candidateDigest, expectedDigest);
}

export function matchesTeamAccessCookie(cookieValue: string | undefined, expected: string): boolean {
  if (!cookieValue || !/^[a-f0-9]{64}$/.test(cookieValue)) {
    return false;
  }
  const suppliedDigest = Buffer.from(cookieValue, "hex");
  const expectedDigest = Buffer.from(digestTeamAccessCode(expected), "hex");
  return timingSafeEqual(suppliedDigest, expectedDigest);
}
