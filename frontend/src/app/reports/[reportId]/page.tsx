import { ReportEditor } from "@/components/reports/ReportEditor";
import { SiteChrome } from "@/components/baseline/SiteChrome";

type ReportPageProps = {
  params: Promise<{ reportId: string }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
  const { reportId } = await params;
  return (
    <SiteChrome>
      <main className="report-page">
        <ReportEditor classroomId={reportId} />
      </main>
    </SiteChrome>
  );
}
