#!/usr/bin/env python3
"""
读取 persona / platform 的结构化配置。
"""

import json
import os

from db import PROJECT_ROOT


def get_platform_config_path(persona: str, platform: str) -> str:
    return os.path.join(
        PROJECT_ROOT,
        "personas",
        persona,
        "platforms",
        f"{platform}.config.json",
    )


def load_platform_config(persona: str, platform: str) -> dict:
    path = get_platform_config_path(persona, platform)
    if not os.path.isfile(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
