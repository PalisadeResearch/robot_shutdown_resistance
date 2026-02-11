from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings

from ..utils import yayamlml

ROOT_DIR = Path(__file__).parent.parent.parent.parent

CONFIG_DIR = ROOT_DIR / "config"


class AgentSettings(BaseModel):
    AGENT_MODEL: str
    MAX_STEPS: int = 300

    # TODO: add more settings and per-state prompts as needed


class Settings(BaseSettings):
    def __init__(self, config_name: str = "baseline", **data) -> None:
        """Load from env vars, then optionally merge YAML preset."""
        config_file = CONFIG_DIR / f"{config_name}.yaml"
        if not config_file.is_file():
            available = [
                p.stem for p in CONFIG_DIR.glob("*.yaml") if not p.stem.startswith("_")
            ]
            raise FileNotFoundError(
                f"Configuration '{config_name}' not found in {CONFIG_DIR}. Available: {available}"
            )
        super_data = data.copy()
        yayamlml.safe_load(
            config_file,
            base=super_data,
            include_paths=[CONFIG_DIR],
        )
        super().__init__(**super_data)

    agent: AgentSettings
    # TODO: add more sections here

    class Config:
        extra = "ignore"
        arbitrary_types_allowed = True
