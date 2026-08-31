from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.config import Settings


def _usage_path() -> Path:
    runtime_data_dir = os.getenv("SCIENCE_POSTER_DATA_DIR", "").strip()
    if runtime_data_dir:
        return Path(runtime_data_dir) / "evidence" / "model-usage.jsonl"
    return Path(__file__).resolve().parents[3] / "evidence" / "model-usage.jsonl"


def estimate_text_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    return round(
        (prompt_tokens * input_price_per_million + completion_tokens * output_price_per_million)
        / 1_000_000,
        6,
    )


def record_text_usage(
    settings: Settings,
    response_body: dict,
    purpose: str,
) -> None:
    usage = response_body.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    estimated_cost = estimate_text_cost(
        prompt_tokens,
        completion_tokens,
        settings.qwen_input_price_per_million,
        settings.qwen_output_price_per_million,
    )
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(settings.dashscope_base_url).hostname,
        "model": settings.qwen_text_model,
        "purpose": purpose,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_cny": estimated_cost,
        "price_assumption_cny_per_million": {
            "input": settings.qwen_input_price_per_million,
            "output": settings.qwen_output_price_per_million,
        },
        "request_id": response_body.get("id", ""),
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_application_usage(
    settings: Settings,
    response_body: dict,
    purpose: str,
) -> None:
    """Record aggregate tokens from a Bailian application call without content."""
    models = (response_body.get("usage") or {}).get("models") or []
    prompt_tokens = sum(int(item.get("input_tokens") or 0) for item in models)
    completion_tokens = sum(int(item.get("output_tokens") or 0) for item in models)
    estimated_cost = estimate_text_cost(
        prompt_tokens,
        completion_tokens,
        settings.qwen_input_price_per_million,
        settings.qwen_output_price_per_million,
    )
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(
            settings.dashscope_app_base_url
            or settings.dashscope_base_url.replace("/compatible-mode/v1", "/api/v1")
        ).hostname,
        "model": ",".join(
            sorted({str(item.get("model_id") or "unknown") for item in models})
        ),
        "purpose": purpose,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_cny": estimated_cost,
        "price_assumption_cny_per_million": {
            "input": settings.qwen_input_price_per_million,
            "output": settings.qwen_output_price_per_million,
        },
        "request_id": response_body.get("request_id", ""),
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_retrieval_usage(
    settings: Settings,
    request_id: str,
    result_count: int,
    max_score: float | None,
    purpose: str,
) -> None:
    """Record a retrieval call without pretending rerank billing is text-token billing."""
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(settings.dashscope_base_url).hostname,
        "model": "qwen3-rerank",
        "purpose": purpose,
        "result_count": result_count,
        "max_retrieval_score": max_score,
        "estimated_cost_cny": None,
        "billing_note": "Retrieval/rerank cost must be reconciled from the Bailian bill.",
        "request_id": request_id,
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recorded_image_cost() -> float:
    path = _usage_path()
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("purpose") == "image_generation":
            total += float(entry.get("estimated_cost_cny") or 0)
    return round(total, 6)


def record_image_usage(
    settings: Settings,
    request_id: str,
    output_count: int,
    output_width: int,
    output_height: int,
) -> float:
    estimated_cost = round(output_count * settings.qwen_image_output_price, 6)
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(settings.dashscope_base_url).hostname,
        "model": settings.qwen_image_model,
        "purpose": "image_generation",
        "output_count": output_count,
        "output_width": output_width,
        "output_height": output_height,
        "estimated_cost_cny": estimated_cost,
        "price_assumption_cny_per_image": settings.qwen_image_output_price,
        "request_id": request_id,
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return estimated_cost


def recorded_tts_cost() -> float:
    path = _usage_path()
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("purpose") == "tts_generation":
            total += float(entry.get("estimated_cost_cny") or 0)
    return round(total, 6)


def record_tts_usage(
    settings: Settings,
    request_id: str,
    character_count: int,
    duration_seconds: float,
) -> float:
    estimated_cost = round(
        character_count / 10_000 * settings.qwen_tts_price_per_10k_chars,
        6,
    )
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(settings.dashscope_base_url).hostname,
        "model": settings.qwen_tts_model,
        "purpose": "tts_generation",
        "character_count": character_count,
        "duration_seconds": round(duration_seconds, 3),
        "estimated_cost_cny": estimated_cost,
        "price_assumption_cny_per_10k_chars": settings.qwen_tts_price_per_10k_chars,
        "request_id": request_id,
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return estimated_cost


def record_vision_review_usage(settings: Settings, response_body: dict) -> float:
    usage = response_body.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    estimated_cost = estimate_text_cost(
        prompt_tokens,
        completion_tokens,
        settings.qwen_vision_input_price_per_million,
        settings.qwen_vision_output_price_per_million,
    )
    entry = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "endpoint_host": urlparse(settings.dashscope_base_url).hostname,
        "model": settings.qwen_vision_model,
        "purpose": "vision_review",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
        "estimated_cost_cny": estimated_cost,
        "price_assumption_cny_per_million": {
            "input": settings.qwen_vision_input_price_per_million,
            "output": settings.qwen_vision_output_price_per_million,
        },
        "request_id": response_body.get("id", ""),
        "secret_recorded": False,
        "content_recorded": False,
    }
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return estimated_cost
