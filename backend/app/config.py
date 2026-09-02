from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load a small .env file without adding a runtime dependency.

    SCIVIS_ENV_FILE points to the file in packaged desktop/docker layouts;
    otherwise the repository root .env is used. Values already present in the
    environment (e.g. set by the desktop launcher) are never overridden.
    """
    configured = os.getenv("SCIVIS_ENV_FILE", "").strip()
    env_path = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    mock_ai: bool = _as_bool(os.getenv("MOCK_AI"), True)
    allowed_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if item.strip()
    )
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_base_url: str = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ).rstrip("/")
    region: str = os.getenv("ALIBABA_REGION", "cn-beijing")
    workspace_id: str = os.getenv("BAILIAN_WORKSPACE_ID", "")
    app_id: str = os.getenv("BAILIAN_APP_ID", "")
    dashscope_app_base_url: str = os.getenv(
        "DASHSCOPE_APP_BASE_URL",
        "",
    ).rstrip("/")
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.50"))
    qwen_text_model: str = os.getenv("QWEN_TEXT_MODEL", "qwen-plus")
    qwen_studio_model: str = os.getenv("QWEN_STUDIO_MODEL", "qwen3-max")
    # Conservative upper-tier estimates; not a substitute for the provider bill.
    qwen_studio_input_price: float = float(os.getenv("QWEN_STUDIO_INPUT_PRICE", "7"))
    qwen_studio_output_price: float = float(os.getenv("QWEN_STUDIO_OUTPUT_PRICE", "28"))
    qwen_image_model: str = os.getenv("QWEN_IMAGE_MODEL") or "qwen-image-3.0"
    qwen_image_output_price: float = float(
        os.getenv("QWEN_IMAGE_OUTPUT_PRICE", "0.18")
    )
    image_generation_budget_cny: float = float(
        os.getenv("IMAGE_GENERATION_BUDGET_CNY", "10")
    )
    qwen_tts_model: str = os.getenv("QWEN_TTS_MODEL") or "qwen-audio-3.0-tts-flash"
    qwen_tts_voice: str = os.getenv("QWEN_TTS_VOICE") or "longanhuan_v3.6"
    qwen_tts_price_per_10k_chars: float = float(
        os.getenv("QWEN_TTS_PRICE_PER_10K_CHARS", "1")
    )
    tts_budget_cny: float = float(os.getenv("TTS_BUDGET_CNY", "2"))
    qwen_vision_model: str = os.getenv("QWEN_VISION_MODEL") or "qwen3-vl-flash"
    qwen_vision_input_price_per_million: float = float(
        os.getenv("QWEN_VISION_INPUT_PRICE_PER_MILLION", "0.15")
    )
    qwen_vision_output_price_per_million: float = float(
        os.getenv("QWEN_VISION_OUTPUT_PRICE_PER_MILLION", "1.5")
    )
    qwen_input_price_per_million: float = float(
        os.getenv("QWEN_INPUT_PRICE_PER_MILLION", "0.8")
    )
    qwen_output_price_per_million: float = float(
        os.getenv("QWEN_OUTPUT_PRICE_PER_MILLION", "2.0")
    )
    budget_limit_cny: float = float(os.getenv("BUDGET_LIMIT_CNY", "100"))
    budget_pause_cny: float = float(os.getenv("BUDGET_PAUSE_CNY", "70"))
    runtime_data_dir: str = os.getenv("SCIENCE_POSTER_DATA_DIR", "")

    def validate_for_real_ai(self) -> None:
        from app.services.model_policy import validate_model_policy
        validate_model_policy(self)
        if self.region != "cn-beijing":
            raise RuntimeError("The competition build expects Bailian AI resources in cn-beijing.")
        if not self.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is missing. Keep MOCK_AI=true until configured.")

    def validate_for_knowledge_app(self) -> None:
        self.validate_for_real_ai()
        if not self.app_id:
            raise RuntimeError("BAILIAN_APP_ID is missing.")

    def validate_for_image_generation(self) -> None:
        self.validate_for_real_ai()
        if not self.qwen_image_model:
            raise RuntimeError("QWEN_IMAGE_MODEL is missing.")

    def validate_for_tts(self) -> None:
        self.validate_for_real_ai()
        if not self.qwen_tts_model or not self.qwen_tts_voice:
            raise RuntimeError("QWEN_TTS_MODEL or QWEN_TTS_VOICE is missing.")

    def validate_for_vision_review(self) -> None:
        self.validate_for_real_ai()
        if not self.qwen_vision_model:
            raise RuntimeError("QWEN_VISION_MODEL is missing.")


settings = Settings()
