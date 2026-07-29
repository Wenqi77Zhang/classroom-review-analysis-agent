import { ReportEditor } from "@/components/reports/ReportEditor";
import { SiteChrome } from "@/components/baseline/SiteChrome";

export default function ReportPage() {
  return (
    <SiteChrome>
      <main className="report-page">
        <ReportEditor />
      </main>
    </SiteChrome>
  );
}
