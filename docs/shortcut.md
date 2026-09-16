# Shortcut 与收件接口

## 文件交付：首个可配置入口

在 iPhone/iPad/Mac 快捷指令创建“雅思截图提交”：

1. 在共享表单显示，接收图像。
2. 输入为“快捷指令输入”。截图原有流程可继续先存照片、复制到剪贴板再分享。
3. 保存文件到 iCloud 的 Shortcuts 文件夹，子路径 `IELTSInbox/`。
4. 关闭“询问保存位置”，关闭“如果文件存在则覆盖”。保留系统自动处理重名能力；正式验收还需测试同名截图不覆盖。
5. 可增加“已保存到待处理目录”通知，不写“已加入 Anki”。

Mac 本地对应目录通常是 `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/IELTSInbox`，需核验实际路径后写入本地 config.json 的 inbox。CLI `shortcuts run NAME --input-path /absolute/screenshot.png` 可用于 Mac 合成样本测试，但不能替代 iPad Share Sheet 验收。

本轮通过原生编辑器创建了“雅思截图提交（待验收）”入口草稿，但首次命令行运行未完成，尚不能称为交付成功的移动入口；没有导出或发布用户现有快捷指令。后续必须验证文件实际到达、同名保存、多图与 iCloud 同步，再给入口 PASS。

## HTTP：自建接口 v1

为简化 Apple 快捷指令，首版每次提交一张原始图片，不采用方案草稿中的 multipart。批量使用逐图重复，相同 ID 重试。

- `POST /v1/submissions`
- `Authorization: Bearer <intake-token>`
- `Content-Type: image/png`、`image/jpeg` 或 `image/webp`
- `Idempotency-Key: <UUID>`
- Body：图片原始字节，最多20MiB/25MP。
- 202：持久化收件 ID、状态和是否重复。不同载荷复用 ID 被拒绝。
- `GET /v1/submissions/<returned-id>` 返回状态；`GET /v1/status` 返回计数。
- 未认证401、超长413、不支持媒体类型415。

接收端只在 Mac loopback 8766 监听，AnkiConnect 在 loopback 8765。两者凭据不同。外部 HTTPS/私有网络反向代理没有在本版本部署；不能直接把控制端口公开。

## 文件包

支持目录内 `manifest.json + 图片 + ready.json`：

```json
{"submission_id":"example-batch","images":[{"file":"image-01.png","sha256":"<actual-sha256>"}]}
```

先校验整个包再收件，忽略符号链接和路径穿越，校验文件真实完整性。普通图不需要 manifest。iCloud 可以乱序送达，ready 出现不等于图片已经下载。
