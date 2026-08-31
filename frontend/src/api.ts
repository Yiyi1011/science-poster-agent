import type {
  PosterPlan,
  PosterRequest,
  ReviewCategory,
  RevisionPlan,
  VideoStoryboard,
  VisualAssetBundle,
} from "./types";

async function readError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: string } | null;
  return new Error(payload?.detail || `${fallback}：${response.status}`);
}

export async function createPosterPlan(input: PosterRequest): Promise<PosterPlan> {
  const response = await fetch("/api/posters/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw await readError(response, "请求失败");
  }
  return response.json() as Promise<PosterPlan>;
}

export async function renderPoster(plan: PosterPlan): Promise<Blob> {
  const response = await fetch("/api/posters/render-svg", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  if (!response.ok) {
    throw await readError(response, "海报渲染失败");
  }
  return response.blob();
}

export async function createVisualAssetSpecs(plan: PosterPlan): Promise<VisualAssetBundle> {
  const response = await fetch("/api/visual-assets/specs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  if (!response.ok) throw await readError(response, "视觉资产规划失败");
  return response.json() as Promise<VisualAssetBundle>;
}

export async function createVideoStoryboard(plan: PosterPlan): Promise<VideoStoryboard> {
  const response = await fetch("/api/videos/storyboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  if (!response.ok) throw await readError(response, "视频分镜规划失败");
  return response.json() as Promise<VideoStoryboard>;
}

export async function createRevisionPlan(input: {
  taskId: string;
  version: number;
  category: ReviewCategory;
  feedback: string;
}): Promise<RevisionPlan> {
  const response = await fetch("/api/revisions/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task_id: input.taskId,
      current_version: input.version,
      user_feedback: input.feedback,
      issues: [{
        issue_id: `USER-${Date.now()}`,
        target_id: "poster-current",
        category: input.category,
        severity: ["fact", "causality", "number"].includes(input.category) ? "major" : "minor",
        description: input.feedback,
        evidence_claim_ids: [],
        suggested_fix: input.feedback,
      }],
    }),
  });
  if (!response.ok) throw await readError(response, "修订规划失败");
  return response.json() as Promise<RevisionPlan>;
}
