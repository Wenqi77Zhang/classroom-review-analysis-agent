"use client";

import { RealReportEditor } from "@/components/reports/RealReportEditor";

export function ReportEditor({ classroomId }: { classroomId: string }) {
  return <RealReportEditor classroomId={classroomId} />;
}
