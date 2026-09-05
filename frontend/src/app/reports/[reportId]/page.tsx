import { ReportEditor } from "@/components/reports/ReportEditor";
import { SiteChrome } from "@/components/baseline/SiteChrome";
import { redirect } from "next/navigation";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type ReportPageProps = {
  params: Promise<{ reportId: string }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
  const { reportId } = await params;
  if (!UUID_PATTERN.test(reportId)) {
    redirect("/classrooms#owned-classrooms");
  }
  return (
    <SiteChrome>
      <main className="report-page">
        <ReportEditor classroomId={reportId} />
      </main>
    </SiteChrome>
  );
}
