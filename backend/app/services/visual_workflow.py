from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from app.models import (
    PosterPlan,
    RevisionAction,
    RevisionPlan,
    RevisionRequest,
    VideoScene,
    VideoStoryboard,
    VisualAssetBundle,
    VisualAssetSpec,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_ROOT = (
    Path(os.environ["SCIENCE_POSTER_DATA_DIR"]) / "workflow"
    if os.getenv("SCIENCE_POSTER_DATA_DIR", "").strip()
    else PROJECT_ROOT / "artifacts" / "workflow"
)


def _safe_task_id(task_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", task_id).strip("-")
    return value[:100] or "untitled-task"


def persist_version(task_id: str, artifact_kind: str, payload: dict, root: Path = WORKFLOW_ROOT) -> str:
    task_dir = root / _safe_task_id(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(task_dir.glob(f"{artifact_kind}-v*.json"))
    version = len(existing) + 1
    path = task_dir / f"{artifact_kind}-v{version:03d}.json"
    envelope = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "secret_recorded": False,
        "artifact_kind": artifact_kind,
        "version": version,
        "payload": payload,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        display_path = path.relative_to(PROJECT_ROOT)
    except ValueError:
        display_path = path
    return str(display_path).replace("\\", "/")


def build_visual_asset_bundle(plan: PosterPlan, persist: bool = True) -> VisualAssetBundle:
    roles = ("hero_illustration", "mechanism_diagram", "context_background")
    role_guidance = (
        "建立一个明确的科学主视觉，主体单一、轮廓清楚",
        "用准确的空间关系和箭头表达机制，不把相关性画成直接因果",
        "提供克制的环境与尺度感，不使用灾难电影式夸张",
    )
    cards = plan.fact_cards[:3]
    assets: list[VisualAssetSpec] = []
    for index, card in enumerate(cards):
        claim = card.claim.strip()
        assets.append(
            VisualAssetSpec(
                asset_id=f"{plan.task_id}-asset-{index + 1:02d}",
                asset_type=roles[index],
                source_claim_ids=[card.claim_id],
                prompt=(
                    f"面向{plan.audience}的科学传播插图。{role_guidance[index]}。"
                    f"必须忠实表达事实：{claim}。视觉方向：{plan.visual_direction}。"
                    "画面内不要生成标题、段落、数字或来源文字，文字由SVG排版层统一添加。"
                ),
                negative_prompt=(
                    "错误科学结构、错误因果箭头、虚构数值、灾难化城市、爆炸电影海报、"
                    "文字乱码、水印、品牌Logo、不可辨识图表"
                ),
                must_show=[claim],
                must_not_show=[card.caveat] if card.caveat else [],
                aspect_ratio=plan.aspect_ratio,
            )
        )
    if not assets:
        assets.append(
            VisualAssetSpec(
                asset_id=f"{plan.task_id}-asset-01",
                asset_type="hero_illustration",
                source_claim_ids=[],
                prompt="等待权威事实卡后再生成科学主视觉。",
                negative_prompt="未经证据支持的科学事实、文字乱码、水印、Logo",
                must_show=[],
                must_not_show=["任何确定性科学断言"],
                aspect_ratio=plan.aspect_ratio,
                status="rejected",
            )
        )
    bundle = VisualAssetBundle(
        task_id=plan.task_id,
        status="planned" if cards else "needs_review",
        assets=assets,
        generation_budget_cny=10.0,
        max_candidates_per_asset=2,
        safety_note=(
            "真实生图前必须核对模型可用性与单价；关键文字、数字和来源不交给图像模型绘制；"
            "每项视觉资产必须关联至少一张已审核事实卡。"
        ),
    )
    if persist:
        path = persist_version(plan.task_id, "visual-assets", bundle.model_dump())
        bundle = bundle.model_copy(update={"manifest_path": path})
    return bundle


def build_revision_plan(request: RevisionRequest, persist: bool = True) -> RevisionPlan:
    actions: list[RevisionAction] = []
    evidence_blocked = False
    for issue in request.issues:
        if issue.category in {"fact", "causality", "number"}:
            evidence_blocked = True
            action = "request_more_sources" if issue.category in {"fact", "number"} else "human_science_review"
            instruction = (
                f"停止自动改写{issue.target_id}；回到事实卡和来源核验。问题：{issue.description}"
            )
        elif issue.category in {"layout", "color", "cropping"}:
            action = "patch_layout" if issue.category != "cropping" else "regenerate_asset"
            instruction = issue.suggested_fix or f"仅修订{issue.target_id}的{issue.category}问题。"
        elif issue.category == "readability":
            action = "patch_text"
            instruction = issue.suggested_fix or f"提高{issue.target_id}的字号、对比度与信息层级。"
        else:
            action = "human_science_review"
            instruction = issue.suggested_fix or f"由人工复核{issue.target_id}：{issue.description}"
        actions.append(
            RevisionAction(
                target_id=issue.target_id,
                action=action,
                instruction=instruction,
                requires_human_approval=True,
            )
        )
    plan = RevisionPlan(
        task_id=request.task_id,
        from_version=request.current_version,
        to_version=request.current_version + 1,
        iteration=min(request.current_version, 2),
        status="blocked_by_evidence" if evidence_blocked else "ready_for_review",
        actions=actions,
    )
    if persist:
        path = persist_version(request.task_id, "revision-plan", plan.model_dump())
        plan = plan.model_copy(update={"manifest_path": path})
    return plan


def build_video_storyboard(plan: PosterPlan, persist: bool = True) -> VideoStoryboard:
    sections = plan.sections[:6]
    duration = max(8, 60 // max(1, len(sections)))
    scenes: list[VideoScene] = []
    claim_ids = [card.claim_id for card in plan.fact_cards]
    for index, section in enumerate(sections):
        linked_claims = [claim_ids[index]] if index < len(claim_ids) else claim_ids[:1]
        narration = section.content_summary.strip()
        scenes.append(
            VideoScene(
                scene_id=f"{plan.task_id}-scene-{index + 1:02d}",
                duration_seconds=min(duration, 30),
                heading=section.heading,
                source_claim_ids=linked_claims,
                visual_prompt=(
                    f"科学科普短视频分镜：{section.visual_form}。{section.content_summary}。"
                    "镜头克制、结构准确、画面内不生成文字，字幕由后期叠加。"
                ),
                narration=narration,
                subtitle=narration,
            )
        )
    storyboard = VideoStoryboard(
        task_id=plan.task_id,
        title=plan.title,
        narration_mode="ai_voice_with_subtitles",
        scenes=scenes,
        total_duration_seconds=sum(scene.duration_seconds for scene in scenes),
    )
    if persist:
        path = persist_version(plan.task_id, "video-storyboard", storyboard.model_dump())
        storyboard = storyboard.model_copy(update={"manifest_path": path})
    return storyboard
