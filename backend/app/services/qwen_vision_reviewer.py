from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import PosterPlan
from app.services.usage_ledger import record_vision_review_usage
from app.services.visual_workflow import persist_version


def parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise RuntimeError("Vision review response must be a JSON object.")
    return value


class QwenVisionReviewer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def review(self, image_path: Path, plan: PosterPlan) -> dict[str, Any]:
        self.settings.validate_for_vision_review()
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        fact_contract = [
            {
                "claim_id": card.claim_id,
                "claim": card.claim,
                "caveat": card.caveat,
            }
            for card in plan.fact_cards
        ]
        prompt = (
            "你是科学信息图视觉质检员。检查上传海报，不补写图外事实。"
            "以JSON返回：status(pass|needs_revision)、scores(object，含readability、hierarchy、"
            "scientific_consistency、source_visibility，0到100整数)、issues(array，每项含"
            "issue_id、category、severity、target、description、suggested_fix)、summary。"
            "重点找：字号过小、对比不足、信息拥挤、伪文字、品牌模仿、三类信使混淆、"
            "时间顺序错配、绝对化因果和来源不可读。看不清时明确说看不清，不猜测。"
            f"事实契约：{json.dumps(fact_contract, ensure_ascii=False)}"
        )
        payload = {
            "model": self.settings.qwen_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 3200,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{self.settings.dashscope_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        body = response.json()
        cost = record_vision_review_usage(self.settings, body)
        raw_content = body["choices"][0]["message"]["content"]
        try:
            review = parse_json_content(raw_content)
        except Exception as exc:
            persist_version(
                plan.task_id,
                "vision-review-raw",
                {
                    "model": self.settings.qwen_vision_model,
                    "raw_content": raw_content,
                    "parse_error": type(exc).__name__,
                    "estimated_cost_cny": cost,
                    "request_id": body.get("id", ""),
                    "secret_recorded": False,
                },
            )
            raise
        envelope = {
            "model": self.settings.qwen_vision_model,
            "image_file": str(image_path.relative_to(Path(__file__).resolve().parents[3])).replace("\\", "/"),
            "review": review,
            "estimated_cost_cny": cost,
            "request_id": body.get("id", ""),
            "human_review_required": True,
        }
        manifest = persist_version(plan.task_id, "vision-review", envelope)
        return {**envelope, "manifest_path": manifest}
