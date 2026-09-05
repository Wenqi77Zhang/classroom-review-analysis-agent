import { ReviewTaskBaseline } from "@/components/baseline/ReviewTaskBaseline";
import { redirect } from "next/navigation";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type ReviewTaskPageProps = {
  params: Promise<{ taskId: string }>;
  searchParams: Promise<{ from?: string }>;
};

export default async function ReviewTaskPage({ params, searchParams }: ReviewTaskPageProps) {
  const { taskId } = await params;
  const { from } = await searchParams;
  if (!UUID_PATTERN.test(taskId)) {
    redirect("/classrooms#owned-classrooms");
  }
  return (
    <ReviewTaskBaseline
      resourceId={taskId}
      resourceKind={from === "classroom" ? "classroom" : "unknown"}
    />
  );
}
