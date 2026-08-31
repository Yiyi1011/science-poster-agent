from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import Settings
from app.models import ImageGenerationResult, VisualAssetSpec
from app.services.bailian_app_client import workspace_origin
from app.services.usage_ledger import record_image_usage, recorded_image_cost
from app.services.visual_workflow import persist_version


def parse_image_response(body: dict[str, Any]) -> tuple[str, str, int, int, int]:
    choices = (body.get("output") or {}).get("choices") or []
    if not choices:
        raise RuntimeError("Image response contains no choices.")
    content = ((choices[0].get("message") or {}).get("content") or [])
    image_url = next(
        (str(item.get("image")) for item in content if isinstance(item, dict) and item.get("image")),
        "",
    )
    if not image_url:
        raise RuntimeError("Image response contains no image URL.")
    usage = body.get("usage") or {}
    return (
        image_url,
        str(body.get("request_id") or body.get("requestId") or ""),
        int(usage.get("output_image_count") or usage.get("image_count") or 1),
        int(usage.get("output_width") or 0),
        int(usage.get("output_height") or 0),
    )


def validate_result_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "aliyuncs.com" or hostname.endswith(".aliyuncs.com")
    ):
        raise RuntimeError(
            "Result URL is not an approved Alibaba Cloud HTTPS host "
            f"(scheme={parsed.scheme or 'missing'}, host={hostname or 'missing'})."
        )


def secure_aliyun_result_url(url: str) -> str:
    """Upgrade an official Alibaba OSS result URL to HTTPS without widening the host allowlist."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and (
        hostname == "aliyuncs.com" or hostname.endswith(".aliyuncs.com")
    ):
        parsed = parsed._replace(scheme="https")
        url = urlunparse(parsed)
    validate_result_url(url)
    return url


class QwenImageClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        spec: VisualAssetSpec,
        output_dir: Path,
        size: str = "768*1024",
    ) -> ImageGenerationResult:
        self.settings.validate_for_image_generation()
        projected = recorded_image_cost() + self.settings.qwen_image_output_price
        if projected > self.settings.image_generation_budget_cny:
            raise RuntimeError("Image generation sub-budget would be exceeded.")

        prompt = f"{spec.prompt}\n严格避免：{spec.negative_prompt}"
        payload = {
            "model": self.settings.qwen_image_model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ]
            },
            "parameters": {
                "prompt_extend": False,
                "size": size,
                "n": 1,
                "watermark": True,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{workspace_origin(self.settings)}/api/v1/services/aigc/multimodal-generation/generation"
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            image_url, request_id, output_count, width, height = parse_image_response(body)
            # Generation is already billable even if the subsequent download fails.
            estimated_cost = record_image_usage(self.settings, request_id=request_id, output_count=output_count,
                output_width=width, output_height=height)
            image_url = secure_aliyun_result_url(image_url)
            image_response = await client.get(image_url)
            image_response.raise_for_status()

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{spec.asset_id}-v{spec.version:03d}.png"
        path.write_bytes(image_response.content)
        updated = spec.model_copy(
            update={
                "status": "needs_review",
                "provider": "Alibaba Cloud Model Studio",
                "model": self.settings.qwen_image_model,
                "file_path": str(path.relative_to(Path(__file__).resolve().parents[3])).replace("\\", "/"),
            }
        )
        result = ImageGenerationResult(
            asset=updated,
            request_id=request_id,
            output_count=output_count,
            estimated_cost_cny=estimated_cost,
            price_assumption_cny_per_image=self.settings.qwen_image_output_price,
        )
        manifest = persist_version(spec.asset_id, "image-generation", result.model_dump())
        return result.model_copy(update={"manifest_path": manifest})
