# entari-plugin-llm-sticker

配合 `entari-plugin-llm` 使用的表情包收集、识别与发送插件。

目前只处理 `platform == "qq-client"` 的消息，并根据 `adapter` 区分平台表情包：

| adapter | 识别字段                     | 发送属性                                        |
|---------|------------------------------|-------------------------------------------------|
| onebot  | `onebot:subType == "1"`      | `onebot:subType="1"`                            |
| milky   | `milky:subType == "sticker"` | `sub_type="sticker"`、`milky:subType="sticker"` |

## 配置

```yaml
plugins:
  entari_plugin_llm_sticker:
    enabled: true
    platform: qq-client
    auto_collect: false      # 默认只手动保存，避免每张图都打标
    auto_collect_chance: 0.1 # 自动收集的概率
    max_size_mb: 5
    max_stickers: 500        # 达到上限后不再保存新的表情包
    tagging: true            # 保存时用视觉模型生成描述/情绪/标签
    vision_model: null       # 打标模型别名
    select_model: null       # 多候选时选择模型别名
    catalog_limit: 20        # 注入主提示词的候选数量，0 只注入发送方式
    admins: []               # 可删除任意表情包的用户 id
```

## 命令

- `记住这个表情` / `存表情`：回复一张表情包，或直接带图发送。
- `表情列表`：列出最近 20 个表情包。
- `删除表情 <id>`：保存者或 `admins` 可删。

## 模型侧

插件会通过 `LLMCollectVariableEvent.instructions` 注入：

- 可以调用 `send_sticker(query)` 工具，`query` 是 id 或描述；
- 也可以直接在回复里写 `<img src="sticker://ID"/>`，发送前会自动替换成真实图片。

`send_sticker` 在多个候选时会用单独的提示词让模型挑一个；打标和选择都通过 `use_tools=False` 调用，不会递归触发主聊天工具。

## 数据

表情包文件与索引存放在 `.entari/data/entari_plugin_llm_sticker/`：

```
stickers/<sha256>.<ext>
index.json
```
