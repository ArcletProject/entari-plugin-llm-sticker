from __future__ import annotations

import asyncio
import random

from arclet.alconna import Alconna, Subcommand, Args, CommandMeta
from arclet.entari import (
    Image,
    MessageChain,
    MessageCreatedEvent,
    Session,
    Text,
    Reply,
    command,
    listen,
    plugin,
)
from arclet.entari.filter import admins
from entari_plugin_llm import LLMCollectVariableEvent, LLMResponseEvent

from .config import _conf
from .recognize import describe_image, download_image
from .store import get_store
from .stickers import image_extra, is_sticker_attrs

_tasks: set[asyncio.Task] = set()


def _images(session: Session) -> list[Image]:
    images = list(session.elements.select(Image))

    reply: Reply | None = getattr(session, "reply", None)
    if reply and reply.quote.children:
        images.extend(MessageChain(reply.quote.children).select(Image))

    unique: dict[str, Image] = {}
    for image in images:
        if image.src:
            unique.setdefault(image.src, image)
    return list(unique.values())


async def save_sticker(
    session: Session,
    image: Image,
    *,
    force: bool,
    announce: bool,
) -> str | None:
    if not force and not is_sticker_attrs(
        image._attrs,
        session.account.platform,
        session.account.adapter,
    ):
        return None

    downloaded = await download_image(image.src, int(_conf.max_size_mb * 1024 * 1024))
    if downloaded is None:
        return "图片下载失败，或者超过了大小限制。" if announce else None
    data, mime = downloaded

    meta = await describe_image(data, mime, _conf.vision_model) if _conf.tagging else None
    description = (meta.description if meta else "") or "未识别的表情包"
    tags = tuple(meta.tags) if meta else ()
    emotion = meta.emotion if meta else ""

    user = getattr(session, "user", None)
    created_by = str(user.id) if user is not None else ""
    sticker, created = await get_store().add(
        data,
        mime,
        description=description,
        tags=tags,
        emotion=emotion,
        created_by=created_by,
        adapter=session.account.adapter or "",
    )

    if sticker is None:
        return "表情包存储已达到上限，未保存此表情包。" if announce else None
    if not announce:
        return None
    if not created:
        return f"这个表情已经存过了：{sticker.id}"
    return f"已保存表情包 {sticker.id}：{description}"


cmd = Alconna(
    "表情管理",
    Subcommand("保存", Args["img", Image]),
    Subcommand("列出"),
    Subcommand("删除", Args["sticker", str]),
    meta=CommandMeta("表情包管理")
)
cmd.shortcut("记住这个表情", command="表情管理 保存")
cmd.shortcut("存表情", command="表情管理 保存")
cmd.shortcut("表情列表", command="表情管理 列出")

handle = command.mount(cmd, skip_for_unmatch=False, block=True).as_execute()


@handle.assign("保存")
@admins()
async def remember_sticker(session: Session, img: Image) -> str:
    """把消息里的图片保存为表情包"""
    result = await save_sticker(session, img, force=True, announce=True)
    return result or "没有保存成功。"


@handle.assign("列出")
async def list_stickers() -> str:
    """列出已保存的表情包"""
    items = get_store().get_all()
    if not items:
        return "还没有保存任何表情包。"

    lines = [f"共 {len(items)} 个表情包，最近 {min(len(items), 20)} 个："]
    for item in items[:20]:
        suffix = f"｜{item.emotion}" if item.emotion else ""
        lines.append(f"{item.id}｜{item.description}{suffix}")
    return "\n".join(lines)


@handle.assign("删除")
@admins()
async def remove_sticker(sticker: str) -> str:
    """按 id 删除表情包（保存者或管理员）"""
    store = get_store()
    item = store.get(sticker)
    if item is None:
        return "没有找到这个表情包。"
    store.remove(item.id)
    return f"已删除表情包 {item.id}。"


@listen(MessageCreatedEvent, priority=10)
async def auto_capture(session: Session) -> None:
    if not _conf.enabled or not _conf.auto_collect:
        return
    items = get_store().get_all()
    if len(items) >= _conf.max_stickers:
        return
    imgs = _images(session)
    if not imgs:
        return

    for image in imgs:
        if random.random() < _conf.auto_collect_chance:
            task = asyncio.create_task(save_sticker(session, image, force=False, announce=False))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)


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


__all__ = ["auto_capture", "inject_sticker_instructions", "rewrite_sticker_refs"]
