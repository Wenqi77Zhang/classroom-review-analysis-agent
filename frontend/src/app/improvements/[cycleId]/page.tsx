import { ImprovementCycleWorkspace } from "@/components/improvements/ImprovementCycleWorkspace";

export default async function ImprovementCyclePage({
  params,
}: {
  params: Promise<{ cycleId: string }>;
}) {
  const { cycleId } = await params;
  return <ImprovementCycleWorkspace cycleId={cycleId} />;
}
