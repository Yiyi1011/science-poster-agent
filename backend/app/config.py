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
    # Public zero-configuration release. These values are configured once by
    # the operator in the cloud; end users receive an anonymous signed session
    # automatically and never see an API key or setup screen.
    public_access_enabled: bool = _as_bool(os.getenv("PUBLIC_ACCESS_ENABLED"), False)
    public_session_secret: str = os.getenv("PUBLIC_SESSION_SECRET", "")
    public_projects_per_day: int = int(os.getenv("PUBLIC_PROJECTS_PER_DAY", "12"))
    public_runs_per_hour: int = int(os.getenv("PUBLIC_RUNS_PER_HOUR", "6"))
    public_media_per_hour: int = int(os.getenv("PUBLIC_MEDIA_PER_HOUR", "3"))
    public_max_active_jobs: int = int(os.getenv("PUBLIC_MAX_ACTIVE_JOBS", "1"))
    public_max_queued_jobs: int = int(os.getenv("PUBLIC_MAX_QUEUED_JOBS", "4"))

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

    def validate_for_public_release(self) -> None:
        """Fail closed before exposing a real-model build to anonymous users."""
        if self.app_env != "production":
            return
        self.validate_for_real_ai()
        if self.mock_ai:
            raise RuntimeError("PUBLIC production release cannot run with MOCK_AI=true.")
        if not self.public_access_enabled:
            raise RuntimeError("PUBLIC_ACCESS_ENABLED=true is required for the public release.")
        if len(self.public_session_secret) < 32:
            raise RuntimeError("PUBLIC_SESSION_SECRET must contain at least 32 characters.")
        if not self.runtime_data_dir or not Path(self.runtime_data_dir).is_absolute():
            raise RuntimeError("SCIENCE_POSTER_DATA_DIR must be an absolute persistent path in production.")
        if not (1 <= self.public_max_active_jobs <= 4):
            raise RuntimeError("PUBLIC_MAX_ACTIVE_JOBS must be between 1 and 4.")
        if self.public_max_queued_jobs < self.public_max_active_jobs:
            raise RuntimeError("PUBLIC_MAX_QUEUED_JOBS cannot be smaller than active jobs.")
        for value in (self.public_projects_per_day, self.public_runs_per_hour, self.public_media_per_hour):
            if value < 1:
                raise RuntimeError("Public usage limits must be positive integers.")


settings = Settings()
