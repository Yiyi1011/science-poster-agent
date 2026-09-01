"""Bounded data contracts for the source-isolated, cross-topic studio."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlsplit


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(StrictModel):
    source_id: str = Field(pattern=r"^S[1-9][0-9]{0,2}$")
    title: str = Field(min_length=2, max_length=160)
    url: str = Field(default="", max_length=1000)
    text: str = Field(min_length=20, max_length=15000)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("来源链接请使用不含账号信息的HTTPS地址；本应用不会自动抓取链接")
            if parsed.query or parsed.fragment:
                raise ValueError("请填写不含查询参数或签名的公开来源地址")
        return value


class ProjectInput(StrictModel):
    topic: str = Field(min_length=2, max_length=160)
    audience: str = Field(default="普通公众", min_length=2, max_length=50)
    sources: list[Source] = Field(default_factory=list, max_length=6)
    auto_sources: bool = False

    @model_validator(mode="after")
    def source_limits(self):
        if len({s.source_id for s in self.sources}) != len(self.sources):
            raise ValueError("来源编号不能重复")
        if sum(len(s.text) for s in self.sources) > 24000:
            raise ValueError("资料合计最多24000字，请精选与问题相关的摘录")
        return self


class Claim(StrictModel):
    claim_id: str = Field(pattern=r"^C[1-9][0-9]?$" )
    text: str = Field(min_length=2, max_length=160)
    source_id: str
    quote: str = Field(min_length=12, max_length=500)
    boundary: str = Field(min_length=2, max_length=160)


class Diagram(StrictModel):
    kind: Literal["sequence", "comparison", "cycle"]
    labels: list[str] = Field(min_length=2, max_length=4)
    caption: str = Field(min_length=2, max_length=90)

    @field_validator("labels")
    @classmethod
    def short_labels(cls, value: list[str]) -> list[str]:
        if any(not label.strip() or len(label) > 12 for label in value):
            raise ValueError("图解节点须为1—12字")
        return value


class Scene(StrictModel):
    scene_id: str = Field(pattern=r"^V[1-9][0-9]?$" )
    heading: str = Field(min_length=2, max_length=20)
    narration: str = Field(min_length=8, max_length=180)
    visual_action: str = Field(min_length=8, max_length=160)
    claim_ids: list[str] = Field(min_length=1, max_length=6)
    role: Literal["hook", "example", "mechanism", "process", "misconception", "boundary", "takeaway"] | None = None


class PublicCard(StrictModel):
    heading: str = Field(min_length=2, max_length=12)
    body: str = Field(min_length=8, max_length=64)
    claim_ids: list[str] = Field(min_length=1, max_length=4)


class VisualNode(StrictModel):
    label: str = Field(min_length=2, max_length=10)
    detail: str = Field(min_length=6, max_length=32)
    icon: Literal["chat", "book", "search", "check", "clock", "spark", "question"]
    claim_ids: list[str] = Field(min_length=1, max_length=4)


class PublicPoster(StrictModel):
    """Public copy is separate from verbatim evidence; every element is traceable."""
    cards: list[PublicCard] = Field(min_length=2, max_length=3)
    example: PublicCard
    caution: PublicCard
    nodes: list[VisualNode] = Field(min_length=2, max_length=4)


class ExplanationStep(StrictModel):
    heading: str = Field(min_length=2, max_length=20)
    body: str = Field(min_length=50, max_length=220)
    claim_ids: list[str] = Field(min_length=1, max_length=4)


class LearningCheck(StrictModel):
    question: str = Field(min_length=8, max_length=100)
    answer: str = Field(min_length=15, max_length=180)
    claim_ids: list[str] = Field(min_length=1, max_length=4)


class StudioDraft(StrictModel):
    title: str = Field(min_length=2, max_length=24)
    takeaway: str = Field(min_length=8, max_length=80)
    claims: list[Claim] = Field(min_length=1, max_length=4)
    diagram: Diagram
    # Old three-scene projects remain readable; new generation has a separate quality gate.
    scenes: list[Scene] = Field(min_length=3, max_length=8)
    public_poster: PublicPoster | None = None
    explainer: list[ExplanationStep] = Field(default_factory=list, max_length=5)
    learning_check: LearningCheck | None = None


class Finding(StrictModel):
    target: str = Field(min_length=1, max_length=60)
    severity: Literal["info", "warning", "blocker"]
    message: str = Field(min_length=2, max_length=400)


class Review(StrictModel):
    findings: list[Finding] = Field(default_factory=list, max_length=16)
    revised: StudioDraft | None = None


class RunInput(StrictModel):
    request_id: UUID
    expected_version: int = Field(ge=0)
    feedback: str = Field(default="", max_length=1000)
    rebuild: bool = False
    make_video: bool = False


class MediaInput(StrictModel):
    request_id: UUID
    expected_version: int = Field(ge=1)
    renderer: Literal["cartoon", "illustrated"] = "cartoon"
    proceed_from_blocked: bool = False  # 用户明确确认：直接用未完全通过检查的现有分镜制作
