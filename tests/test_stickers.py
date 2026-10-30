import importlib.util
import sys
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


stickers = _load("sticker_rules", "stickers.py")


class AdapterKindTest(unittest.TestCase):
    def test_onebot(self):
        self.assertEqual(stickers.adapter_kind("onebot11"), "onebot")
        self.assertEqual(stickers.adapter_kind("OneBot"), "onebot")

    def test_milky(self):
        self.assertEqual(stickers.adapter_kind("milky"), "milky")

    def test_other(self):
        self.assertIsNone(stickers.adapter_kind("satori"))
        self.assertIsNone(stickers.adapter_kind(None))


class IsStickerAttrsTest(unittest.TestCase):
    def test_onebot_sticker(self):
        self.assertTrue(stickers.is_sticker_attrs({"onebot:subType": "1"}, "qq-client", "onebot11"))

    def test_onebot_normal_image(self):
        self.assertFalse(stickers.is_sticker_attrs({"onebot:subType": "0"}, "qq-client", "onebot11"))
        self.assertFalse(stickers.is_sticker_attrs({}, "qq-client", "onebot11"))

    def test_milky_sticker(self):
        self.assertTrue(stickers.is_sticker_attrs({"milky:subType": "sticker"}, "qq-client", "milky"))
        self.assertFalse(stickers.is_sticker_attrs({"milky:subType": "image"}, "qq-client", "milky"))

    def test_fallback_keys(self):
        self.assertTrue(stickers.is_sticker_attrs({"sub_type": "1"}, "qq-client", "onebot11"))
        self.assertTrue(stickers.is_sticker_attrs({"sub_type": "sticker"}, "qq-client", "milky"))

    def test_wrong_platform(self):
        self.assertFalse(stickers.is_sticker_attrs({"onebot:subType": "1"}, "qq", "onebot11"))


class ImageExtraTest(unittest.TestCase):
    def test_onebot(self):
        self.assertEqual(stickers.image_extra("qq-client", "onebot11"), {"onebot:subType": "1"})

    def test_milky(self):
        self.assertEqual(
            stickers.image_extra("qq-client", "milky"),
            {"sub_type": "sticker", "milky:subType": "sticker"},
        )

    def test_other_platform(self):
        self.assertEqual(stickers.image_extra("qq", "onebot11"), {})


if __name__ == "__main__":
    unittest.main()
