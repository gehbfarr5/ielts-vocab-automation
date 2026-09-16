# 逐词高亮定位：本地改进与边界

2026-09-16。问题：原实现仅统计OCR整行颜色，无法识别具体目标，还将蓝色App界面计入诊断。当前Python3.12 / Apple Vision accurate，本地截图，不启用云图像或正式Anki写入。

比较两种路线：本地Vision逐词框+颜色重叠，复用现有组件、成本小但需校准；云端视觉可辅助复杂页面，需要明确图像传输范围和独立评估。选择前者。先原生词框，再背景与覆盖率判断，再连续同色词组，最后真实样本回归。回滚为Git还原相关实现并重建OCR；不改学习数据。

## 实现

Vision boundingBox(for:)提供每个非空白token的位置；缺少位置显式失败，不能用整行框假装逐词位置。Python保留整行诊断，新增marked_spans作为候选边界。背景亮度/饱和度过滤排除深色界面；当前仅支持浅底阅读页。行中亮背景像素比例至少0.70、OCR置信度至少0.8；词色覆盖率至少0.30、主色占比至少0.80。相邻同色词组合为片段，未标记词或异色打断组合。阈值为保守启发式，不能当作已校准概率。

正文不靠固定顶部裁剪：避免横竖屏固定坐标带来的误删。但此过滤不是通用正文检测，浅色工具栏、插图、深色页面、跨行搭配及边缘浅划仍待处理。相邻词也可能因人工涂抹边界而歧义；后续独立样本才能验收。

对本次私人样本：三个正文片段分别命中三色，顶部界面没有进入marked_spans。样本用于开发，不能计作独立准确率评估。原图/OCR不进入公开仓库。完整本地process入口也需单独核验；calibration_verified仍false，不能因此自动入卡。

## 复用证据

仅围绕现有Vision API窄范围检索，未使用子代理。查询GitHub代码boundingBox(for:)与macOS OCR Vision仓库，再核验Apple文档。复用Apple公开接口与已有OCR流程，自行实现本项目颜色规则；不复制第三方代码或引入新库。

- Apple API：https://developer.apple.com/documentation/vision/vnrecognizedtext/boundingbox(for:)
- Ente：28914 Stars / 1802 forks，AGPL-3.0，2026-09-16仍有更新；其照片文字识别用同一API取得字符位置，适合作接口证据，避免复制其AGPL实现。https://github.com/ente/ente/blob/958e8db1c4a98f2f4bfc96bd85323fd31f2f1883/mobile/apps/photos/plugins/ente_vision/ios/Sources/EnteVisionCore/TextRecognizer.swift
- OpenFind：1073 Stars / 71 forks，MIT，最后推送2023-02-10；同一API用例，较旧，仅作旁证，不引入整套视觉搜索App。https://github.com/aheze/OpenFind/blob/db1eede9cf4d9fa54d1e01972ea9388faf2842e6/Sources/MLVision/Find+Sentences.swift

## 验证

50项自动测试通过；新增覆盖邻词擦边、深蓝工具栏排除、未标记间隔/异色分组，以及旧OCR程序缺词框时明确报错。Swift编译和Python包构建通过。下一步用不同缩放、横竖屏、不同标记宽度的新截图独立验证。后续只有校准通过才能开放自动选词，云与正式写入门槛不变。

## Agent语义边界裁决
用户进一步确认高亮可能误连邻词。marked_spans改作候选范围，不是最终卡片边界：Agent结合原句及词典证据删除擦边邻词、还原词形，并恢复同一构式必需的邻接成分。不得借此挖掘无关未标记词。优先有迁移价值的实词和固定搭配；不伪造雅思官方频率。还原不确定则DEFER，并记录删减/补入理由。识别器仍负责颜色/位置证据，不能自行猜测用户心理。
