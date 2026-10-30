from __future__ import annotations

import json

from arclet.entari import Image, MessageChain, Session, plugin
from arclet.letoderea import STOP
from entari_plugin_llm import LLMCollectVariableEvent, LLMResponseEvent, llm, register_tool
from pydantic import BaseModel
from satori import Text

from .config import _conf
from .log import logger
from .store import get_store
from .stickers import image_extra


STICKER_SELECT_PROMPT = """你是一个表情包选择助手。根据用户想表达的意思，从候选表情包里挑一个最合适的。

只输出结构化结果：
- id：选中的表情包 id；都不合适时填 null
- reason：一句话说明为什么选它

优先匹配情绪和画面含义，不要只看字面关键词。"""


class StickerChoice(BaseModel):
    id: str | None = None
    reason: str = ""


@register_tool
async def send_sticker(session: Session, query: str):
    """发送一个表情包。query 可以是表情包 id，也可以是画面或情绪描述。

    Args:
        session (Session): 会话对象
        query (str): 可以是表情包 id，也可以是画面或情绪描述。
    """
    if not _conf.enabled:
        return STOP

    store = get_store()
    item = store.get(query)
    if item is None:
        candidates = store.search(query, 12)
        if not candidates:
            return "没有找到合适的表情包。"
        item = candidates[0]
        if len(candidates) > 1:
            item = await _choose(query, candidates) or item

    try:
        data = store.read(item)
    except OSError:
        logger.warning(f"表情包文件丢失: {item.file!s}")
        return STOP

    extra = image_extra(session.account.platform, session.account.adapter)
    image = Image.of(raw=data, mime=item.mime, name=item.id, extra=extra or None)
    await session.send(MessageChain([image]))
    return f"已发送表情包：{item.description}"


async def _choose(query: str, candidates):
    listing = "\n".join(
        f"- {item.id}｜{item.description}｜{item.emotion}｜{'、'.join(item.tags)}" for item in candidates
    )
    prompt = f"用户想表达：{query}\n候选表情包：\n{listing}"
    try:
        response = await llm.generate(
            prompt,
            system=STICKER_SELECT_PROMPT,
            output=StickerChoice,
            model=_conf.select_model,
            use_tools=False,
        )
    except Exception:
        logger.debug("表情包选择失败", exc_info=True)
        return None

    if response.stopped or not response.output:
        return None

    output = response.output
    if isinstance(output, dict):
        try:
            output = StickerChoice.model_validate(output)
        except (TypeError, ValueError):
            return None
    if isinstance(output, StickerChoice) and output.id:
        return next((item for item in candidates if item.id == output.id), None)
    if isinstance(output, str):
        try:
            payload = json.loads(output)
        except ValueError:
            return None
        target = payload.get("id") if isinstance(payload, dict) else None
        if target:
            return next((item for item in candidates if item.id == target), None)
    return None


collect = plugin.dispatch(LLMCollectVariableEvent)


@collect.on()
async def inject_sticker_instructions(event: LLMCollectVariableEvent) -> None:
    if not _conf.enabled:
        return

    items = get_store().get_all()
    if not items:
        return

    lines = [
        "你可以发送表情包来回复。",
        "方式一：调用 send_sticker(query) 工具，query 是表情包 id，或画面/情绪描述。",
        '方式二：在回复文本里直接写 <img src="sticker://表情包ID"/>，系统会自动替换成真实表情。',
    ]
    shown = items[:_conf.catalog_limit] if _conf.catalog_limit > 0 else []
    if shown:
        lines.append("可用表情包（id｜描述｜情绪）：")
        lines.extend(f"- {item.id}｜{item.description}｜{item.emotion}".rstrip("｜") for item in shown)
    event.instructions.append("\n".join(lines))


response = plugin.dispatch(LLMResponseEvent)


@response.on()
async def rewrite_sticker_refs(event: LLMResponseEvent) -> MessageChain | None:
    if not _conf.enabled:
        return None

    store = get_store()
    chain = MessageChain()
    changed = False
    for element in event.message:
        if isinstance(element, Image) and isinstance(element.src, str) and element.src.startswith("sticker://"):
            changed = True
            item = store.get(element.src[len("sticker://") :].strip().strip("/"))
            if item is None:
                chain.append(Text("[表情包不存在]"))
                continue
            extra = image_extra(
                event.session.account.platform,
                event.session.account.adapter,
            )
            chain.append(Image.of(raw=store.read(item), mime=item.mime, name=item.id, extra=extra or None))
        else:
            chain.append(element)

    return chain if changed else None


__all__ = ["STICKER_SELECT_PROMPT", "StickerChoice", "send_sticker"]
