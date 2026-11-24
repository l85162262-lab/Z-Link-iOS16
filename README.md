# Z-Link iOS 16.7.2 兼容改造

把 **Z-Link 0.7.7**（`com.liruixin.zlink`，原包最低要求 iOS 17.0）改造成面向 **iOS 16.7.2** 的构建。

| 项目 | 值 |
| --- | --- |
| 原始包 | `Z-Link-0.7.7-unsigned.ipa` · 30.18 MB · SHA-256 `d3698311a5bcd751b14bcd2fda9eb3848dbc2dd9a8408bea605abaf8f2dd5f8c` |
| 补丁包 | `Z-Link-0.7.7-iOS16.7.ipa`（Releases 附件） · 31.64 MB · SHA-256 `bb53bf5a187c27a6df3104fe97f877ba18ef04ced879e13103a1331ca142fd72` |
| 目标系统 | iOS 16.7.0+（覆盖 16.7.2） |
| 原始 SDK | `iphoneos27.2`（Xcode 27.0 / DTXcode 2720） |

## 结论先行

已完成：部署目标（`MinimumOSVersion` + Mach-O `LC_BUILD_VERSION.minos`）从 **17.0** 降到 **16.7**，主 App 与两个扩展（Widget / 投屏 Broadcast）全部同步，IPA 重新打包并保留可执行位。

**但仅靠改版本号无法让它在 16.7.2 上跑起来。** 主二进制用 chained fixups（`LC_DYLD_CHAINED_FIXUPS`），所有外部符号在**启动时**一次性绑定；而它硬引用了 4 组 iOS 17 才有的 SwiftUI API（见下表），在 16.7.2 上会以 `Symbol not found` 直接退出。要真正可用，必须改源码重编，改动点已整理在 [docs/compatibility-report.md](docs/compatibility-report.md)。

## 改动明细（Patch Table）

| 文件 | 字段 | 原值 | 新值 |
| --- | --- | --- | --- |
| `Payload/ZLink.app/Info.plist` | `MinimumOSVersion` | `17.0` | `16.7` |
| `Payload/ZLink.app/PlugIns/ZLinkBroadcast.appex/Info.plist` | `MinimumOSVersion` | `17.0` | `16.7` |
| `Payload/ZLink.app/PlugIns/ZLinkWidgets.appex/Info.plist` | `MinimumOSVersion` | `17.0` | `16.7` |
| `Payload/ZLink.app/ZLink` | `LC_BUILD_VERSION.minos` @ `0xED4` | `0x00110000`（17.0.0） | `0x00100700`（16.7.0） |
| `Payload/ZLink.app/PlugIns/ZLinkBroadcast.appex/ZLinkBroadcast` | `LC_BUILD_VERSION.minos` @ `0xC04` | `0x00110000`（17.0.0） | `0x00100700`（16.7.0） |
| `Payload/ZLink.app/PlugIns/ZLinkWidgets.appex/ZLinkWidgets` | `LC_BUILD_VERSION.minos` @ `0xBB4` | `0x00110000`（17.0.0） | `0x00100700`（16.7.0） |

SDK 字段（`sdk 27.2.0`）保留原值，不影响安装与运行。

## iOS 17+ 依赖清单

| 符号（去前缀） | 最低系统 | 导入 | 位置 | iOS 16 替代 |
| --- | --- | --- | --- | --- |
| `SwiftUI.View.containerRelativeFrame(_:alignment:)` | 17.0 | 强 | 主 App | `GeometryReader` + 手动计算宽高 |
| `SwiftUI.View.scrollTargetBehavior(_:)` | 17.0 | 强 | 主 App | `TabView(...).tabViewStyle(.page)` 或 `UIScrollView` 分页 |
| `SwiftUI.View.scrollPosition(id:anchor:)` | 17.0 | 强 | 主 App | `TabView(selection:)` / `UIPageViewController` |
| `SwiftUI.ContentTransition.symbolEffect(_:options:)` | 17.0 | 强 | 主 App | `withAnimation` + `.opacity` / `.scaleEffect` |
| `SwiftUI.View.onScrollGeometryChange(for:of:action:)` | 18.0 | **弱** | 主 App | `GeometryReader` + `PreferenceKey` 读取 offset |
| `SwiftUI.View.containerBackground(for:alignment:content:)` | 17.0 | 强 | Widget 扩展 | iOS 16 用 `ZStack` 铺满，不调用该修饰符 |
| `SwiftUI.View.presentationBackground(_:)` | 16.4 | 强 | 主 App | 16.7.2 可用，无需改 |

弱导入的 `onScrollGeometryChange` 在 16.7.2 上不会拦启动，但真被执行时同样会崩。

## 两条路线

### A. 先验证补丁包（5 分钟）

补丁包只为解决「装不上」。用 Sideloadly / AltStore / SideStore 重签安装到 16.7.2 设备：

1. 装得上 → 说明部署目标已放开；
2. 启动闪退 → 抓 `Console`/`Xcode Devices` 日志，正常会看到 `Symbol not found: _$s7SwiftUI4ViewPAAE22containerRelativeFrame...`，即上表所列 API 缺失，转路线 B。

### B. 源码移植（推荐，唯一能真正跑通的路径）

1. 把 Xcode 工程的 `IPHONEOS_DEPLOYMENT_TARGET` 设为 `16.7`（App 与两个 extension target 都要改）；
2. 按 [docs/compatibility-report.md](docs/compatibility-report.md) 替换 5 处 API（含可直接粘贴的 Swift 代码）；
3. 全工程搜索并清掉 `#available(iOS 17, *)` 之外的隐式 17+ 用法；
4. 按 [docs/build-from-source.md](docs/build-from-source.md) 在 GitHub Actions 的 macOS runner 上出无签名 IPA（把工程放进 `src/` 即可，含现成 workflow）。

## 仓库结构

```
.
├── README.md
├── CHANGELOG.md
├── docs/
│   ├── compatibility-report.md          # 依赖扫描结果 + iOS 16 替代代码
│   └── build-from-source.md             # 源码构建 + GitHub Actions workflow
├── tools/
│   ├── lower_minos.py                   # 任意 IPA 降部署目标（可复用）
│   └── scan_ios17_deps.py               # 扫描 IPA 里的 iOS 17+ 符号
```

补丁包 IPA 以 Release 附件形式发布（避免 31 MB 进 git 历史），在 [Releases](https://github.com/l85162262-lab/Z-Link-iOS16/releases) 页下载 `Z-Link-0.7.7-iOS16.7.ipa`。

## 使用工具

```bash
# 降任意 IPA 的部署目标
python tools/lower_minos.py input.ipa output.ipa --min-os 16.7

# 扫描是否还残留 iOS 17+ 依赖
python tools/scan_ios17_deps.py output.ipa
```

## 校验

```bash
shasum -a 256 Z-Link-0.7.7-iOS16.7.ipa   # 从 Releases 下载后校验
# bb53bf5a187c27a6df3104fe97f877ba18ef04ced879e13103a1331ca142fd72
```

## 说明

- 原包为无签名 IPA，仓库不包含任何证书或描述文件；安装时的签名由 Sideloadly/AltStore 完成。
- 本项目只做部署目标降级与兼容性分析，不修改业务逻辑、不上传任何用户数据。
- 16.7.2 可用的安装方式：Sideloadly（Windows/macOS）、AltStore/SideStore（需自签）；TrollStore 不支持 16.7.2。
