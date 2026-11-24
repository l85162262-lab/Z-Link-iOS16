# 源码构建（iOS 16.7）

补丁包只能解决「装不上」，要真正在 16.7.2 跑起来必须重编。本文给出从源码到无签名 IPA 的完整步骤。

## 1. 调整部署目标

Xcode 里把三个 target 的 `IPHONEOS_DEPLOYMENT_TARGET` 全部改成 `16.7`：

- `ZLink`（主 App）
- `ZLinkWidgets`（Widget 扩展）
- `ZLinkBroadcast`（投屏扩展）

命令行等价写法：

```bash
xcodebuild -project ZLink.xcodeproj -scheme ZLink \
  IPHONEOS_DEPLOYMENT_TARGET=16.7 build
```

## 2. 替换 iOS 17+ API

按 [compatibility-report.md](compatibility-report.md) 第 4 节逐项替换：

| 原 API | 最低系统 | 替代 |
| --- | --- | --- |
| `containerRelativeFrame` | 17.0 | `GeometryReader` 手动算宽高 |
| `scrollTargetBehavior` | 17.0 | `TabView` + `.tabViewStyle(.page)` |
| `scrollPosition(id:)` | 17.0 | `TabView(selection:)` |
| `onScrollGeometryChange` | 18.0 | `PreferenceKey` 读 offset |
| `ContentTransition.symbolEffect` | 17.0 | `.transition` + `withAnimation` |
| `containerBackground`（Widget） | 17.0 | `ZStack` 铺底 |

改完用仓库里的扫描脚本自查，退出码 0 才算干净：

```bash
python tools/scan_ios17_deps.py build/Z-Link.ipa
```

## 3. GitHub Actions 出包

把 Xcode 工程放进 `src/`，然后在仓库网页 `Add file → Create new file` 新建
`.github/workflows/build-ios16.yml`，粘贴下面内容（网页创建不需要 `workflow` scope，
用 API/命令行上传才需要）：

```yaml
name: Build unsigned IPA (iOS 16.7)

on:
  workflow_dispatch:
    inputs:
      scheme:
        description: Xcode scheme（留空则自动取第一个）
        required: false
  push:
    branches: [main]
    paths:
      - 'src/**'

jobs:
  build:
    if: ${{ hashFiles('src/**/*.xcodeproj', 'src/**/*.xcworkspace') != '' }}
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v4

      - name: Show toolchain
        run: xcodebuild -version

      - name: Build
        env:
          SCHEME_INPUT: ${{ github.event.inputs.scheme }}
        run: |
          set -euo pipefail
          PROJECT=$(find src -maxdepth 4 \( -name '*.xcworkspace' -o -name '*.xcodeproj' \) | head -n1)
          echo "project: $PROJECT"
          if [[ "$PROJECT" == *.xcworkspace ]]; then FLAG="-workspace"; else FLAG="-project"; fi

          if [[ -n "${SCHEME_INPUT}" ]]; then
            SCHEME="${SCHEME_INPUT}"
          else
            SCHEME=$(xcodebuild -list "$FLAG" "$PROJECT" | sed -n '/Schemes:/,$p' | sed -n '2p' | xargs)
          fi
          echo "scheme: $SCHEME"

          DERIVED="$RUNNER_TEMP/dd"
          xcodebuild "$FLAG" "$PROJECT" \
            -scheme "$SCHEME" \
            -configuration Release \
            -sdk iphoneos \
            -derivedDataPath "$DERIVED" \
            IPHONEOS_DEPLOYMENT_TARGET=16.7 \
            CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" \
            CODE_SIGN_ENTITLEMENTS=""

          APP=$(find "$DERIVED/Build/Products/Release-iphoneos" -maxdepth 1 -name '*.app' | head -n1)
          echo "app: $APP"

          otool -l "$APP/${APP##*/}" | grep -A2 LC_BUILD_VERSION || true

          mkdir -p out/Payload
          cp -R "$APP" out/Payload/
          (cd out && zip -qry "../${APP##*/}-unsigned.ipa" Payload)

          shasum -a 256 "${APP##*/}-unsigned.ipa"

      - uses: actions/upload-artifact@v4
        with:
          name: unsigned-ipa
          path: '*-unsigned.ipa'
          if-no-files-found: error
```

产物在 Actions 运行的 Artifacts 里，下载后用 Sideloadly 重签安装。

## 4. 真机验收

- [ ] 16.7.2 冷启动不闪退
- [ ] 孪生仪表、卡片左右滑动、投屏连接、桌面小组件逐项打开
- [ ] 17.x / 18.x 设备回归（16 的写法向上兼容）
