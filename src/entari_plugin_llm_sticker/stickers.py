from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ONEBOT_KEYS = (
    "onebot:subType",
    "onebot:sub-type",
    "onebot:sub_type",
    "subType",
    "sub-type",
    "sub_type",
)

MILKY_KEYS = (
    "milky:subType",
    "milky:sub-type",
    "milky:sub_type",
    "sub_type",
    "subType",
    "sub-type",
)


def adapter_kind(adapter: str | None) -> str | None:
    """把适配器名归一成 onebot / milky，其他适配器返回 None"""
    if not adapter:
        return None
    value = adapter.lower()
    if "onebot" in value:
        return "onebot"
    if "milky" in value:
        return "milky"
    return None


def is_sticker_attrs(
    attrs: Mapping[str, Any],
    platform: str | None,
    adapter: str | None,
) -> bool:
    """根据 Element._attrs 判断一张图片是不是平台表情包"""
    if platform == "qq-client":
        kind = adapter_kind(adapter)
        if kind == "onebot":
            return any(str(attrs.get(key, "")).strip() == "1" for key in ONEBOT_KEYS)
        if kind == "milky":
            return any(str(attrs.get(key, "")).strip().lower() == "sticker" for key in MILKY_KEYS)
        return False
    return False


def image_extra(
    platform: str | None,
    adapter: str | None,
) -> dict[str, str]:
    """发送图片时需要附加的平台属性"""
    if platform == "qq-client":
        kind = adapter_kind(adapter)
        if kind == "onebot":
            return {"onebot:subType": "1"}
        if kind == "milky":
            # milky 适配器读取 sub_type（源码里还有一个 subTyoe 的 typo 回退）
            return {"sub_type": "sticker", "milky:subType": "sticker"}
    return {}


__all__ = ["adapter_kind", "image_extra", "is_sticker_attrs"]
