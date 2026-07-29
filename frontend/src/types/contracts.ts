// 与 backend/app/schemas/ 和 docs/interface-contracts.md 对齐。
// TODO(成员 2，契约成员 3/5)：后续补齐全部业务类型，并建立自动生成或漂移检查。
export type AssetKind = "video" | "courseware" | "transcript";
export type ReviewStatus = "pending" | "accepted" | "modified" | "rejected";
export type ConclusionType = "fact" | "judgment" | "suggestion";

export type BackendHealthResponse = {
  reachable: boolean;
  status: "ok" | "unavailable";
  appEnv?: "development" | "test" | "production";
  traceId?: string;
};
