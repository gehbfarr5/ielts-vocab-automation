# Shortcut 与收件接口

## 主入口：雅思截屏 控制中心

2026-09-16按用户现有“截屏 控制中心”复制为独立入口，原快捷指令保持原样。新入口已通过Mac原生编辑器保存，移动运行待验收。

1. 切换控制中心：沿用原ShowControlCenterAction的operation=toggle。从已展开的控制中心点击，意图是关闭控制中心；不要在快捷指令App内直接运行来验收这个动作。
2. 等待1秒：原动作参数为空，原生编辑器显示默认1秒，完整保留。
3. 全屏幕截图。
4. 截图存入最近项目。
5. 已存照片媒体复制到剪贴板兜底。
6. 同一已存照片媒体自动保存到Shortcuts/IELTSInbox/；不询问位置、不覆盖同名文件。没有分享菜单。

在iPad/iPhone控制中心添加“快捷指令”控件，选择“雅思截屏 控制中心”。回到Goodnotes后下拉控制中心并点击。首次照片/文件权限提示需要用户在设备上处理。此控件为运行按钮，不是持续开关。

Apple官方设置说明：https://support.apple.com/en-nz/guide/shortcuts/apd06a9201d4/ios

Mac不支持第一步，不能用Mac运行宣称控制中心时序通过。验收需检查截图没有控制中心覆盖、保存无菜单、原图/剪贴板可用、新文件到达Mac、重复运行不覆盖，且自动worker真实触发。Mac睡眠及iCloud延迟可能推迟处理；保存并不等于Anki已入卡。

旧“雅思截图提交”共享入口保留备用。2026-09-16首次真实截图已到达固定目录并完成手动触发的本地OCR与独立Anki创建/读回/删除测试，定时器触发和移动Anki同步尚未验收。

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
