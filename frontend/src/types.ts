export type PosterRequest = {
  topic: string;
  audience: string;
  source_text: string;
  visual_style: string;
  aspect_ratio: "3:4" | "4:3" | "1:1" | "16:9";
};

export type PosterPlan = {
  task_id: string;
  mode: "mock" | "bailian";
  status: "ready" | "needs_sources" | "needs_human_review";
  title: string;
  subtitle: string;
  audience: string;
  aspect_ratio: string;
  fact_cards: Array<{
    claim_id: string;
    claim: string;
    evidence_status: "supported" | "missing" | "conflict";
    evidence: Array<{ source_id: string; locator: string; excerpt: string }>;
    caveat: string;
  }>;
  sections: Array<{
    heading: string;
    purpose: string;
    visual_form: string;
    content_summary: string;
  }>;
  visual_direction: string;
  missing_information: string[];
  safety_note: string;
  retrieval_status: string;
  retrieval_max_score: number | null;
  source_documents: string[];
};

export type VisualAssetBundle = {
  task_id: string;
  status: "planned" | "partially_ready" | "ready" | "needs_review";
  assets: Array<{
    asset_id: string;
    asset_type: "hero_illustration" | "mechanism_diagram" | "context_background" | "icon" | "chart";
    status: "planned" | "generating" | "ready" | "needs_review" | "rejected";
    source_claim_ids: string[];
    must_show: string[];
  }>;
  generation_budget_cny: number;
  max_candidates_per_asset: number;
  safety_note: string;
  manifest_path: string;
};

export type VideoStoryboard = {
  task_id: string;
  title: string;
  aspect_ratio: "16:9" | "9:16" | "1:1";
  narration_mode: "ai_voice_with_subtitles" | "human_voice" | "subtitles_only";
  scenes: Array<{
    scene_id: string;
    duration_seconds: number;
    heading: string;
    source_claim_ids: string[];
    narration: string;
    subtitle: string;
    status: "planned" | "generating" | "ready" | "needs_review";
  }>;
  total_duration_seconds: number;
  status: "planned" | "ready" | "needs_review";
  manifest_path: string;
};

export type ReviewCategory = "fact" | "causality" | "number" | "readability" | "layout" | "color" | "cropping";

export type RevisionPlan = {
  task_id: string;
  from_version: number;
  to_version: number;
  iteration: number;
  status: "planned" | "blocked_by_evidence" | "ready_for_review";
  actions: Array<{
    target_id: string;
    action: string;
    instruction: string;
    requires_human_approval: boolean;
  }>;
  max_automatic_iterations: number;
  manifest_path: string;
};
