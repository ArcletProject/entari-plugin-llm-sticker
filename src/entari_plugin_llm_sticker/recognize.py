from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from agno.models.message import Message
from entari_plugin_llm import get_model_config, llm, supports_vision
from pydantic import BaseModel, Field

from .log import logger

STICKER_TAG_PROMPT = """你是一个表情包分类助手。请判断用户提供的图片是否适合当作聊天表情包/贴纸使用。

要求：
1. 普通照片、截图、长图、文字图、二维码不属于表情包，is_sticker 设为 false。
2. description 用中文概括画面内容，30 字以内，便于以后检索。
3. emotion 用一个词概括情绪，例如：开心、无语、疑惑、生气、得意、难过、震惊。
4. tags 给 3-6 个中文关键词，覆盖主体、动作、情绪、梗。
5. 只输出结构化结果，不要额外解释。"""


class StickerMeta(BaseModel):
    is_sticker: bool = False
    description: str = ""
    emotion: str = ""
    tags: list[str] = Field(default_factory=list)


async def download_image(src: str, max_bytes: int) -> tuple[bytes, str] | None:
    """下载图片，返回 (bytes, mime)；失败或超限返回 None"""
    if not src:
        return None

    try:
        if src.startswith("data:"):
            header, _, payload = src.partition(",")
            mime = header[5:].split(";")[0].strip().lower() or "image/png"
            data = base64.b64decode(payload)
            return (data, mime) if len(data) <= max_bytes else None

        if src.startswith("file://"):
            path = Path(unquote(urlparse(src).path))
            data = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            return (data, mime) if len(data) <= max_bytes else None

        if not src.startswith(("http://", "https://")):
            return None

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            response = await client.get(src)
            response.raise_for_status()
            mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                return None
            data = response.content
            if len(data) > max_bytes:
                return None
            return data, mime
    except Exception:
        logger.debug(f"下载表情包失败: {src}", exc_info=True)
        return None


async def describe_image(data: bytes, mime: str, model: str | None = None) -> StickerMeta | None:
    """用视觉模型给图片打标；模型不支持视觉或调用失败时返回 None"""
    try:
        model_config = get_model_config(model)
        if not supports_vision(model_config):
            return None

        uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        message = Message(
            role="user",
            content=[
                {"type": "text", "text": "请判断这张图片是否适合作为表情包，并给出描述、情绪和标签。"},
                {"type": "image_url", "image_url": {"url": uri}},
            ],
        )
        response = await llm.generate(
            [message],
            system=STICKER_TAG_PROMPT,
            output=StickerMeta,
            model=model_config.name,
            use_tools=False,
        )
    except Exception:
        logger.debug("表情包打标失败", exc_info=True)
        return None

    if response.stopped or not response.output:
        return None

    output = response.output
    if isinstance(output, StickerMeta):
        return output
    if isinstance(output, dict):
        try:
            return StickerMeta.model_validate(output)
        except (TypeError, ValueError):
            return None
    if hasattr(output, "model_dump"):
        try:
            return StickerMeta.model_validate(output.model_dump())
        except (TypeError, ValueError):
            return None
    return None


__all__ = ["STICKER_TAG_PROMPT", "StickerMeta", "describe_image", "download_image"]
