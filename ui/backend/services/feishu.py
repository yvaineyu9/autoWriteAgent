"""Feishu Open Platform client — tenant_access_token + image upload + post message.

Credentials come from os.environ (loaded in main.py from PROJECT_ROOT/.env):
- FEISHU_APP_ID
- FEISHU_APP_SECRET
- FEISHU_CHAT_ID
"""
from __future__ import annotations

import json
import os
import time

import httpx

_BASE = "https://open.feishu.cn/open-apis"

# Process-wide token cache. httpx client is created per-call (cheap) so this
# module stays stateless apart from the token cache.
_token_cache: dict = {"value": None, "expires_at": 0.0}


class FeishuError(RuntimeError):
    def __init__(self, code: int, msg: str, detail: str = ""):
        self.code = code
        self.msg = msg
        self.detail = detail
        parts = [f"feishu API {code}: {msg}"]
        if detail:
            parts.append(detail)
        super().__init__(" ".join(parts))


def _get_tenant_access_token() -> str:
    now = time.time()
    if _token_cache["value"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["value"]

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise FeishuError(-1, "FEISHU_APP_ID / FEISHU_APP_SECRET not set in environment")

    resp = httpx.post(
        f"{_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10.0,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(data.get("code", -1), data.get("msg", "token request failed"))

    token = data["tenant_access_token"]
    expire = int(data.get("expire", 7200))
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + expire
    return token


def upload_image(path: str) -> str:
    """Upload a single image file to Feishu and return its image_key."""
    token = _get_tenant_access_token()
    with open(path, "rb") as f:
        resp = httpx.post(
            f"{_BASE}/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": f},
            timeout=30.0,
        )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(
            data.get("code", -1),
            data.get("msg", "upload failed"),
            os.path.basename(path),
        )
    return data["data"]["image_key"]


def send_post_message(chat_id: str, image_keys: list) -> str:
    """Send a Feishu `post` message whose body is nothing but image_keys, one per line.

    Returns message_id.
    """
    if not image_keys:
        raise FeishuError(-1, "no image_keys to send")

    token = _get_tenant_access_token()

    # Feishu post format: content is a list of paragraphs, each paragraph is a
    # list of inline elements. For image-only messages, each paragraph is just
    # one {tag:"img", image_key:...}.
    post_content = {
        "zh_cn": {
            "title": "",
            "content": [
                [{"tag": "img", "image_key": key}]
                for key in image_keys
            ],
        }
    }

    resp = httpx.post(
        f"{_BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "receive_id": chat_id,
            "msg_type": "post",
            # Feishu requires `content` to be a JSON-encoded string, not a nested object.
            "content": json.dumps(post_content, ensure_ascii=False),
        },
        timeout=15.0,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(data.get("code", -1), data.get("msg", "send failed"))
    return data["data"]["message_id"]
