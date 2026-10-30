from __future__ import annotations

import asyncio
import random

from arclet.alconna import Alconna, Subcommand, Args, CommandMeta
from arclet.entari import (
    Image,
    MessageChain,
    MessageCreatedEvent,
    Session,
    Reply,
    command,
    listen,
    metadata,
)
from arclet.entari.filter import admins

from .config import _conf
from .recognize import describe_image, download_image
from .store import get_store
from .stickers import is_sticker_attrs


metadata(
    name="表情包管理",
    author=[
        {"name": "RF-Tar-Railt", "email": "rf_tar_railt@qq.com"},
    ],
    version="0.1.0",
    description="表情包插件中用来管理表情包的命令模块",
)


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


@listen(MessageCreatedEvent, priority=10, label="自动收集表情包")
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

__all__ = ["auto_capture"]
