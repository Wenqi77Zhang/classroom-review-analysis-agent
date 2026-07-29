import type { ReviewStatus } from "@/types/contracts";

export const DEMO_REPORT_DRAFT_KEY = "classroom-review-demo-report-draft";

export type DemoReportDraft = {
  status: Extract<ReviewStatus, "accepted" | "modified">;
  note: string;
  savedAt: string;
};

export function saveDemoReportDraft(
  status: ReviewStatus,
  note: string,
): boolean {
  if (status !== "accepted" && status !== "modified") {
    return false;
  }
  sessionStorage.setItem(
    DEMO_REPORT_DRAFT_KEY,
    JSON.stringify({ status, note: note.trim(), savedAt: new Date().toISOString() }),
  );
  return true;
}

export function loadDemoReportDraft(): DemoReportDraft | null {
  const raw = sessionStorage.getItem(DEMO_REPORT_DRAFT_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<DemoReportDraft>;
    if (value.status !== "accepted" && value.status !== "modified") return null;
    return {
      status: value.status,
      note: typeof value.note === "string" ? value.note : "",
      savedAt: typeof value.savedAt === "string" ? value.savedAt : "",
    };
  } catch {
    return null;
  }
}
