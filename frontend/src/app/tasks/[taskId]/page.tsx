import { ReviewTaskBaseline } from "@/components/baseline/ReviewTaskBaseline";

type ReviewTaskPageProps = {
  params: Promise<{ taskId: string }>;
};

export default async function ReviewTaskPage({ params }: ReviewTaskPageProps) {
  const { taskId } = await params;
  return <ReviewTaskBaseline resourceId={taskId} />;
}
