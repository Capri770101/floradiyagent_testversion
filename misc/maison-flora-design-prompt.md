# Maison Flora — 轻奢花店 UI 设计提示词文档

> 一套可直接复用的「高级轻奢」花店视觉规范。既可给设计师/前端当设计规范，也可直接当 AI 文生图、代码生成、页面重构的提示词使用。
> 风格代号：**Maison（法式轻奢）** · 场景：**花店 / 花艺电商**

---

## 1. 设计定位（Style Positioning）

**一句话风格**：安静、克制、有材质感的轻奢花艺美学——像一间精品酒店大堂，而非喧闹的花市。

**关键词（可直接用作 tag / mood board）**
`luxury floral` · `quiet elegance` · `minimalist chic` · `editorial` · `warm ivory` · `champagne gold` · `serif headline` · `fine hairline` · `generous whitespace` · `French atelier`

**风格对立面（避免）**：彩虹配色、圆滚滚大圆角、重投影、卡通插画、emoji 装饰、粗黑体大字、信息密集。

---

## 2. 核心色板（Color Palette）

| 角色 | 色名 | HEX | 用途 |
|---|---|---|---|
| 主色 Primary | Champagne Gold 香槟金 | `#B5985A` | 主按钮、强调短线、eyebrow 标签、价格 |
| 主色暗 | Deep Bronze 深古铜 | `#6B5630` | 金色文字（浅底上）、叶茎线 |
| 强调 Accent | Burgundy 酒红 | `#722F37` | Limited / 稀缺标记、花蕊点缀 |
| 文字主 | Ink 墨黑 | `#1A1A1A` | 标题、正文、导航 |
| 文字次 | Slate 石板灰 | `#6B6B6B` | 辅助说明 |
| 文字弱 | Stone 石灰 | `#8B8680` | 标签、注释 |
| 页面底 | Ivory 象牙白 | `#FAF8F5` | 全局背景（带暖意） |
| 卡片底 | White 纯白 | `#FFFFFF` | 卡片、表单 |
| 柔和底 | Sand 砂色 | `#F0EBE3` | subtle 按钮、hover、画布区 |
| 描边 | Stone | `#D4CFC6` | 0.5px 极细线 |

> 配色纪律：**低饱和 + 暖调**。金色只做点缀，绝不大面积铺。整屏颜色不超过 4 个。

---

## 3. 字体系统（Typography）

| 用途 | 字体 | 字重 | 字号 |
|---|---|---|---|
| 大标题 Display | Cormorant Garamond（衬线） | 400 | 36–58px |
| 区块标题 H2 | Cormorant Garamond（衬线） | 400 | 22–38px |
| 产品名 | Cormorant Garamond（衬线） | 400 | 22–23px |
| 正文 Body | Inter（无衬线） | 400 | 14px |
| 辅助文字 | Inter（无衬线） | 400 | 13px |
| Eyebrow 小标签 | Inter（无衬线） | 500 | 10px，字间距 3px，金色 |
| 中文衬线兜底 | 思源宋体 / Source Han Serif | 400 | — |

**原则**：衬线字体自带分量，**永远不加粗（不用 600/700）**。全站只用两个字重：400 与 500。

---

## 4. 设计原则（Design Tokens / Rules）

| 维度 | 规则 |
|---|---|
| 圆角 Radius | **2px / 最大 4px**，近直角，拒绝圆润 |
| 描边 Border | **永远 0.5px**，颜色 `#D4CFC6`，绝不用 1px+ |
| 字重 Weight | 仅 400 / 500，无 bold |
| 留白 Spacing | 区块间距 ≥ 48px，元素间距 ≥ 20px，宁多勿少 |
| 分隔 Divider | 用 40px 金色短线，而非整条长线 |
| 阴影 Shadow | **无投影**（flat）。层次靠留白与描边，不靠阴影 |
| 图片 | 优先真实花卉摄影 + 留白；或极简金线 SVG 花卉插画 |

---

## 5. 组件规范（Components）

- **主按钮**：墨黑实底 + 象牙白字 / 或香槟金实底。小圆角 2px，字间距 1px，无投影。
- **次按钮**：白底 + 0.5px 墨黑描边；hover 转金色描边。
- **柔和按钮**：砂色底 + 深古铜字（用于"加入""查看"等次级动作）。
- **产品卡**：白底 + 0.5px 描边，上部花卉图（16:10 或 1:1），图下 eyebrow → 衬线产品名 → 灰色描述 → 价格 + 加入按钮。
- **稀缺标签**：贴角小标。`Premium` 金色实底；`Limited` 酒红描边；`New` 砂色底。
- **输入框**：白底 + 0.5px 描边，聚焦时左侧出现 1px 金色竖线，不放大边框。
- **金句区**：居中衬线大字 + 下方 letter-spacing 2px 的署名小字。

---

## 6. H5 移动端适配要点

- 视口锁定 `max-width: 390px`，整屏单栏瀑布流。
- 顶部加状态栏（`9:41 / 5G`）+ `≡` 菜单，模拟原生 App。
- 产品卡改为**整屏宽度**，稀缺标签**贴角**。
- 底部加**吸底结算栏**（墨黑 + 香槟金 CTA），滑动常驻。
- 触控目标 ≥ 44px，按钮内边距加大。

---

## 7. 花店场景应用（Flower Shop Specifics）

**品牌命名**：`MAISON·FLORA`（衬线 logo）+ 法文副标 `Atelier de Fleurs`（花艺工坊）。
**产品命名**：诗意路线，如 `绯红絮语 / 素白之约 / 金晖礼赞`，配「厄瓜多尔红玫瑰·11 枝手扎」式材质说明。
**文案调性**：克制、有仪式感。例：「真正的奢侈，是把时间，温柔地交还给一朵花。」
**品类话术**：Premium（主推）/ Limited（限量）/ New（新品），对应金色 / 酒红描边 / 砂色标签。

---

## 8. 可复用提示词（Reusable Prompts）

### 8.1 AI 文生图 —  Hero 主视觉花卉（极简金线风，匹配本规范）

```
Minimalist single-line floral illustration, elegant rose in full bloom,
delicate champagne gold thin strokes on warm ivory background (#FAF8F5),
subtle bronze stem lines, burgundy accent center, editorial luxury style,
negative space, fine hairline art, no shadow, no fill color, serene and refined
```

### 8.2 AI 文生图 — 真实花卉产品摄影（电商主图）

```
Luxury product photography of a hand-tied bouquet, Ecuadorian red roses,
soft natural light, warm ivory background, generous negative space,
champagne gold ribbon, high-end editorial floral campaign, muted tones,
minimalist composition, 8k, sharp focus
```

### 8.3 给设计工具 / 前端的自然语言 brief

```
设计一套轻奢花店 H5 页面。风格：法式极简、安静克制、高级感。
配色用象牙白底 #FAF8F5 + 香槟金主色 #B5985A + 酒红强调 #722F37 + 墨黑文字 #1A1A1A。
标题用衬线字体（Cormorant Garamond），正文用无衬线（Inter）。
圆角仅 2px，描边统一 0.5px 极细线，全站无投影，大量留白。
包含：状态栏+导航、衬线大标题 Hero、当季臻选单栏产品卡（贴角稀缺标签）、
居中金句区、底部吸底结算栏。品牌名 MAISON·FLORA。
```

### 8.4 给代码生成的 brief（可直接丢给 AI 写前端）

```
用 HTML + CSS（可用 Tailwind）做一个移动端 H5 花店首页，风格为轻奢极简。
设计 token：背景 #FAF8F5，主色金 #B5985A，强调酒红 #722F37，文字 #1A1A1A；
字体 Cormorant Garamond（标题）+ Inter（正文），均通过 Google Fonts 引入；
圆角 2px，边框 0.5px #D4CFC6，无 box-shadow，留白充足。
结构：状态栏、顶栏 MAISON·FLORA + 菜单、Hero 衬线大标题+金线花卉 SVG、
当季臻选 3 张全宽产品卡（含 Premium/Limited/New 贴角标签）、金句区、页脚、吸底结算栏。
花卉图用内联 SVG 极简金线插画，不依赖外部图片。
```

---

## 9. 完整 CSS 变量（落地即用）

```css
:root {
  --bg-page: #FAF8F5;
  --bg-card: #FFFFFF;
  --bg-subtle: #F0EBE3;
  --border: #D4CFC6;
  --text-primary: #1A1A1A;
  --text-secondary: #6B6B6B;
  --text-muted: #8B8680;
  --gold: #B5985A;
  --gold-dark: #6B5630;
  --gold-light: #F0EBE3;
  --burgundy: #722F37;
  --radius-sm: 2px;
  --radius-md: 4px;
  --font-serif: 'Cormorant Garamond', Georgia, serif;
  --font-sans: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}
```

---

*文档版本 Maison v1.0 · 适用于花店 / 花艺 / 礼品电商的轻奢视觉统一。*
