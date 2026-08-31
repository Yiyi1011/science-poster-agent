from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime
from pathlib import Path

import httpx

from app.config import Settings
from app.models import PosterRequest
from app.services.usage_ledger import record_text_usage


SYSTEM_PROMPT = """你是科学传播证据整理员与海报叙事规划师。
必须遵守：
1. 只根据用户提供的权威资料形成科学事实，不得用常识补写证据；
2. 资料为空或不足时，将status设为needs_sources，事实卡标为missing；
3. 区分事实、假设、比喻和艺术化表达；
4. 海报面向普通公众，优先单一视觉主线和清晰信息层级；
5. 返回严格JSON，不要使用Markdown代码围栏。
输出字段必须包含：status,title,subtitle,audience,aspect_ratio,fact_cards,sections,
visual_direction,missing_information,safety_note。fact_cards中的每项包含claim_id、claim、
evidence_status、evidence、caveat；sections中的每项包含heading、purpose、visual_form、
content_summary。
JSON类型约束：evidence、fact_cards、sections、missing_information必须始终为数组；没有证据时
evidence必须输出[]，不得输出空字符串、null或对象。"""


class QwenClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def studio_json(self, prompt: str, data: dict, purpose: str) -> tuple[dict, dict]:
        from app.services.model_policy import guard_text_budget
        self.settings.validate_for_real_ai()
        guard_text_budget(self.settings, reserve_cny=1.0)
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            response = await client.post(
                f"{self.settings.dashscope_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.dashscope_api_key}"},
                json={"model": self.settings.qwen_text_model,
                      "messages": [{"role": "system", "content": prompt},
                                   {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
                      "response_format": {"type": "json_object"}, "temperature": 0.2,
                      "enable_thinking": False, "max_tokens": 7500},
            )
            response.raise_for_status()
        body = response.json()
        record_text_usage(self.settings, body, purpose=purpose)
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("模型输出被截断，未保存不完整作品")
        return json.loads(choice["message"]["content"]), {
            "provider": "阿里云百炼", "model": self.settings.qwen_text_model,
            "response_model": body.get("model", ""), "region": self.settings.region,
            "request_id": body.get("id", ""), "purpose": purpose,
            "prompt_version": "studio-v1.2-public", "prompt_sha256": sha256(prompt.encode()).hexdigest(), "usage": body.get("usage", {}),
        }

    async def create_poster_plan(self, request: PosterRequest) -> dict:
        self.settings.validate_for_real_ai()
        payload = {
            "model": self.settings.qwen_text_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(request.model_dump(), ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.dashscope_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        response_body = response.json()
        record_text_usage(self.settings, response_body, purpose="poster_plan")
        content = response_body["choices"][0]["message"]["content"]
        raw_path = (
            Path(__file__).resolve().parents[3]
            / "artifacts"
            / "raw"
            / f"qwen-poster-plan-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(content, encoding="utf-8")
        return json.loads(content)
