from arclet.entari import metadata
from arclet.entari.plugin import PluginRole

from .config import StickerConfig

metadata(
    name="表情包管理",
    role=PluginRole.NORMAL,
    author=[{"name": "RF-Tar-Railt", "email": "rf_tar_railt@qq.com"}],
    version="0.1.0",
    description="收集、识别并按平台发送表情包，配合 entari-plugin-llm 使用。",
    config=StickerConfig,
)

from . import capture as capture
from . import tools as tools
