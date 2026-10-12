import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


@dataclass
class Config:
    """Configuration for the LLM API and application."""

    # OpenAI-compatible API settings
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o"))

    # Agent settings
    max_steps: int = 15
    code_timeout: int = 30  # seconds

    # Server settings
    upload_dir: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(__file__), "uploads")
    )
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:3001", "http://127.0.0.1:3001"]
    )


config = Config()
