import asyncio
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "entari_plugin_llm_sticker"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SRC / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


store_module = _load("sticker_store", "store.py")
StickerStore = store_module.StickerStore


class StickerStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = StickerStore(self.root, max_stickers=10)

    def tearDown(self):
        self._tmp.cleanup()

    def _add(self, store, data: bytes, description: str, **kwargs):
        return asyncio.run(
            store.add(
                data,
                "image/png",
                description=description,
                **kwargs,
            )
        )

    def test_add_and_read(self):
        sticker, created = self._add(self.store, b"one", "开心", tags=("猫", "笑"), emotion="开心")

        self.assertTrue(created)
        self.assertEqual(sticker.description, "开心")
        self.assertEqual(self.store.read(sticker), b"one")
        self.assertEqual(self.store.get(sticker.id), sticker)
        self.assertEqual(self.store.get(sticker.id[:6]), sticker)

    def test_dedupe(self):
        first, _ = self._add(self.store, b"same", "第一次")
        second, created = self._add(self.store, b"same", "第二次")

        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.store.get_all()), 1)

    def test_search(self):
        happy, _ = self._add(self.store, b"a", "橘猫大笑", tags=("猫", "开心"), emotion="开心")
        sad, _ = self._add(self.store, b"b", "柴犬流泪", tags=("狗", "难过"), emotion="难过")

        self.assertEqual(self.store.search("橘猫")[0].id, happy.id)
        self.assertEqual(self.store.search("难过")[0].id, sad.id)
        self.assertEqual(self.store.search(happy.id)[0].id, happy.id)
        self.assertEqual(self.store.search("不存在"), [])

    def test_remove(self):
        sticker, _ = self._add(self.store, b"gone", "待删除")
        path = self.root / sticker.file
        self.assertTrue(path.exists())

        self.assertTrue(self.store.remove(sticker.id))
        self.assertFalse(path.exists())
        self.assertIsNone(self.store.get(sticker.id))
        self.assertFalse(self.store.remove(sticker.id))

    def test_persistence(self):
        sticker, _ = self._add(self.store, b"persist", "持久化", emotion="无语")

        loaded = StickerStore(self.root, max_stickers=10)
        item = loaded.get(sticker.id)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.description, "持久化")
        self.assertEqual(item.emotion, "无语")

    def test_rejects_new_sticker_at_capacity(self):
        store = StickerStore(self.root, max_stickers=2)
        first, _ = self._add(store, b"1", "一")
        second, _ = self._add(store, b"2", "二")
        rejected, created = self._add(store, b"3", "三")

        self.assertIsNone(rejected)
        self.assertFalse(created)
        self.assertEqual(store.get(first.id), first)
        self.assertEqual(store.get(second.id), second)
        self.assertEqual(len(store.get_all()), 2)
        self.assertTrue((self.root / first.file).exists())


if __name__ == "__main__":
    unittest.main()
