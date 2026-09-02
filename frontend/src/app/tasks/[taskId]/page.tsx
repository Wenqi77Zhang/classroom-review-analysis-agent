import { ReviewTaskBaseline } from "@/components/baseline/ReviewTaskBaseline";

type ReviewTaskPageProps = {
  params: Promise<{ taskId: string }>;
  searchParams: Promise<{ from?: string }>;
};

export default async function ReviewTaskPage({ params, searchParams }: ReviewTaskPageProps) {
  const { taskId } = await params;
  const { from } = await searchParams;
  return (
    <ReviewTaskBaseline
      resourceId={taskId}
      resourceKind={from === "classroom" ? "classroom" : "unknown"}
    />
  );
}
