from arclet.entari import BasicConfModel, plugin_config


class StickerConfig(BasicConfModel):
    enabled: bool = True
    """是否启用表情包功能"""

    auto_collect: bool = False
    """是否自动收集群里的表情包（默认关闭，避免每张图都调用视觉模型）"""

    auto_collect_chance: float = 0.2
    """有多少概率触发自动收集任务"""

    max_size_mb: float = 5.0
    """单张表情包允许的最大体积（MB）"""

    max_stickers: int = 500
    """最多保存多少个表情包，达到上限后不再保存新的"""

    tagging: bool = True
    """保存时是否调用视觉模型生成描述和标签"""

    vision_model: str | None = None
    """打标使用的模型别名，不填使用默认模型"""

    select_model: str | None = None
    """多个候选时选择表情包使用的模型别名，不填使用默认模型"""

    catalog_limit: int = 20
    """注入主提示词的表情包候选数量，0 表示只注入发送方式、不列清单"""

    def __post_init__(self) -> None:
        if self.max_size_mb <= 0:
            raise ValueError("max_size_mb must be positive")
        if self.max_stickers < 0:
            raise ValueError("max_stickers must be a non-negative integer")
        if self.catalog_limit < 0:
            raise ValueError("catalog_limit must be a non-negative integer")


_conf = plugin_config(StickerConfig)

__all__ = ["StickerConfig", "_conf"]
