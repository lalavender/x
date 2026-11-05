# yh Explorer 设计系统规范

> 版本 `1.0.0` · 2026-10-24 · 适用对象 `tools/yh-explorer.html`（648 行单文件）
> 配套可运行页面（原 `deliverables/gstack/` 下）未入库、仓库内不存在，仅本规范文本保留；
> 2026-11-06 由 `deliverables/gstack/` 迁入本目录。

**一句话定位**：一套为「编译器工具界面」而生的暗色优先设计系统 —— 信息密度优先、诊断可读、状态诚实、键盘可达。

**三个关键词**：`Dense`（密集）/ `Honest`（诚实）/ `Monospace-first`（等宽优先）

---

## 0. 边界声明

| 项 | 约定 |
|---|---|
| 影响范围 | 仅 `tools/yh-explorer.html` 与其后续页面。不进入编译器本体、不影响 `compiler/` 产物 |
| 技术约束 | 纯 HTML + CSS（+ 少量原生 JS）。**零框架、零构建链、零 CDN**，与项目铁律一致 |
| 单文件约束 | 所有 token 与组件类内联在同一个 `<style>` 里；不新增 `.css` 文件、不引入 `@import` |
| 主题默认 | 暗色为默认（编译器工具的主要使用场景是长时间盯屏） |
| 本轮不改动 | `tools/yh-explorer.html` 保持原样，本规范与示例页面为独立交付物 |

> `design-html` skill 已加载。其规范要求"self-contained HTML + embedded CSS + 语义化标记 + 响应式"，本交付物全部满足；但该 skill 建议的 Pretext 框架（30KB vendor 依赖）与本项目"零依赖单文件"铁律冲突，且仓库 `vendor/` 下并无 `pretext.js`，故**按 skill 的输出形态规范执行、不引入其框架依赖**。这是一次有意识的取舍，已在此记录。

---

## 1. 设计原则

六条，按优先级排序。冲突时上位原则胜出。

### P1 · 信息密度优先，但不牺牲可扫读性
编译器工具的用户是"读汇编的人"。屏幕空间比美观重要：行高锁 `21px`、控件高度 `≤28px`、面板头 `40px`、控制台默认 `170px`。密度靠**节奏**而非靠"塞满"——同一屏内只允许 3 级视觉重量（标题 / 正文 / 次要），第 4 级必须删掉。

### P2 · 诊断是一等公民，不是日志
编译器输出的错误不是"运行结果的一部分"，而是**产品本身**。因此：错误码、位置（`file:line:col`）、严重级、文案、**修复建议**必须是结构化字段而非一整段字符串。契约版本化落地后，"接口版本 N 需要 M，请重建种子"这类诊断必须能一眼看出「哪里错 / 为什么 / 下一步做什么」。

### P3 · 状态诚实：宁可说"不知道"，不许假装"正常"
现有页面的状态点只有 `· / ✓ / ✕` 三态，**缺失"编译中"**——用户在 700ms 防抖窗口里看到的 `·` 与"从未编译"完全一样。设计系统要求：任何异步过程都必须有独立可见态；服务器不可达与"编译失败"必须是**两种不同的视觉语言**（前者是环境问题，后者是代码问题，修复动作完全不同）。

### P4 · 键盘优先，鼠标是加速器
`Cmd/Ctrl+Enter` 运行、`Cmd/Ctrl+S` 拦截、`Tab` 缩进、`Esc` 收起控制台、`Cmd/Ctrl+K` 聚焦编译器路径。所有可交互元素必须可 Tab 到达、有可见焦点环（`≥3:1`）、焦点顺序符合视觉顺序。

### P5 · 等宽是主字体，比例字体只做标签
代码、汇编、路径、错误位置、退出码 → 等宽。面板标题、按钮、提示 → 比例字体。**不允许**在代码区出现比例字体（对齐会崩），也**不允许**用等宽字体排中文长句（阅读效率差）。

### P6 · 暗色为默认，亮色是完整公民
暗色不是"深色皮肤"，亮色也不是"把颜色反过来"。两套主题各自独立校准对比度（见 §4），亮色主题的每一个语法色都实测 `≥4.5:1`。

---

## 2. Token 体系

### 2.1 四层结构

```
L0  兼容桥（legacy alias）   ← 迁移期临时层，值 = 现有硬编码值，逐字节相等
     ↓ var()
L1  语义基础层（surface / border / text / status）   ← 组件 90% 的取值来源
L2  语法域层（syn-*）                                ← 独立成层：有自己的对比度规则，整组换主题
L3  组件域层（btn-* / dot-* / focus-ring / editor-*） ← 仅当组件需要 L1/L2 推导不出的值时存在
```

**为什么是四层而不是两层**：
- L1/L2 分离是必须的——语法色是"内容色"，其对比度规则（代码正文 `≥4.5`）与 UI 色（描边 `≥1.2`、焦点环 `≥3.0`）完全不同，混在一层会导致换主题时互相牵连。
- L0 是**迁移工具**，不是设计决策。它让"换 token"这一步可以做到**零像素变化**（见 §6），迁完即删。
- L3 刻意保持很小（10 个），避免变成"每个组件一套私有变量"的伪系统。

### 2.2 命名规则

```
--yh-<层域>-<角色>[-<变体>]
     │        │        └─ hover / solid / strong / muted / gutter
     │        └─ surface | text | border | syn | btn | dot | editor | diag
     └─ 固定前缀，避免与宿主页面/未来嵌入场景冲突
```

- 全部小写、连字符分隔、**不带单位以外的语义缩写**（`--yh-text-muted` 而不是 `--yh-tm`）。
- 不使用 `--yh-color-red-400` 这类"调色板序号"命名 —— 换主题时序号含义会翻转，维护者必然搞错。
- 允许的例外：`--yh-syn-kw` 等沿用现有短名（`kw/num/str/com/fn/label/dir`），因为语法高亮器已按这些名字产出 class，改名收益为零、风险为正。

### 2.3 L0 兼容桥（迁移期，值逐字节等价）

```css
/* 迁移第 1 步插入；第 4 步删除。值必须与现有 :root 完全一致。 */
:root {
  --bg:          var(--yh-legacy-bg);          /* #282c34 */
  --bg-panel:    var(--yh-legacy-bg-panel);    /* #21252b */
  --bg-input:    var(--yh-legacy-bg-input);    /* #1b1d23 */
  --border:      var(--yh-legacy-border);      /* #181a1f */
  --text:        var(--yh-legacy-text);        /* #abb2bf */
  --text-dim:    var(--yh-legacy-text-dim);    /* #6b7280  ← 2.90:1，见 §4.5 债务表 */
  --gutter-text: var(--yh-legacy-gutter);      /* #495162  ← 1.76:1，见 §4.5 债务表 */
  --kw:  var(--yh-legacy-kw);   --num: var(--yh-legacy-num);
  --str: var(--yh-legacy-str);  --com: var(--yh-legacy-com);
  --fn:  var(--yh-legacy-fn);   --label: var(--yh-legacy-label);
  --dir: var(--yh-legacy-dir);
  --ok:  var(--yh-legacy-ok);   --err: var(--yh-legacy-err);
  --mono: var(--yh-font-mono);
}
```

`--yh-legacy-*` 是"考古层"，只存历史值，**新代码永远不要用**。这样 `--text-dim` 与新 `--yh-text-muted` 可以并存：前者保证像素不变，后者保证对比度达标，迁移时逐个替换使用点即可。

---

## 3. Token 全量定义

### 3.1 颜色 · L1 语义基础层

| Token | 暗色（默认） | 亮色 | 用途 |
|---|---|---|---|
| `--yh-surface-editor` | `#282c34` | `#fafafa` | 编辑器 / 汇编区底色 |
| `--yh-surface-panel` | `#21252b` | `#f0f0f1` | 面板头 / 行号槽 / 控制台底 |
| `--yh-surface-input` | `#1b1d23` | `#ffffff` | 输入框 / 下拉框底 |
| `--yh-surface-raised` | `#2f343d` | `#ffffff` | 卡片 / 浮起层（新增，暗色比编辑器略亮） |
| `--yh-surface-hover` | `#3a3f4b` | `#e8e8ea` | 悬停底 / 状态点空闲底 / 拖拽条激活 |
| `--yh-border` | `#181a1f` | `#d4d4d5` | 分隔线（装饰性，非状态载体） |
| `--yh-border-strong` | `#33363d` | `#8a8b90` | 输入框 / 幽灵按钮描边（亮色达 3.40:1） |
| `--yh-text` | `#abb2bf` | `#383a42` | 正文 / 代码正文 |
| `--yh-text-strong` | `#c8cdd6` | `#202127` | 面板标题 / 段标题（现有硬编码 `#c8cdd6` 收编） |
| `--yh-text-muted` | `#8b93a3` | `#5c5f66` | 次要说明 / 控制台提示（**新增，替代 `--text-dim`**） |
| `--yh-text-gutter` | `#6e7788` | `#696c73` | 行号（**新增，替代 `--gutter-text`**） |
| `--yh-accent` | `#61afef` | `#0969da` | 焦点 / 链接 / 交互强调（= 现有 `--fn`） |
| `--yh-ok` | `#2ea043` | `#166f30` | 成功（文字/图标场景） |
| `--yh-ok-solid` | `#2ea043` | `#1a7f37` | 成功实心填充（按钮/圆点底） |
| `--yh-ok-solid-hover` | `#38b84f` | `#166f30` | 成功实心悬停 |
| `--yh-warn` | `#e5c07b` | `#8a5c00` | 警告 / 契约版本不匹配（**新增**） |
| `--yh-err` | `#f14c4c` | `#b32024` | 失败 / 错误 |
| `--yh-info` | `#56b6c2` | `#0b7285` | 信息 / 进行中（**新增**） |

### 3.2 颜色 · L2 语法域层

| Token | 暗色 | 亮色 | 语法元素 |
|---|---|---|---|
| `--yh-syn-kw` | `#e06c75` | `#c02b22` | 关键字 / 类型 |
| `--yh-syn-num` | `#d19a66` | `#8a5d00` | 数字 / 寄存器 / 立即数 |
| `--yh-syn-str` | `#98c379` | `#37713a` | 字符串 / 字符 |
| `--yh-syn-com` | `#5c6370` | `#6a6b72` | 注释（斜体） |
| `--yh-syn-fn` | `#61afef` | `#1f5fd0` | 函数名 / 汇编助记符 |
| `--yh-syn-label` | `#d7dae0` | `#202127` | 汇编标签（粗体） |
| `--yh-syn-dir` | `#c678dd` | `#a626a4` | 汇编伪指令 |

### 3.3 颜色 · L3 组件域层

| Token | 暗色 | 亮色 | 用途 |
|---|---|---|---|
| `--yh-focus-ring` | `#61afef` | `#0969da` | 焦点环色 |
| `--yh-focus-ring-w` | `2px` | `2px` | 焦点环宽度 |
| `--yh-btn-primary-bg` | `#2ea043` | `#1a7f37` | 主按钮底 |
| `--yh-btn-primary-bg-hover` | `#38b84f` | `#166f30` | 主按钮悬停底 |
| `--yh-btn-primary-fg` | `#ffffff` | `#ffffff` | 主按钮文字（暗色下见 §4.5 债务 D4） |
| `--yh-dot-idle-bg` | `#3a3f4b` | `#dcdcdf` | 状态点 · 空闲 |
| `--yh-dot-ok-bg` | `#2ea043` | `#1a7f37` | 状态点 ✓ |
| `--yh-dot-err-bg` | `#f14c4c` | `#b32024` | 状态点 ✕ |
| `--yh-dot-busy-bg` | `#56b6c2` | `#0b7285` | 状态点 编译中（**新增第四态**） |
| `--yh-editor-line-active` | `#32353d` | `#ececef` | 当前行高亮（现有 `rgba(255,255,255,.045)` 的实色等价） |
| `--yh-editor-sel` | `rgba(97,175,239,.25)` | `rgba(9,105,218,.25)` | 选区（暗色值保留现状，AA 档见 §4.5） |
| `--yh-editor-caret` | `#f0f0f0` | `#1b1d23` | 光标 |
| `--yh-diag-err-bg` | `rgba(241,76,76,.10)` | `rgba(179,32,36,.07)` | 错误诊断条底 |
| `--yh-diag-warn-bg` | `rgba(229,192,123,.10)` | `rgba(138,92,0,.07)` | 警告诊断条底 |
| `--yh-console-out` | `#b5bd68` | `#2c6632` | 程序 stdout |
| `--yh-console-err` | `#f14c4c` | `#b32024` | 编译错误 / stderr |
| `--yh-console-sys` | `#f14c4c` | `#b32024` | 程序 stderr（与 err 同色，靠段标题区分） |

> `--yh-console-sys` 与 `--yh-console-err` 同值但**必须保留为两个 token**：语义不同（编译器说的 vs 程序说的），未来若要分开（例如 sys 改用 `--yh-warn`）只需改一处。

### 3.4 字体

```css
--yh-font-ui: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
--yh-font-mono: "SF Mono", ui-monospace, Menlo, Consolas, "Courier New", monospace;
```

| Token | 值 | 用途 |
|---|---|---|
| `--yh-fs-2xs` | `11px` | 徽标 / 对比度标注 |
| `--yh-fs-xs` | `11.5px` | 编译器路径 / 选项输入框（现有值） |
| `--yh-fs-sm` | `12px` | 幽灵按钮 / 下拉框（现有值） |
| `--yh-fs-md` | `12.5px` | 控制台正文 / 选项输入（现有值） |
| `--yh-fs-base` | `13px` | 页面默认 / 主按钮（现有值） |
| `--yh-fs-lg` | `14px` | **代码与汇编**（现有值，硬约束） |
| `--yh-fs-xl` | `16px` | 分区标题 |
| `--yh-fs-2xl` | `20px` | 页面标题 |
| `--yh-fs-3xl` | `26px` | 设计系统页 Hero |

| Token | 值 | 用途 |
|---|---|---|
| `--yh-lh-code` | `21px` | **代码行高（硬约束）** |
| `--yh-lh-tight` | `1.3` | 标题 |
| `--yh-lh-ui` | `1.5` | UI 文本 |
| `--yh-lh-prose` | `1.7` | 长说明 |
| `--yh-fw-normal` | `400` | 正文 |
| `--yh-fw-medium` | `500` | 次要强调 |
| `--yh-fw-semibold` | `600` | 面板标题 / 按钮 |
| `--yh-fw-bold` | `700` | 段标题 / 汇编标签 |
| `--yh-tracking-caps` | `.04em` | 全大写小标签 |

> ⚠️ **硬约束**：`--yh-lh-code` 必须等于 JS 里的 `const LINE_H = 21`。迁移时要么保持 21px 字面量，要么在 `init()` 里用 `parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--yh-lh-code'))` 覆盖 `LINE_H`。两者不同步会导致「当前行高亮错位」——这是三层叠加编辑器最典型的 bug。

### 3.5 间距阶（4px 主阶 + 2px 半阶）

```css
--yh-sp-0:0; --yh-sp-1:2px; --yh-sp-2:4px; --yh-sp-3:6px; --yh-sp-4:8px;
--yh-sp-5:10px; --yh-sp-6:12px; --yh-sp-7:14px; --yh-sp-8:16px; --yh-sp-9:18px;
--yh-sp-10:20px; --yh-sp-11:24px; --yh-sp-12:32px; --yh-sp-13:40px; --yh-sp-14:52px;
```

**为什么允许 2px 半阶**：现有页面的 `10px`（面板内边距）、`14px`（控制台左右内边距）、`18px`（Run 按钮左右内边距）、`52px`（行号槽宽）都不是 4 的倍数。若强行归到 4 的倍数，迁移就不再是"零像素变化"，违背硬要求。因此定义为：**4px 为主阶（布局、区块间距），2px 为半阶（仅限紧凑控件的内边距）**。所有现有值都能落到阶梯上，这是刻意设计的兼容性。

| 语义 | Token | 值 | 现有对应 |
|---|---|---|---|
| 面板头高 | `--yh-h-pane-header` | `40px` | `.pane-header` height |
| 控制台高 | `--yh-h-console` | `170px` | `#console` height |
| 控制台折叠高 | `--yh-h-console-folded` | `34px` | `#console.folded` |
| 行号槽宽 | `--yh-w-gutter` | `52px` | `.gutter` / `.asm-gutter` |
| 拖拽条宽 | `--yh-w-splitter` | `5px` | `#split` |
| 控件最小高 | `--yh-h-control` | `26px` | 输入框 / 按钮 |
| 状态点直径 | `--yh-h-dot` | `20px` | `#status-dot` |

### 3.6 圆角 / 层级 / 动效

```css
--yh-radius-sm:4px; --yh-radius-md:6px; --yh-radius-lg:10px; --yh-radius-full:999px;
```

现有输入框与按钮均为 `6px` → `--yh-radius-md`；状态点为 `50%` → `--yh-radius-full`。

```css
--yh-z-base:0; --yh-z-line:1; --yh-z-highlight:2; --yh-z-gutter:3;
--yh-z-input:4; --yh-z-splitter:10; --yh-z-banner:20; --yh-z-toast:30;
```

**必须保留 `1/2/3/4` 这四个值**：它们对应三层叠加编辑器的堆叠顺序（当前行 < 高亮层 < 行号槽 < textarea），任何改动都会破坏编辑器。

```css
--yh-dur-fast:120ms; --yh-dur-base:180ms; --yh-dur-slow:260ms;
--yh-ease-standard:cubic-bezier(.4,0,.2,1);
--yh-ease-out:cubic-bezier(0,0,.2,1);
--yh-ease-in-out:cubic-bezier(.4,0,.6,1);
```

**动效预算**：编译器工具的任何过渡都不得让用户等待"动画"。上限 `260ms`，且只允许作用于 `background-color / border-color / color / opacity / transform`。**禁止**对 `width / height / top / left` 做过渡（布局抖动 + 与编辑器滚动同步打架）。

JS 侧的时序常量（不可 token 化，须在代码里显式命名）：

| 常量 | 值 | 含义 |
|---|---|---|
| `COMPILE_DEBOUNCE_MS` | `700` | 编辑后自动汇编的防抖（现有 700ms） |
| `COPY_FLASH_MS` | `1200` | 复制成功提示闪现时长（现有 1200ms） |
| `RUN_TIMEOUT_MS` | 由后端决定 | 运行超时（后端返回 `exit: null`） |

---

## 4. 暗 / 亮双主题

### 4.1 实现方式

```css
:root { /* 暗色 = 默认 */ }
[data-theme="light"] { /* 亮色：只覆盖颜色类 token，不动字号/间距/圆角/层级 */ }
@media (prefers-color-scheme: light) { :root:not([data-theme]) { /* 跟随系统 */ } }
```

三条规则：
1. **主题切换只覆盖颜色 token**。字号、间距、圆角、层级、动效在两个主题下完全一致 —— 避免"换主题导致布局跳动"。
2. **`data-theme` 挂在 `<html>` 上**，不用 `.light` class（属性选择器优先级稳定，且可与 `data-contrast` 正交叠加）。
3. **首次访问读 `localStorage.yh-explorer.theme`，无值时跟随 `prefers-color-scheme`，但暗色优先**（编译器工具默认暗色）。

```js
// 主题切换（约 12 行，无依赖）
const THEME_KEY = 'yh-explorer.theme';
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem(THEME_KEY, t);
  document.querySelectorAll('[data-theme-btn]').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.themeBtn === t)));
}
applyTheme(localStorage.getItem(THEME_KEY) ||
  (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
```

### 4.2 亮色主题设计思路

亮色不是"反色"。它保留 One Dark 的**色相身份**（红=关键字、橙=数字、绿=字符串、蓝=函数、紫=伪指令），只把明度压到能在白底上站住：

- 底色用 `#fafafa` 而非纯白 —— 纯白 + 深色等宽代码会产生光晕（halation），长时间阅读疲劳。
- 面板 `#f0f0f1` 比编辑器**暗**，与暗色主题"面板比编辑器暗"的方向一致，保持层级感一致。
- 语法色统一压暗 1~2 档，宁可牺牲一点"鲜艳"也要拿到 `≥4.5:1`。

### 4.3 亮色主题实测对比度（背景 `#fafafa`）

全部数字为 WCAG 2.1 相对亮度公式实算结果（`(L1+0.05)/(L2+0.05)`，sRGB 线性化），非估算。

| Token | 值 | 对比度 | 判定 |
|---|---|---|---|
| `--yh-text` | `#383a42` | **10.86:1** | AA ✓ |
| `--yh-text-strong` | `#202127` | **15.38:1** | AAA ✓ |
| `--yh-text-muted` | `#5c5f66` | **6.13:1** | AA ✓ |
| `--yh-text-gutter` | `#696c73` | **5.04:1** | AA ✓ |
| `--yh-accent` | `#0969da` | **4.97:1** | AA ✓ |
| `--yh-ok` | `#166f30` | **6.00:1** | AA ✓ |
| `--yh-warn` | `#8a5c00` | **5.57:1** | AA ✓ |
| `--yh-err` | `#b32024` | **6.39:1** | AA ✓ |
| `--yh-info` | `#0b7285` | **5.35:1** | AA ✓ |
| `--yh-syn-kw` | `#c02b22` | **5.57:1** | AA ✓ |
| `--yh-syn-num` | `#8a5d00` | **5.52:1** | AA ✓ |
| `--yh-syn-str` | `#37713a` | **5.61:1** | AA ✓ |
| `--yh-syn-com` | `#6a6b72` | **5.08:1** | AA ✓ |
| `--yh-syn-fn` | `#1f5fd0` | **5.58:1** | AA ✓ |
| `--yh-syn-label` | `#202127` | **15.38:1** | AAA ✓ |
| `--yh-syn-dir` | `#a626a4` | **5.86:1** | AA ✓ |
| `--yh-console-out` | `#2c6632` | **6.59:1** | AA ✓ |

**亮色主题 17 个文字/语法 token 全部 `≥4.5:1`，无一例外。** 这是本规范对"亮底语法色"硬要求的交付结果。

面板底 `#f0f0f1` 上复测（控制台/面板头同样承载文字，必须一起验）：

| Token | 对比度 |
|---|---|
| `--yh-text` | **9.96:1** |
| `--yh-text-muted` | **5.62:1** |
| `--yh-text-gutter` | **4.62:1** |
| `--yh-syn-com` | **4.66:1** |
| `--yh-syn-kw` | **5.11:1** |
| `--yh-syn-str` | **5.14:1** |
| `--yh-syn-fn` | **5.11:1** |

亮色下最紧的一项是 `--yh-text-gutter` 在面板底的 **4.62:1**，仍达标（行号本身是"非必要信息"，4.62 已超过 AA 正文线）。

### 4.4 实心填充上的文字

| 组合 | 对比度 | 判定 |
|---|---|---|
| 白字 on `--yh-ok-solid` 暗 `#2ea043` | **3.37:1** | ✕ 不达标（现状） |
| 白字 on `--yh-ok-solid-hover` 暗 `#38b84f` | **2.58:1** | ✕ 更差（现状） |
| `#0d1117` on `#2ea043`（AA 档方案） | **5.61:1** | AA ✓ |
| 白字 on `--yh-err` 暗 `#f14c4c` | **3.57:1** | ✕ 不达标 |
| 白字 on `--yh-ok-solid` 亮 `#1a7f37` | **5.08:1** | AA ✓ |
| 白字 on `--yh-ok-solid-hover` 亮 `#166f30` | **6.27:1** | AA ✓ |
| 白字 on `--yh-err` 亮 `#b32024` | **6.67:1** | AA ✓ |

**亮色主题的按钮/徽标对比度天然更好**（深绿白字），暗色主题则因为绿太亮而"白字不够黑"。

### 4.5 暗色对比度债务表（必须如实记录）

现有暗色页面有 6 处不达标。因为硬要求是"换 token 后像素级一致"，**默认暗色主题保留原值**，同时提供 `[data-contrast="aa"]` 修饰档修复。这是"诚实优先"原则的直接应用：先承认债务，再给可选修复，不偷偷改设计。

| ID | 场景 | 现值 | 对比度 | AA 档值 | 修复后 | 视觉代价 |
|---|---|---|---|---|---|---|
| **D1** | 行号 `--gutter-text` | `#495162` | **1.76:1** | `#8b93a3` | 4.53:1 | 行号明显变亮 |
| **D2** | 次要文字 `--text-dim` | `#6b7280` | **2.90:1** | `#8b93a3` | 4.53:1 | 提示文字变亮 |
| **D3** | 注释 `--syn-com` | `#5c6370` | **2.32:1** | `#8e95a2` | 4.65:1 | 注释不再"退到背景里" |
| **D4** | Run 按钮白字 | `#fff` on `#2ea043` | **3.37:1** | 文字改 `#0d1117` | 5.61:1 | 按钮文字由白转近黑 |
| **D5** | 关键字 `--syn-kw` | `#e06c75` | **4.38:1** | `#e5747d` | 4.75:1 | 几乎无感（+6 明度） |
| **D6** | 选区文字 | `#abb2bf` on `#364d63` | **4.11:1** | 选区改 `#2b425b` | 4.85:1 | 选区更"深"而非更"亮" |

```css
/* 可选修饰档：与主题正交，可叠加在 dark 或 light 上 */
[data-contrast="aa"] {
  --yh-text-gutter: #8b93a3;
  --yh-text-muted:  #8b93a3;
  --yh-syn-com:     #8e95a2;
  --yh-btn-primary-fg: #0d1117;
  --yh-syn-kw:      #e5747d;
  --yh-editor-sel:  rgba(47,93,138,.45);   /* 实色 ≈ #2b425b */
}
[data-theme="light"][data-contrast="aa"] {
  --yh-text-gutter: #62656b;   /* 4.83:1 on panel */
  --yh-text-muted:  #52555c;
  --yh-syn-com:     #66676e;   /* 4.94:1 on panel */
}
```

> **D6 的反直觉点**：提高选区不透明度反而让文字更难读（选区变亮 → 与正文 `#abb2bf` 拉近）。正确做法是选一个**更暗、更低饱和**的蓝做选区底，让选区与底色的差（2.35:1）来自"更深"而不是"更亮"。

### 4.6 边框与焦点环

| 组合 | 对比度 | 判定 |
|---|---|---|
| `--yh-border` `#181a1f` on `#282c34`（暗分隔线） | **1.24:1** | 可见（装饰性，不承载状态） |
| `--yh-border-strong` `#33363d` on `#1b1d23`（暗输入框） | **1.39:1** | 可见 |
| `--yh-border` `#d4d4d5` on `#fafafa`（亮分隔线） | **1.42:1** | 可见 |
| `--yh-border-strong` `#8a8b90` on `#ffffff`（亮输入框） | **3.40:1** | ✓ 达 3:1 |
| `--yh-focus-ring` `#61afef` on `#1b1d23`（暗焦点） | **7.13:1** | ✓ |
| `--yh-focus-ring` `#0969da` on `#ffffff`（亮焦点） | **5.19:1** | ✓ |

暗色输入框描边只有 1.39:1 —— 低于 WCAG 1.4.11 对"状态载体"要求的 3:1。但输入框的**状态**由焦点环（7.13:1）与 placeholder 文字承载，描边本身是装饰。若未来要更严格，把 `--yh-border-strong` 暗色改为 `#4a505c`（约 1.9:1）或 `#5c6370`（约 2.3:1）；本轮不改，记录在案。

---

## 5. 组件清单

每个组件给出：**用途 / Anatomy / 状态 / 尺寸 / 可访问性**。

### C1 · pane-header（面板头）

- **用途**：标识区域身份（"yh 源码 #1" / "AArch64 汇编"），承载该区域的工具栏与状态指示。
- **Anatomy**：`标题(必) → 副标 small(选) → 控件组(选) → spacer → 操作组(必) → 状态点(选)`
- **状态**：`default` / `scrolled`（`overflow-x: auto` 出现横向滚动，隐藏滚动条）/ `busy`（子元素按钮 disabled）
- **尺寸**：高 `--yh-h-pane-header: 40px`；水平内边距 `--yh-sp-5: 10px`；元素间距 `--yh-sp-4: 8px`
- **可访问性**：`<div role="toolbar" aria-label="yh 源码工具栏">`；标题用真实文本节点而非图标；横向溢出时提供键盘可达（不要只靠 `overflow-x` 滚动 —— 溢出元素必须仍可 Tab 到）

### C2 · toolbar 输入（select / text）

- **用途**：选择编译器、输入自定义路径、附加编译选项。
- **Anatomy**：`label(视觉隐藏) → 控件 → 可选后缀图标`
- **状态**：`default` / `hover`（描边 `--yh-border-strong` 提亮）/ `focus`（`border-color: var(--yh-accent)` + `box-shadow: 0 0 0 2px color-mix(...)` 或 `outline: 2px solid var(--yh-focus-ring); outline-offset: 1px`）/ `invalid`（描边 `--yh-err` + 下方 `--yh-fs-2xs` 错误文本）/ `disabled`（`opacity:.5`，`cursor:not-allowed`）/ `readonly`
- **尺寸**：高 `26px`；内边距 `--yh-sp-2 --yh-sp-4`（4px 8px）；圆角 `--yh-radius-md`；路径框宽 `240px`、选项框宽 `130px`；字号：路径/选项用 `--yh-fs-xs` + 等宽，下拉用 `--yh-fs-sm`
- **可访问性**：`<label for>` 必须存在（可 `sr-only`）；placeholder **不能**替代 label；`aria-invalid="true"` 配合错误文本；`aria-describedby` 指向错误文本 id

### C3 · 按钮（primary / ghost / danger / icon）

- **用途**：Run（primary）、复制/清空/收起（ghost）、危险确认（danger）、主题切换（icon）。
- **Anatomy**：`[前图标] 文字 [后图标] [加载指示]`
- **状态矩阵**：

| 状态 | primary | ghost | danger |
|---|---|---|---|
| default | 底 `--yh-btn-primary-bg`，字 `--yh-btn-primary-fg` | 透明底，`--yh-border-strong` 描边，字 `--yh-text` | 底 `--yh-err`，字 `#fff` |
| hover | 底 `--yh-btn-primary-bg-hover` | 描边 `--yh-accent`，字 `--yh-text-strong` | 底提亮 8% |
| active | 底再压暗 6%，`transform: translateY(.5px)` | 底 `--yh-surface-hover` | 底压暗 6% |
| focus-visible | `outline: 2px solid var(--yh-focus-ring); outline-offset: 2px` | 同左 | 同左 |
| disabled | `opacity:.5; cursor:default`（**不用** `pointer-events:none`，否则键盘仍可聚焦但无反馈） | 同左 | 同左 |
| loading | 文字替换为 `编译中…` + 前置 12px 旋转指示器，`disabled` 但 `aria-busy="true"` | 同左 | — |

- **尺寸**：高 `26px`（ghost）/ `28px`（primary）；primary 内边距 `--yh-sp-3 --yh-sp-9`（6px 18px）；ghost 内边距 `--yh-sp-2 --yh-sp-5`（4px 10px）；圆角 `--yh-radius-md`
- **可访问性**：`<button>` 而非 `<div>`；图标按钮必须有 `aria-label`；loading 时 `aria-busy="true"` + `aria-live="polite"` 播报；**禁用态要说明原因**（`title` 或相邻文本，例如"编译中…"）

### C4 · 状态指示点（四态）

- **用途**：一眼回答"现在是什么状态"。是整个页面最重要的 20×20px。
- **Anatomy**：`圆点（色 + 符号）→ [可选] 文字标签`
- **四态**（现有只有三态，**新增 `compiling`**）：

| 状态 | 底色 | 符号 | 动效 | `aria-label` |
|---|---|---|---|---|
| `idle` | `--yh-dot-idle-bg` | `·` | 无 | 尚未编译 |
| `compiling` | `--yh-dot-busy-bg` | `◐` | `spin 900ms linear infinite`（`prefers-reduced-motion` 下改为静态 `◐`） | 正在编译 |
| `ok` | `--yh-dot-ok-bg` | `✓` | 无 | 编译成功 |
| `err` | `--yh-dot-err-bg` | `✕` | 无 | 编译失败 |

- **尺寸**：`20×20px`，`--yh-radius-full`，字号 `--yh-fs-sm`，白字（`ok`/`err`/`compiling` 底），`idle` 用 `--yh-text-muted`
- **可访问性**：`role="status"` + `aria-live="polite"` + `aria-label` 随状态更新；**不能只靠颜色区分**（`✓/✕/◐/·` 符号是色盲用户的唯一通道）；`title` 给鼠标用户补充细节（"编译成功（退出码 0）"）

### C5 · 代码视图（gutter / 高亮层 / 当前行 / 选区 / 错误行）

- **用途**：展示 yh 源码与汇编。
- **Anatomy（源码，三层叠加）**：
  ```
  .editor-wrap (position:relative)
    ├ .active-line      z-index: var(--yh-z-line)       当前行背景
    ├ .gutter           z-index: var(--yh-z-gutter)     行号，translateY 跟随滚动
    ├ pre.highlight      z-index: var(--yh-z-highlight) 高亮层，pointer-events:none
    └ textarea.code     z-index: var(--yh-z-input)      透明文字，caret-color 可见
  ```
- **Anatomy（汇编，只读）**：`.asm-wrap > .asm-inner > (.asm-gutter[sticky] + pre.asm-code)`
- **状态**：`default` / `focused` / `empty`（空文件 → 行号槽显示 1 行 + 占位文案）/ `has-error`（错误行左侧 3px `--yh-err` 竖条 + 行号变 `--yh-err`）/ `readonly`
- **尺寸**：字号 `--yh-fs-lg:14px`，行高 `--yh-lh-code:21px`，`tab-size:4`，行号槽宽 `--yh-w-gutter:52px`，内容左内边距 `64px`（= 52 + 12）
- **可访问性**：高亮层 `aria-hidden="true"`（否则屏幕阅读器读两遍）；`textarea` 必须有 `aria-label`（"yh 源码编辑器"）；错误行标记要配合 `aria-describedby` 指向诊断条目；**选区对比度见 D6**；`caret-color` 必须与背景有 `≥3:1` 差

### C6 · 控制台 section（out / err / sys）

- **用途**：承载编译诊断、程序 stdout、程序 stderr、退出码。
- **Anatomy**：`段标题（── 标题 ──）→ 段内容（等宽 pre-wrap）`，段之间空一行
- **三类语义 + 一类补充**：

| 类 | Token | 语义 | 现有类名 |
|---|---|---|---|
| `out` | `--yh-console-out` | 程序正常输出 | `.o-out` |
| `err` | `--yh-console-err` | 编译器诊断 / 程序 stderr | `.o-err` / `.o-sys` |
| `sys` | `--yh-console-sys` | 程序 stderr | `.o-sys` |
| `dim` | `--yh-text-muted` | 提示 / 建议动作 | `.o-dim` |

- **状态**：`empty`（"等待运行…"）/ `running`（`aria-busy="true"` + 段标题追加"运行中…"）/ `has-output` / `folded`（高 `34px`，仅留 header）
- **尺寸**：高 `170px`（`--yh-h-console`），折叠 `34px`；正文 `--yh-fs-md:12.5px` / `19px` 行高；内边距 `--yh-sp-2 --yh-sp-7 --yh-sp-5`（4px 14px 10px）
- **可访问性**：`role="log"` + `aria-live="polite"` + `aria-relevant="additions"`；**不要**用 `aria-live="assertive"`（会打断用户输入）；折叠时 `aria-expanded` 同步到按钮；段标题用 `<h3>` 或 `role="heading" aria-level="3"` 而非纯 span

### C7 · 诊断条目（含契约版本化变体）

- **用途**：把一行编译器 stderr 变成可操作的 UI。这是本设计系统**相对现状最大的增量**。
- **现有真实格式**（实测 `./yh build`）：

  ```
  src/main.yh:4:20: 错误: 不能把指针赋给非指针（用 .to_type）
  yh: 模块编译失败；已停止最终链接
  ```

  即 `file:line:col: 严重级: 文案（修复建议）`，最后一行是汇总。

- **Anatomy**：
  ```
  ┌─ [严重级图标] [错误码] [file:line:col] ─────────────── [复制] ┐
  │  文案                                                        │
  │  ↳ 建议：修复建议（可点击执行的动作）                          │
  └──────────────────────────────────────────────────────────────┘
  ```
  字段：`severity`（err/warn/info）、`code`（如 `E0308`，当前缺失 → 契约版本化后由 `diag/` 错误码目录提供）、`location`（`file:line:col`，可点击跳转到编辑器对应行）、`message`、`fix`（修复建议，**可执行**）。
- **变体 · 契约版本不匹配**（为 S3 预留）：当诊断文案匹配"接口版本 N 需要 M"模式时，升级为**行动型诊断**：
  - 严重级图标改为 `--yh-warn`，左侧 3px 竖条，底 `--yh-diag-warn-bg`
  - 正文并列展示 `需要 schema_version 3` vs `产物 schema_version 2` 的对照
  - 修复建议渲染为**按钮组**：`重建种子` / `清理缓存` / `查看 yh version`
  - 附一行等宽的可复制命令（`yh version --contracts`）
- **状态**：`default` / `hover`（底加深）/ `active`（跳转到位置）/ `collapsed`（多诊断时默认折叠第 2 条起，显示"+3 条"）/ `resolved`（重新编译成功后置灰 2s 再移除）
- **尺寸**：内边距 `--yh-sp-3 --yh-sp-4`（6px 8px）；字号 `--yh-fs-md`；错误码用 `--yh-fs-2xs` 等宽 + `--yh-radius-sm` 徽标
- **可访问性**：`<ul role="list">` + 每项 `<li>`；严重级不能只靠颜色（图标 + 文本"错误"/"警告"）；位置链接是真实 `<button>`（`跳转到第 4 行第 20 列`），`Cmd/Ctrl+Click` 不劫持；修复按钮组用 `role="group" aria-label="修复建议"`

### C8 · 空态 / 错误态 / 断连态

- **用途**：三种"没有正常内容"的情况必须视觉可分。
- **三态区分**：

| 态 | 触发 | 视觉语言 | 主行动 |
|---|---|---|---|
| **空态** | 从未编译 / 无输出 | 居中，`--yh-text-muted`，1 个图标 + 1 句说明 + 1 个次要按钮 | "加载示例" |
| **错误态** | 编译失败 | 左上对齐，`--yh-err` 强调，诊断条目列表 | "跳到第一个错误" |
| **断连态** | `serverDown()` | 顶部 banner（`#5a2d2d` 底 / `#f2c4c4` 字，实测 **7.29:1**）+ 控制台内命令行代码块 | "复制启动命令" |

- **Anatomy（banner）**：`[图标] 一句话结论 → 等宽命令 → [复制] [关闭]`
- **尺寸**：banner 内边距 `--yh-sp-4 --yh-sp-7`（8px 14px）；空态容器最大宽 `420px` 居中
- **可访问性**：banner `role="alert"`（断连是需要立即知道的）；空态**不要**用 `role="alert"`（会误播报）；断连态提供**可复制**的命令文本（用户下一步就是去终端执行）

### C9 · 分隔拖拽条

- **用途**：调整左右栏宽度（15%~75%）。
- **Anatomy**：`5px 竖条`，`cursor: col-resize`
- **状态**：`default`（`--yh-border`）/ `hover`（`--yh-surface-hover`）/ `dragging`（`--yh-surface-hover` + 相邻面板 `user-select:none`）/ `focus`（`outline: 2px solid var(--yh-focus-ring)`）
- **尺寸**：宽 `--yh-w-splitter:5px`；**热区**扩到 11px（`::before` 伪元素左右各溢出 3px），视觉仍 5px
- **可访问性**：`role="separator" aria-orientation="vertical" aria-valuenow="46" aria-valuemin="15" aria-valuemax="75" tabindex="0"`；`ArrowLeft/ArrowRight` 每次 ±2%，`Shift+Arrow` ±10%，`Home/End` 到边界；`aria-valuetext="左栏 46%"`

---

## 6. 状态矩阵（现有页面最缺的部分）

五个全局状态 × 四个区域。**这张表是本规范的核心交付**：任何状态变化都必须同时更新这四格，不允许"只改一个地方"。

| 全局状态 | 状态点（C4） | 汇编区（C5） | 控制台（C6） | Run 按钮（C3） |
|---|---|---|---|---|
| **① 编译中**<br>`compiling` | `◐` `--yh-dot-busy-bg` 旋转<br>`aria-label="正在编译"` | **保留上一版汇编**（不清空、不置灰）<br>右上角叠加 `1px` 顶部进度条（`--yh-accent`，`indeterminate`）<br>行号槽不变 | 保持上次内容不变<br>`aria-busy="true"`<br>提示位显示"编译中…" | **`disabled`** + 文字改"编译中…"<br>`aria-busy="true"` |
| **② 成功**<br>`ok` | `✓` `--yh-dot-ok-bg`<br>`title="编译成功（退出码 0）"` | 替换为新汇编，行号重排<br>滚动位置**保留**（不跳回顶部） | 若上次有诊断 → 替换为"编译成功，无诊断"<br>程序输出追加在下方 | 正常可用<br>文字"▶ Run" |
| **③ 失败**<br>`err`（代码问题） | `✕` `--yh-dot-err-bg`<br>`title="编译失败（退出码 1）"` | **保留上一版汇编** + 顶部一条 `--yh-diag-err-bg` 横条："汇编未更新：源码编译失败"<br>错误行在编辑器侧标红（若位置可解析） | 渲染诊断条目列表（C7）<br>段标题"编译诊断"用 `--yh-err`<br>提示位"编译失败 · 1 个错误" | 正常可用（可重试）<br>**不 disabled** |
| **④ 服务器不可达**<br>`serverDown` | `·` 但底改 `--yh-err` 描边（虚线环）<br>`title="本地服务器未响应"`<br>**与 ③ 视觉可分** | 全部替换为断连占位（居中，`--yh-text-muted`）<br>**不保留**旧汇编（避免误导：旧数据不可信） | 顶部 banner（C8）<br>控制台内：错误摘要 + **可复制**的启动命令<br>提示位"连接失败" | **`disabled`**（无后端可调）<br>`title="服务器未启动"` |
| **⑤ 契约版本不匹配**<br>`contract-mismatch` | `!` `--yh-warn` 底（**第四种颜色**，不是 err 的红）<br>`title="产物契约版本不匹配"` | 顶部 `--yh-diag-warn-bg` 横条：<br>`需要 schema_version 3 · 产物为 2`<br>汇编区显示空态 + "无法读取产物" | 行动型诊断条目（C7 变体）：<br>版本对照 + 修复按钮组（重建种子/清缓存/查看版本）+ 可复制命令 | 正常可用，但 `title` 提示"需先修复契约版本"<br>点击后诊断区高亮脉冲 1 次 |

**跨状态的三个不变式**：

1. **汇编区永远不"变白"**。除了 ④ 断连，任何状态都保留上一版可见内容（编译器工具的用户需要对比"改之前长什么样"）。这是 godbolt 的核心体验。
2. **Run 按钮的 `disabled` 只表达"现在点了没用"**，不表达"出错了"。所以只有 ① 和 ④ 禁用；③ 失败**必须**可点（用户要重试）。
3. **颜色不能是唯一信号**。⑤ 与 ③ 都是"出问题了"，靠 `warn` vs `err` 色相 + 符号 `!` vs `✕` + 是否提供修复按钮三重区分。

---

## 7. 落地迁移路径

目标：从现有 648 行单文件迁到 token 化，**零构建依赖、零像素跳变、可分 5 次提交**。

### 第 1 步 · 插入 token 层（+约 120 行，纯新增，不改任何现有规则）

在现有 `:root` 之前插入 `--yh-legacy-*`（考古层），在 `:root` 内追加 L1/L2/L3 token，然后追加 L0 兼容桥：

```css
:root{
  /* 考古层：只存历史值 */
  --yh-legacy-bg:#282c34; --yh-legacy-bg-panel:#21252b; /* …共 18 个… */
  /* L1 / L2 / L3 */
  --yh-surface-editor:#282c34; /* … */
  /* L0 兼容桥 */
  --bg: var(--yh-legacy-bg); /* … */
}
```

**验收**：`git diff` 只有 `+`，页面截图与改前 **逐像素相同**。方法：

```bash
# 改前
screencapture -x before.png   # 或 puppeteer/playwright 截图
# 改后
screencapture -x after.png
compare -metric AE before.png after.png null:   # ImageMagick，应输出 0
```

### 第 2 步 · 收编硬编码色值（约 12 处替换，零视觉变化）

现有 CSS 里有 12 个"游离 hex"，值本身是对的，只是没进 token。逐个换成 token：

| 位置 | 现值 | 换成 |
|---|---|---|
| `.pane-title` color | `#c8cdd6` | `var(--yh-text-strong)` |
| `select, input` border | `#33363d` | `var(--yh-border-strong)` |
| `#btn-run:hover` bg | `#38b84f` | `var(--yh-btn-primary-bg-hover)` |
| `#status-dot` bg | `#3a3f4b` | `var(--yh-dot-idle-bg)` |
| `#split:hover` bg | `#3a3f4b` | `var(--yh-surface-hover)` |
| `#banner` bg / color | `#5a2d2d` / `#f2c4c4` | `var(--yh-diag-err-bg)` 实色 / `var(--yh-text-strong)` |
| `#active-line` bg | `rgba(255,255,255,.045)` | `var(--yh-editor-line-active)`（`#32353d`，实色等价） |
| `textarea.code` caret | `#f0f0f0` | `var(--yh-editor-caret)` |
| `::selection` | `rgba(97,175,239,.25)` | `var(--yh-editor-sel)` |
| `.o-out` | `#b5bd68` | `var(--yh-console-out)` |
| `.o-sec` | `#c8cdd6` | `var(--yh-text-strong)` |
| `#btn-run` color | `#fff` | `var(--yh-btn-primary-fg)` |

**验收**：仍然 `AE = 0`（`--yh-editor-line-active: #32353d` 是 `rgba(255,255,255,.045)` 叠在 `#282c34` 上的精确混合结果，已算过）。

### 第 3 步 · 补第四态与状态机（约 +45 行 JS，+6 行 CSS）

```js
// 现有 setDot 只有 "" | "ok" | "err"，扩为四态
const DOT = {
  idle:      { sym:'·', cls:'',        label:'尚未编译' },
  compiling: { sym:'◐', cls:'busy',    label:'正在编译' },
  ok:        { sym:'✓', cls:'ok',      label:'编译成功' },
  err:       { sym:'✕', cls:'err',     label:'编译失败' },
};
function setDot(state, detail) {
  const d = DOT[state] || DOT.idle;
  dot.className = d.cls;
  dot.textContent = d.sym;
  dot.setAttribute('aria-label', detail ? `${d.label}：${detail}` : d.label);
  dot.title = detail || d.label;
}
```

在 `compileAsm()` 开头 `setDot('compiling')`，`runCode()` 开头同样；`scheduleCompile()` 里**不**设 `compiling`（防抖期间还没发请求，设了会闪）。

CSS 只需：

```css
#status-dot.busy { background: var(--yh-dot-busy-bg); }
#status-dot.busy { animation: yh-spin 900ms linear infinite; }
@media (prefers-reduced-motion: reduce) { #status-dot.busy { animation: none; } }
```

### 第 4 步 · 诊断结构化（约 +60 行 JS）

新增 `parseDiag(stderr)`，把 `file:line:col: 严重级: 文案` 解析成对象数组，再渲染 C7：

```js
// 实测真实输出格式：src/main.yh:4:20: 错误: 不能把指针赋给非指针（用 .to_type）
const DIAG_RE = /^(.+?):(\d+)(?::(\d+))?:\s*(错误|警告|提示):\s*(.*)$/;
function parseDiag(text) {
  const out = [];
  for (const line of text.split('\n')) {
    const m = line.match(DIAG_RE);
    if (!m) { if (line.trim()) out.push({ raw: line }); continue; }
    const [, file, ln, col, sev, msg] = m;
    // 文案末尾的全角括号视为修复建议
    const fix = (msg.match(/（([^）]+)）$/) || [])[1] || null;
    out.push({ file, line:+ln, col:col?+col:null, severity:
      sev === '错误' ? 'err' : sev === '警告' ? 'warn' : 'info',
      message: fix ? msg.replace(/（[^）]+）$/, '').trim() : msg, fix });
  }
  return out;
}
```

契约版本化落地后，只需在 `parseDiag` 里加一条分支识别"接口版本 N 需要 M"，升级为 C7 变体。**这是预留的关键**：结构化解析先落地，UI 升级是纯增量。

### 第 5 步 · 删兼容桥（-18 行）

确认所有使用点已迁到 `--yh-*` 后删除 L0 与 `--yh-legacy-*`。此后 `--text-dim` 等旧名不再存在，防止回潮。

### 迁移改动量汇总

| 类别 | 行数量级 |
|---|---|
| CSS 新增（token 层） | +120 行 |
| CSS 硬编码替换 | 12 处（约 12 行改动） |
| CSS 组件类新增（诊断条目、四态、空态） | +90 行 |
| JS 状态机（四态） | +45 行 |
| JS 诊断解析与渲染 | +60 行 |
| HTML 结构（诊断列表容器、banner 按钮组） | +15 行 |
| **合计** | **约 +330 行 / 改 12 行 / 删 18 行** |

648 行 → 约 970 行，仍是一个单文件、双击可用、无任何外部请求的页面。

---

## 8. 可访问性与键盘

### 8.1 焦点顺序

```
1. 左栏 pane-header：示例下拉 → 复制 → Run
2. 源码 textarea
3. 分隔条（tabindex=0）
4. 右栏 pane-header：编译器下拉 → 路径 → 选项 → 复制 → 状态点（tabindex=0，可读 title）
5. 汇编区（tabindex=0，可键盘滚动）
6. 控制台 header：清空 → 收起
7. 控制台内容（role=log）
```

规则：DOM 顺序 = 视觉顺序 = Tab 顺序，**不用 `tabindex>0` 重排**。跳跃用 `skip link`（"跳到编辑器" / "跳到输出"）而非改 tabindex。

### 8.2 键盘映射

| 快捷键 | 动作 | 现状 |
|---|---|---|
| `Cmd/Ctrl+Enter` | 编译并运行 | 已有 |
| `Cmd/Ctrl+S` | 保存（拦截浏览器对话框） | 已有 |
| `Tab` / `Shift+Tab` | 缩进 / 反缩进（多行选区同时处理） | 部分（现有仅单点插入） |
| `Esc` | 收起控制台 / 关闭 banner | **新增** |
| `Cmd/Ctrl+K` | 聚焦编译器路径输入 | **新增** |
| `Cmd/Ctrl+Shift+P` | 循环主题 暗/亮 | **新增** |
| `Cmd/Ctrl+1` / `+2` | 焦点跳到编辑器 / 汇编区 | **新增** |
| `F8` / `Shift+F8` | 跳到下/上一个诊断位置 | **新增**（诊断结构化后才有意义） |
| `←/→`（焦点在分隔条） | 调整栏宽 ±2%（`Shift` ±10%） | **新增** |

所有快捷键必须在 UI 上有发现路径（按钮 `title` 里写明，例如 `▶ Run` 的 title 已含 `Ctrl/Cmd+Enter`）。

### 8.3 `aria-live` 策略

| 区域 | 属性 | 理由 |
|---|---|---|
| 控制台 `#console-body` | `role="log" aria-live="polite" aria-relevant="additions"` | 输出是追加流，不打断输入 |
| 状态点 `#status-dot` | `role="status" aria-live="polite"` | 状态变化需要播报，但不必打断 |
| 断连 banner `#banner` | `role="alert"` | 环境故障，需要立即知道 |
| 诊断列表容器 | `aria-live="polite"` **但**只在"错误数变化"时播报摘要（"3 个错误"），不逐条播报 | 逐条播报会淹没用户 |
| 空态 | 无 live 属性 | 静态内容，播报是噪音 |

**禁止**在控制台用 `aria-live="assertive"`：用户在编辑时每次自动编译都会被朗读打断。

### 8.4 动效降级

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
  #status-dot.busy { animation: none; }        /* 旋转改为静态 ◐ */
}
```

降级原则：**信息不丢失**。旋转指示器停了，但 `◐` 符号 + `aria-label="正在编译"` 仍在；进度条停了，但"编译中…"文字仍在。

### 8.5 对比度底线

| 类别 | 底线 | 本规范达成情况 |
|---|---|---|
| 正文 / 代码 / 语法色（亮色） | `≥4.5:1` | ✓ 17/17 达标（最低 4.62:1 行号） |
| 正文 / 代码 / 语法色（暗色） | `≥4.5:1` | 12/18 达标，6 项入债务表 D1–D6，提供 `data-contrast="aa"` 修复档 |
| 焦点环 | `≥3:1` | ✓ 暗 7.13:1 / 亮 5.19:1 |
| 非文本 UI 边界（输入框） | `≥3:1` | 亮 ✓ 3.40:1；暗 1.39:1（记入 §4.6，靠焦点环补偿） |
| 状态色可辨识 | 不能只靠色相 | ✓ 每态配独立符号 `· ◐ ✓ ✕ !` |

### 8.6 其他

- **语言**：`<html lang="zh-CN">`（现有已有）；诊断文案含英文标识符时用 `<code lang="en">` 包裹。
- **缩放**：`font-size` 全部用绝对 px（不用 `rem`），因为三层叠加编辑器的 `LINE_H=21` 是像素硬约束，`rem` 缩放会导致行号与高亮错位。代价是用户浏览器缩放不生效 —— 补偿方案：提供 `Cmd/Ctrl +/-` 调整 `--yh-fs-lg` 与 `--yh-lh-code`（两者同步缩放，比例锁定 `1.5`）。
- **高对比模式**：`@media (forced-colors: active)` 下所有边框改用 `CanvasText`，背景改 `Canvas`，状态点保留符号。

---

## 9. 附录 · 现有 CSS 变量 → 新 token 映射表

| 现有 | 新 token | 值是否变化 |
|---|---|---|
| `--bg` | `--yh-surface-editor` | 否（`#282c34`） |
| `--bg-panel` | `--yh-surface-panel` | 否（`#21252b`） |
| `--bg-input` | `--yh-surface-input` | 否（`#1b1d23`） |
| `--border` | `--yh-border` | 否（`#181a1f`） |
| `--text` | `--yh-text` | 否（`#abb2bf`） |
| `--text-dim` | `--yh-text-muted` | **是**（`#6b7280` → `#8b93a3`，2.90 → 4.53，修 D2） |
| `--gutter-text` | `--yh-text-gutter` | **是**（`#495162` → `#6e7788`，1.76 → 3.10，修 D1） |
| `--kw` | `--yh-syn-kw` | 否（`#e06c75`） |
| `--num` | `--yh-syn-num` | 否（`#d19a66`） |
| `--str` | `--yh-syn-str` | 否（`#98c379`） |
| `--com` | `--yh-syn-com` | 否（`#5c6370`，AA 档才改） |
| `--fn` | `--yh-syn-fn` | 否（`#61afef`） |
| `--label` | `--yh-syn-label` | 否（`#d7dae0`） |
| `--dir` | `--yh-syn-dir` | 否（`#c678dd`） |
| `--ok` | `--yh-ok` / `--yh-ok-solid` | 否（`#2ea043`） |
| `--err` | `--yh-err` | 否（`#f14c4c`） |
| `--mono` | `--yh-font-mono` | 否（同字体栈） |

**只有 2 个变量在迁移时值发生变化**（`--text-dim`、`--gutter-text`），且都是"修 bug"性质。其余 15 个逐字节等价 —— 这就是"换 token 后像素级基本一致"的可验证保证。

---

## 10. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-24 | 1.0.0 | 首版。基于 `tools/yh-explorer.html`（648 行）现状测绘；新增四层 token、亮色主题、四态状态点、诊断条目组件、五态×四区域状态矩阵、迁移五步路径。所有对比度数字为 WCAG 2.1 公式实算。 |
