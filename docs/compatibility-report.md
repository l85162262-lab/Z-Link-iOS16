# 兼容性分析报告

目标：让 Z-Link 0.7.7（原 `MinimumOSVersion = 17.0`）运行在 iOS 16.7.2 上。

## 1. 包结构

```
Payload/ZLink.app
├── ZLink                      # 主二进制，arm64，12.1 MB
├── Info.plist                 # com.liruixin.zlink, 0.7.7 (build 32)
└── PlugIns
    ├── ZLinkBroadcast.appex   # 投屏扩展，191 KB
    └── ZLinkWidgets.appex     # 桌面小组件，1.1 MB
```

无 `Frameworks/` 目录，无内嵌动态库，Swift 运行时走系统 `/usr/lib/swift`（iOS 12.2+ 自带），不需要额外 back-deployment 库。

## 2. 原始构建信息

| 项 | 值 |
| --- | --- |
| `MinimumOSVersion` | 17.0 |
| `LC_BUILD_VERSION.minos` | 17.0.0（三个二进制一致） |
| `LC_BUILD_VERSION.sdk` | 27.2.0 |
| `DTXcode` / `DTXcodeBuild` | 2720 / 27B52（Xcode 27.0） |
| 链接方式 | `LC_DYLD_CHAINED_FIXUPS`（启动时全量绑定，无惰性绑定） |
| 架构 | arm64（`0x100000c`） |

**关键点**：chained fixups 在进程启动时解析全部 import。只要有一个强引用符号在系统库里不存在，dyld 就直接 `Symbol not found` 终止，不会进入 `main`。所以「把版本号改小」对这类包只能解决安装，解决不了启动。

## 3. 扫描结果

对三个二进制做 `LC_SYMTAB` 未定义符号扫描，命中 iOS 17/18 新增 API 如下。

### 3.1 主 App（`Payload/ZLink.app/ZLink`）

| 符号 | 最低系统 | 绑定 | 说明 |
| --- | --- | --- | --- |
| `_$s7SwiftUI4ViewPAAE22containerRelativeFrame_9alignmentQrAA4AxisO3SetV_AA9AlignmentVtF` | 17.0 | 强 | `.containerRelativeFrame` 实现 |
| `...containerRelativeFrame...FQOMQ` | 17.0 | 强 | 对应不透明返回类型的元数据描述符 |
| `_$s7SwiftUI4ViewPAAE20scrollTargetBehavioryQrqd__AA06ScrolleF0Rd__lF` | 17.0 | 强 | `.scrollTargetBehavior` |
| `...scrollTargetBehavior...FQOMQ` | 17.0 | 强 | 同上 |
| `_$s7SwiftUI4ViewPAAE14scrollPosition2id6anchorQrAA7BindingVyqd__SgG_AA9UnitPointVSgtSHRd__lF` | 17.0 | 强 | `.scrollPosition(id:anchor:)` |
| `...scrollPosition...FQOMQ` | 17.0 | 强 | 同上 |
| `_$s7SwiftUI17ContentTransitionV12symbolEffect_7optionsACx_7Symbols06SymbolF7OptionsVtAF0cdiF0RzAF0iF0RzlFZ` | 17.0 | 强 | `.contentTransition(.symbolEffect(...))` |
| `_$s7SwiftUI4ViewPAAE22onScrollGeometryChange3for2of6action...` | 18.0 | 弱 | `.onScrollGeometryChange`（编译器按 18.0 标了 weak） |
| `_$s7SwiftUI4ViewPAAE22presentationBackgroundyQrqd__AA10ShapeStyleRd__lF` | 16.4 | 强 | 16.7.2 可用，无需处理 |

结论：**7 个强引用符号在 iOS 16.7.2 上不存在**，启动必崩。

### 3.2 投屏扩展（`ZLinkBroadcast`）

无 iOS 17+ 依赖，降版本号后可直接使用。

### 3.3 Widget 扩展（`ZLinkWidgets`）

| 符号 | 最低系统 | 绑定 |
| --- | --- | --- |
| `_$s7SwiftUI4ViewPAAE19containerBackground3for9alignment7content...` | 17.0 | 强 |
| `...FQOMQ` | 17.0 | 强 |

主 App 不加载该 appex，但桌面添加小组件时会被 WidgetKit 拉起来并崩溃。要恢复小组件功能需按 4.5 改。

## 4. iOS 16 替代实现

以下代码可直接替换对应调用，改完把三个 target 的 `IPHONEOS_DEPLOYMENT_TARGET` 设为 `16.7` 重编即可。

### 4.1 `containerRelativeFrame` → `GeometryReader`

原（iOS 17）：

```swift
Color.clear
    .containerRelativeFrame(.horizontal, count: 2, span: 1, spacing: 8)
```

替换（iOS 16，等价于「一行放 2 个、间距 8」）：

```swift
GeometryReader { geo in
    let count: CGFloat = 2
    let spacing: CGFloat = 8
    let itemWidth = (geo.size.width - spacing * (count - 1)) / count
    Color.clear.frame(width: itemWidth, height: geo.size.height)
}
.frame(height: 120) // 外层给固定高度，GeometryReader 会把高度撑满
```

如果原调用是 `containerRelativeFrame(.horizontal) { length, axis in ... }` 这种按比例算的写法，把 `length` 直接换成 `geo.size.width` 即可。

### 4.2 `scrollTargetBehavior(.paging)` → `TabView` 分页

原（iOS 17）：

```swift
ScrollView(.horizontal) {
    LazyHStack(spacing: 12) { ForEach(items) { CardView($0) } }
}
.scrollTargetBehavior(.paging)
```

替换（iOS 16）：

```swift
TabView {
    ForEach(items) { item in
        CardView(item).padding(.horizontal, 16)
    }
}
.tabViewStyle(.page(indexDisplayMode: .never))
.frame(height: 200)
```

需要保留「松手吸附到整页、无页码点」的原观感，`TabView` 的 `.page` 样式就是 iOS 16 上最接近的实现。

### 4.3 `scrollPosition(id:)` → `TabView(selection:)`

原（iOS 17）：

```swift
@State private var currentID: Item.ID?
ScrollView(.horizontal) { ... }
.scrollPosition(id: $currentID)
```

替换（iOS 16）：

```swift
@State private var currentID: Item.ID?
TabView(selection: $currentID) {
    ForEach(items) { item in
        CardView(item).tag(item.id)
    }
}
.tabViewStyle(.page(indexDisplayMode: .never))
```

### 4.4 `onScrollGeometryChange` → `PreferenceKey`

原（iOS 18）：

```swift
ScrollView { content }
.onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { old, new in ... }
```

替换（iOS 16）：

```swift
private struct ScrollOffsetKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

ScrollView {
    content
        .background(
            GeometryReader { geo in
                Color.clear.preference(
                    key: ScrollOffsetKey.self,
                    value: -geo.frame(in: .named("scroll")).minY
                )
            }
        )
}
.coordinateSpace(name: "scroll")
.onPreferenceChange(ScrollOffsetKey.self) { offset in
    // 原来在 action 里做的事放这里
}
```

### 4.5 Widget `containerBackground` → `ZStack` 铺底

原（iOS 17）：

```swift
Text("剩余 42%")
    .containerBackground(for: .widget) { Color.black }
```

替换（iOS 16）：

```swift
ZStack {
    Color.black          // iOS 16 的 widget 没有 containerBackground，内容自行铺满
    Text("剩余 42%")
}
```

注意 iOS 16 的 widget 不能使用 `.contentMarginsDisabled()`、`.containerBackgroundRemovable()` 等 17+ 修饰符；如果原代码里还有，一并删掉。

### 4.6 `ContentTransition.symbolEffect` → 显式过渡

原（iOS 17）：

```swift
Image(systemName: iconName)
    .contentTransition(.symbolEffect(.replace))
```

替换（iOS 16）：

```swift
Image(systemName: iconName)
    .id(iconName)                       // 让切换时真正替换视图，触发 transition
    .transition(.opacity.combined(with: .scale(scale: 0.9)))

// 触发处
withAnimation(.easeInOut(duration: 0.2)) { iconName = newName }
```

## 5. 验收清单

- [ ] 三个 target 的 `IPHONEOS_DEPLOYMENT_TARGET = 16.7`
- [ ] 全工程搜索 `containerRelativeFrame`、`scrollTargetBehavior`、`scrollPosition`、`onScrollGeometryChange`、`symbolEffect`、`containerBackground`，无残留
- [ ] 编译通过，`otool -l` 检查 `minos 16.7.0`
- [ ] 真机 16.7.2：冷启动、进入孪生仪表、左右滑动卡片、连接车机投屏、添加桌面小组件，五项都不崩
- [ ] 17.x / 18.x 设备回归一遍（16 的写法在 17 上同样有效）
