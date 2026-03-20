from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    vault_path: Path
    host: str = "127.0.0.1"
    port: int = 8765


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    vault_path = Path(os.getenv("VAULT_PATH", "~/Desktop/vault")).expanduser()
    return Settings(project_root=project_root, vault_path=vault_path)
