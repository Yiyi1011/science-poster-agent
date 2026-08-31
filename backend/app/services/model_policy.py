"""Fail closed: competition calls stay on Qwen through Bailian in Beijing."""
import json
import re
from urllib.parse import urlsplit

from app.config import Settings
from app.services.usage_ledger import _usage_path


def validate_model_policy(settings: Settings):
    for model in (settings.qwen_text_model, settings.qwen_image_model, settings.qwen_tts_model, settings.qwen_vision_model):
        if not re.fullmatch(r"qwen[a-zA-Z0-9._-]*", model):
            raise RuntimeError("赛事模式仅允许已配置的千问系列模型，不会自动切换第三方模型")
    for url in (settings.dashscope_base_url, settings.dashscope_app_base_url):
        if not url:
            continue
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        valid = host == "dashscope.aliyuncs.com" or host.endswith(".cn-beijing.maas.aliyuncs.com")
        if parsed.scheme != "https" or not valid or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None, 443):
            raise RuntimeError("赛事模式只允许百炼北京HTTPS接口")


def guard_text_budget(settings: Settings):
    """Conservative local estimate guard, NOT a replacement for the actual Alibaba bill."""
    path = _usage_path()
    total = 0.0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                # A corrupt ledger must not silently reset spending to zero.
                total += float(json.loads(line).get("estimated_cost_cny") or 0)
    if total + 0.25 >= min(settings.budget_pause_cny, settings.budget_limit_cny, 70):
        raise RuntimeError("本地记录估算已接近暂停线，需核对账单后继续")

