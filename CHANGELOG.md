# Changelog

## 0.7.7-ios16.7+1 · 2026-11-24

### 变更

- `Info.plist` 的 `MinimumOSVersion`：`17.0` → `16.7`
  - `Payload/ZLink.app/Info.plist`
  - `Payload/ZLink.app/PlugIns/ZLinkBroadcast.appex/Info.plist`
  - `Payload/ZLink.app/PlugIns/ZLinkWidgets.appex/Info.plist`
- Mach-O `LC_BUILD_VERSION.minos`：`17.0.0` → `16.7.0`
  - `Payload/ZLink.app/ZLink` @ `0xED4`
  - `Payload/ZLink.app/PlugIns/ZLinkBroadcast.appex/ZLinkBroadcast` @ `0xC04`
  - `Payload/ZLink.app/PlugIns/ZLinkWidgets.appex/ZLinkWidgets` @ `0xBB4`
- 重新打包，保留三个可执行文件的 `0755` 权限位

### 校验

| | SHA-256 |
| --- | --- |
| 原始包 | `d3698311a5bcd751b14bcd2fda9eb3848dbc2dd9a8408bea605abaf8f2dd5f8c` |
| 补丁包 | `bb53bf5a187c27a6df3104fe97f877ba18ef04ced879e13103a1331ca142fd72` |

### 已知限制

- 主 App 强引用 4 组 iOS 17.0 SwiftUI API（`containerRelativeFrame`、`scrollTargetBehavior`、`scrollPosition`、`ContentTransition.symbolEffect`），在 iOS 16.7.2 上启动会被 dyld 拒绝（chained fixups 启动即绑定）。
- Widget 扩展强引用 iOS 17.0 的 `containerBackground`，桌面添加小组件时会崩溃。
- 上述两项只能通过源码替换 API 后重编解决，见 `docs/compatibility-report.md`。
