from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PosterRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    audience: str = Field(default="普通公众", min_length=2, max_length=50)
    source_text: str = Field(
        default="",
        max_length=60_000,
        description="Authoritative source excerpts. Empty input must not yield asserted facts.",
    )
    visual_style: str = Field(default="现代、清晰、克制", max_length=200)
    aspect_ratio: Literal["3:4", "4:3", "1:1", "16:9"] = "3:4"


class EvidenceRef(BaseModel):
    source_id: str = ""
    locator: str = ""
    excerpt: str = ""


class FactCard(BaseModel):
    claim_id: str
    claim: str
    evidence_status: Literal["supported", "missing", "conflict"]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    caveat: str = ""

    @field_validator("evidence_status", mode="before")
    @classmethod
    def normalize_evidence_status(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        mapping = {
            "confirmed": "supported",
            "verified": "supported",
            "unsupported": "missing",
            "unknown": "missing",
            "contradicted": "conflict",
        }
        return mapping.get(value.lower(), value)

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_empty_evidence(cls, value: object) -> object:
        """Some model responses use an empty string for an empty evidence list."""
        if value is None or value == "":
            return []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [
                {
                    "source_id": item,
                    "locator": "retrieved_document_id",
                    "excerpt": "",
                }
                if isinstance(item, str)
                else item
                for item in value
            ]
        return value


class PosterSection(BaseModel):
    heading: str
    purpose: str
    visual_form: str
    content_summary: str


class PosterPlan(BaseModel):
    task_id: str
    mode: Literal["mock", "bailian"]
    status: Literal["ready", "needs_sources", "needs_human_review"]
    title: str
    subtitle: str
    audience: str
    aspect_ratio: str
    fact_cards: list[FactCard]
    sections: list[PosterSection]
    visual_direction: str
    missing_information: list[str]
    safety_note: str
    retrieval_status: str = "not_used"
    retrieval_max_score: float | None = None
    source_documents: list[str] = Field(default_factory=list)

    @field_validator("missing_information", "source_documents", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("safety_note", mode="before")
    @classmethod
    def normalize_safety_note(cls, value: object) -> object:
        """Accept a model-produced one-item list while keeping the API field textual."""
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        return value


class PublicConfig(BaseModel):
    app_env: str
    mock_ai: bool
    region: str
    text_model: str
    studio_model: str = "qwen3-max"
    knowledge_app_enabled: bool
    retrieval_min_score: float


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)
    session_id: str = Field(default="", max_length=200)


class KnowledgeReference(BaseModel):
    index_id: str = ""
    title: str = ""
    doc_id: str = ""
    doc_name: str = ""
    text: str = ""
    score: float


class KnowledgeAnswer(BaseModel):
    status: Literal["supported", "insufficient_evidence"]
    answer: str
    session_id: str = ""
    references: list[KnowledgeReference] = Field(default_factory=list)
    max_retrieval_score: float | None = None
    threshold: float
    gate_reason: str
    request_id: str = ""


class VisualAssetSpec(BaseModel):
    asset_id: str
    asset_type: Literal["hero_illustration", "mechanism_diagram", "context_background", "icon", "chart"]
    status: Literal["planned", "generating", "ready", "needs_review", "rejected"] = "planned"
    provider: str = "unassigned"
    model: str = ""
    source_claim_ids: list[str] = Field(default_factory=list)
    prompt: str
    negative_prompt: str
    must_show: list[str] = Field(default_factory=list)
    must_not_show: list[str] = Field(default_factory=list)
    aspect_ratio: str = "3:4"
    file_path: str = ""
    version: int = 1


class VisualAssetBundle(BaseModel):
    task_id: str
    status: Literal["planned", "partially_ready", "ready", "needs_review"] = "planned"
    assets: list[VisualAssetSpec]
    generation_budget_cny: float = 10.0
    max_candidates_per_asset: int = 2
    safety_note: str
    manifest_path: str = ""


class ImageGenerationResult(BaseModel):
    asset: VisualAssetSpec
    request_id: str
    output_count: int
    estimated_cost_cny: float
    price_assumption_cny_per_image: float
    manifest_path: str = ""


class TtsGenerationResult(BaseModel):
    scene_id: str
    model: str
    voice: str
    file_path: str
    character_count: int
    duration_seconds: float
    estimated_cost_cny: float
    request_id: str
    manifest_path: str = ""


class ReviewIssue(BaseModel):
    issue_id: str
    target_id: str
    category: Literal[
        "fact",
        "causality",
        "number",
        "readability",
        "layout",
        "color",
        "cropping",
        "safety",
        "copyright",
    ]
    severity: Literal["minor", "major", "critical"]
    description: str
    evidence_claim_ids: list[str] = Field(default_factory=list)
    suggested_fix: str = ""


class RevisionRequest(BaseModel):
    task_id: str
    current_version: int = Field(default=1, ge=1)
    issues: list[ReviewIssue]
    user_feedback: str = Field(default="", max_length=2000)


class RevisionAction(BaseModel):
    target_id: str
    action: Literal[
        "request_more_sources",
        "human_science_review",
        "regenerate_asset",
        "patch_layout",
        "patch_text",
        "no_change",
    ]
    instruction: str
    requires_human_approval: bool = True


class RevisionPlan(BaseModel):
    task_id: str
    from_version: int
    to_version: int
    iteration: int
    status: Literal["planned", "blocked_by_evidence", "ready_for_review"]
    actions: list[RevisionAction]
    max_automatic_iterations: int = 2
    manifest_path: str = ""


class VideoScene(BaseModel):
    scene_id: str
    duration_seconds: int = Field(ge=3, le=30)
    heading: str
    source_claim_ids: list[str] = Field(default_factory=list)
    visual_prompt: str
    narration: str
    subtitle: str
    status: Literal["planned", "generating", "ready", "needs_review"] = "planned"


class VideoStoryboard(BaseModel):
    task_id: str
    title: str
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    narration_mode: Literal["ai_voice_with_subtitles", "human_voice", "subtitles_only"] = "ai_voice_with_subtitles"
    scenes: list[VideoScene]
    total_duration_seconds: int
    status: Literal["planned", "ready", "needs_review"] = "planned"
    manifest_path: str = ""
