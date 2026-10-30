import asyncio
import hashlib
import json
import mimetypes
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from arclet.entari import keeping
from arclet.entari.localdata import local_data

from .config import _conf
from .log import logger


_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


@dataclass(frozen=True, slots=True)
class Sticker:
    id: str
    hash: str
    file: str
    mime: str
    description: str
    tags: tuple[str, ...] = ()
    emotion: str = ""
    created_at: float = 0.0
    created_by: str = ""
    adapter: str = ""


class StickerStore:
    """基于 index.json 的简单表情包仓库，不依赖 Entari，便于单测"""

    def __init__(self, root: str | Path, max_stickers: int = 500) -> None:
        self.root = Path(root)
        self.max_stickers = max_stickers
        self._dir = self.root / "stickers"
        self._index = self.root / "index.json"
        self._items: dict[str, Sticker] | None = None
        self._lock = asyncio.Lock()

    def _ensure_loaded(self) -> None:
        if self._items is not None:
            return

        items: dict[str, Sticker] = {}
        try:
            payload = json.loads(self._index.read_text("utf-8"))
        except (OSError, ValueError):
            payload = {}

        for key, raw in (payload.get("items") or {}).items():
            if not isinstance(raw, dict):
                continue
            try:
                items[key] = Sticker(
                    id=raw["id"],
                    hash=raw.get("hash", ""),
                    file=raw["file"],
                    mime=raw.get("mime", "image/png"),
                    description=raw.get("description", ""),
                    tags=tuple(raw.get("tags") or ()),
                    emotion=raw.get("emotion", ""),
                    created_at=float(raw.get("created_at") or 0),
                    created_by=raw.get("created_by", ""),
                    adapter=raw.get("adapter", ""),
                )
            except (KeyError, TypeError, ValueError):
                continue

        self._items = items

    def _save(self) -> None:
        if self._items is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": {key: asdict(item) for key, item in self._items.items()},
        }
        tmp = self._index.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self._index)

    async def add(
        self,
        data: bytes,
        mime: str,
        *,
        description: str,
        tags: tuple[str, ...] = (),
        emotion: str = "",
        created_by: str = "",
        adapter: str = "",
    ) -> tuple[Sticker | None, bool]:
        """保存一张表情包，返回 (记录, 是否新建)，容量已满时记录为 None。"""
        digest = hashlib.sha256(data).hexdigest()

        async with self._lock:
            self._ensure_loaded()
            assert self._items is not None

            for item in self._items.values():
                if item.hash == digest:
                    return item, False

            if self.max_stickers > 0 and len(self._items) >= self.max_stickers:
                logger.info("表情包存储已达上限，取消保存新表情包")
                return None, False

            ext = _EXTENSIONS.get(mime.lower()) or mimetypes.guess_extension(mime) or ".bin"
            relative = f"stickers/{digest}{ext}"
            self._dir.mkdir(parents=True, exist_ok=True)
            target = self.root / relative
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)

            sticker = Sticker(
                id=digest[:12],
                hash=digest,
                file=relative,
                mime=mime,
                description=description.strip(),
                tags=tuple(tags),
                emotion=emotion.strip(),
                created_at=time.time(),
                created_by=created_by,
                adapter=adapter,
            )
            logger.info(f"保存表情包 {sticker.id}：{sticker.description}")
            self._items[sticker.id] = sticker
            self._save()
            return sticker, True

    def get_all(self) -> list[Sticker]:
        self._ensure_loaded()
        assert self._items is not None
        return sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, key: str) -> Sticker | None:
        self._ensure_loaded()
        assert self._items is not None
        value = key.strip()
        if not value:
            return None
        if value in self._items:
            return self._items[value]
        matches = [item for item in self._items.values() if item.id.startswith(value)]
        if not matches:
            return None
        return max(matches, key=lambda item: item.created_at)

    def search(self, query: str, limit: int = 10) -> list["Sticker"]:
        self._ensure_loaded()
        assert self._items is not None

        value = query.strip().lower()
        if not value:
            return self.get_all()[:limit]

        tokens = [token for token in value.split() if token]
        scored: list[tuple[int, Sticker]] = []
        for item in self._items.values():
            haystack = f"{item.description} {item.emotion} {' '.join(item.tags)}".lower()
            score = sum(2 for token in tokens if token in haystack)
            if value in item.description.lower():
                score += 3
            if item.id.startswith(value):
                score += 10
            if score:
                scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], -pair[1].created_at))
        return [item for _, item in scored[:limit]]

    def read(self, sticker: Sticker) -> bytes:
        return (self.root / sticker.file).read_bytes()

    def remove(self, key: str) -> bool:
        self._ensure_loaded()
        assert self._items is not None
        item = self.get(key)
        if item is None:
            return False
        self._items.pop(item.id, None)
        (self.root / item.file).unlink(missing_ok=True)
        self._save()
        return True


_store = keeping(
    "sticker_store",
    obj_factory=lambda: StickerStore(local_data.get_data_dir("entari_plugin_llm_sticker"), max_stickers=_conf.max_stickers),
    dispose=lambda o: o._save()
)


def get_store():
    return _store


__all__ = ["get_store", "Sticker", "StickerStore"]
