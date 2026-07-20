# SuperVideoGenerator 前端风格约束

> 最后更新：2026-07-17（品牌标改为圆软小夜枭：圆耳圆头、取景器四角、无齿孔颏条）  
> 视觉语言：**暗房胶片**（Darkroom Film）— AI 视频创作工作流的取景器美学。

本文档是 `apps/web` 的唯一前端视觉与交互约束来源。新增页面、组件或样式变更须符合本文；Agent 开发时参见 `.cursor/rules/frontend-style.mdc`。

---

## 1. 设计定位

| 维度 | 约束 |
|------|------|
| **产品** | AI 多 Agent 视频生成工作台 |
| **受众** | 创作者、导演、内容策划 — 熟悉分镜、胶片、剪辑术语 |
| **页面职责** | 在深色工作环境中清晰呈现资产、分镜与生成状态，减少认知负荷 |
| **签名元素** | 顶栏**胶片齿孔**、详情面板**取景器顶光条**、运行态**录制脉冲**、冷启动**取景器胶片条**、品牌标**圆软猫头鹰镜头眼**（取景器四角 + 珊瑚瞳；无齿孔颏条） |

避免套用通用 AI 界面模板（暖奶油底 + 衬线标题、纯黑 + 酸性绿、报纸式大编号）。结构元素（分区编号、装饰线）须承载真实信息，而非纯装饰。

---

## 2. 设计令牌（Design Tokens）

**唯一来源**：`apps/web/src/styles/design-system.css`  
**详情页扩展**：`apps/web/src/styles/asset-detail.css`

### 2.1 色板

| 名称 | CSS 变量 | 用途 |
|------|----------|------|
| 深空 | `--svf-void` `#080a0f` | 预览区、媒体底 |
| 面板 | `--svf-surface` / `--svf-surface-2` | 卡片、区块背景 |
| 框线 | `--svf-frame` `#2a3347` | 边框、分隔 |
| **取景器珊瑚** | `--svf-accent` `#e0634a` | 主操作、类型徽章、焦点 |
| 胶片琥珀 | `--svf-gold` `#c9a227` | 警告、次要强调 |
| 成功 | `--svf-success` `#4dbb8a` | 完成状态 |
| 危险 | `--svf-danger` `#e05252` | 错误、删除 |
| 信息 | `--svf-info` `#6b9fd4` | 链接、信息 chip |
| 正文 | `--svf-text` / `--svf-text-soft` | 主/次文本 |
| 弱化 | `--svf-muted` `#8e9aaf` | 标签、说明 |

**禁止**在组件内硬编码 `#1d9bf0` 等外来 accent；链接与强调统一 `--svf-accent` 或 `--svf-info`。

### 2.2 字体

| 角色 | 变量 | 字体 | 用途 |
|------|------|------|------|
| Display | `--svf-font-display` | Newsreader | 页面/详情标题，**克制使用** |
| Body | `--svf-font-body` | Outfit | 正文、按钮、表单 |
| Mono | `--svf-font-mono` | IBM Plex Mono | 区块眉标、ID、时间码、状态 |

区块标题（section eyebrow）统一：**0.62–0.68rem · uppercase · letter-spacing 0.12–0.14em · mono · muted/accent**。

### 2.3 间距与圆角

- 间距：`--svf-space-xs` ~ `--svf-space-xl`
- 圆角：`--svf-radius-sm` (6px) 控件 · `--svf-radius` (10px) 面板 · `--svf-radius-lg` (14px) 大卡片

### 2.4 阴影与光晕

- 面板：`--svf-shadow-md`
- 主操作 hover：`--svf-shadow-accent`（珊瑚光晕）

---

## 3. 组件层级

```
apps/web/src/styles/
  design-system.css    ← 全局令牌 + 按钮/顶栏/状态
  asset-detail.css     ← 详情 Modal/Drawer + 二次生成
  agent-workbench.css  ← Agent 工作台专用（含工具 Schema 详情侧栏 `.aw-tool-detail-panel`）
  editor-studio.css    ← Edit Studio 专用
  splash-screen.css    ← 冷启动加载页（取景器 + 胶片条）

apps/web/src/components/boot/
  AppBootGate.tsx          ← 启动门闸，协调最短展示与退场
  AppSplashScreen.tsx      ← 全屏加载动画

apps/desktop/
  splash-boot.html         ← Electron 冷启动胶片页（与 Web 首帧一致）

apps/web/src/components/assetDetail/
  AssetDetailShell.tsx     ← Modal 遮罩 + 面板
  AssetDetailHeader.tsx    ← 类型徽章 + 标题 + actions
  AssetDetailSection.tsx   ← 取景器卡片区块（可选 `actions`，如提示词旁小眼睛）
  ResolvedPromptPreview.tsx ← 实际生成提示词预览弹层
```

**规则**：新建详情类 UI 必须复用 `assetDetail/*` 壳层，不得再复制 overlay/panel 结构。`AssetDetailSection` 可通过 `actions` 在标题行右侧挂轻量操作（如 `ResolvedPromptPreview`）。

### 3.1 冷启动加载页

- **入口**：`AppBootGate` 包裹应用根；`index.html` 内联 `#svf-inline-boot` 全尺寸胶片占位，React 绘制后移除；Electron 桌面壳通过 [`apps/desktop/splash-boot.html`](apps/desktop/splash-boot.html) 展示同款动画（**禁止**再出现「正在启动…」文案页）。
- **视觉**：齿孔顶栏漂移、大取景器四角框（宽 `min(78vw, 36rem)`）、框内滚动胶片条 + 珊瑚扫描线 + 颗粒层；标题 Newsreader 2rem + 珊瑚脉冲点。
- **文案**：`common.splash.*`（眉标 / 标语 / 三阶段状态轮播）；导片条显示 0–100 进度。
- **时序**：最短约 1.9s + 字体就绪后淡出（~0.6s）；`prefers-reduced-motion` 关闭动画。
- **样式**：`splash-screen.css` 与 `splash-boot.html` 内联 CSS 共用同一套尺寸数值，仅使用 `--svf-*` 令牌（HTML 占位允许硬编码回退色）。

### 3.2 品牌标（Favicon / App Icon · 圆软小夜枭）

- **主题**：仅猫头鹰头部主体 — **圆耳 + 圆头**、镜头眼（更大珊瑚瞳 + 高光）、钝椭圆喙、轻腮红、取景器四角（圆角端点）；**无**颏下齿孔条；**不含**大圆角应用底板装饰层。
- **Web**：[`favicon.svg`](../../../apps/web/public/favicon.svg)、[`icon.svg`](../../../apps/web/public/icon.svg)、[`icon.png`](../../../apps/web/public/icon.png) / [`favicon-32.png`](../../../apps/web/public/favicon-32.png)；`index.html` 引用 SVG + PNG + `theme-color=#080a0f`。
- **桌面**：[`apps/desktop/icon.ico`](../../../apps/desktop/icon.ico) + [`icon.png`](../../../apps/desktop/icon.png) + 源图 [`icon-source.png`](../../../apps/desktop/icon-source.png)；Electron `BrowserWindow({ icon })`；`scripts/update_desktop_shortcut.ps1` 写入桌面 `.lnk`。
- **再生**：`python scripts/export_owl_icon.py`（委托 `scripts/export_owl_icon.mjs` + `apps/web` 的 sharp，从 `icon.svg` 栅格化方正深空底 PNG/ICO）。
- **色值**：`#080a0f` / `#121826` / `#1a2233` / `#2a3347` / `#3d465c` / `#8e9aaf` / `#e0634a` / `#f4d4cc`。

---

## 4. 详情页结构

### 4.1 Modal（图文 / 媒体资产）

```
┌─ asset-editor-overlay ─────────────────────────┐
│  ┌─ asset-detail-panel ───────────────────────┐ │
│  │ ▔▔ 取景器顶光渐变线 ▔▔                    │ │
│  │ [TYPE BADGE]  标题 (Newsreader)    [actions]│ │
│  │ ─────────────────────────────────────────  │ │
│  │ ┌ asset-editor-form-body（可滚动）───────┐  │ │
│  │ │ ┌ asset-detail-section ───────────────┐ │  │ │
│  │ │ │ SECTION EYEBROW (mono)            │ │  │ │
│  │ │ │ 字段…                             │ │  │ │
│  │ │ └───────────────────────────────────┘ │  │ │
│  │ └───────────────────────────────────────┘  │ │
│  │ ── asset-editor-footer（固定底栏）──────  │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- 宽度：`min(720px, 100%)`
- **只读 Modal**（`ImageTextAssetDetailModal` / `MediaAssetDetailModal`）：`AssetDetailShell` + `.asset-detail-body` **独立纵向滚动**（顶栏 sticky，内容超出时可下拉）
- **编辑 Modal**（`ImageTextAssetEditor`）：复用 `AssetDetailShell` + `AssetDetailHeader` + `AssetDetailSection`；正文区 `.asset-editor-form-body` 独立滚动，底栏 `.asset-editor-footer` 固定
- **底栏样式**：仅 `.asset-editor-panel.asset-detail-panel > .asset-editor-footer`（直接子元素）可加底栏渐变，且须用 `--panel-bg` 等主题令牌；禁止硬编码深色 `rgba(8,10,15,…)`，禁止后代选择器以免嵌套弹窗误吃样式
- **嵌套新建弹窗**（如分镜抽屉内 `CreateTextAssetDialog`）：须 `createPortal(..., document.body)`，勿作为 `.asset-detail-panel` 的 DOM 后代
- **画面 / 视频片段**（`frame` / `video_clip`）：创建、编辑、详情五块——名称、摘要、关联资产、提示词（`image_prompt` / `video_prompt`）、备注（`notes`，AI 编排自用，不进入提示词）；角色/空镜/物品仍用完整字段
- **关联资产选择**（`AssetRefPicker` / `AssetVisualSelect`）：接触印样交互——分类 pill Tab + 缩略图/名称/摘要卡片网格；已选落在顶部胶片条（序号 + 预览 + 名称），再点取消；子镜 frame / video_clip **多选**挂接复用同一组件，每条可编 `start_ms`/`end_ms`；`allowDuplicateSelection` 时同一资产可多次挂接（卡片显示 ×N，胶片条按次移除）。`video_clip` 无可用预览（空 URL / 非法 / 加载失败）时不渲染预览区与破图，改为**纯文案卡片**（左侧胶片齿孔轨 + Newsreader 标题，`hideEmptyPreview`）；有 mp4 等视频 URL 时用 `<video preload="metadata">` 而非 `<img>`。令牌与选中态用 `--svf-accent` / `--svf-success`，禁止外来蓝色勾选风格
- **关联资产展示**（`LinkedAssetRefsSection`）：详情「关联资产」以缩略图卡片展示（优先 `variant_refs` 指定子形象图，否则主图）；可点跳转
- **子形象挂接**：`content.variant_refs` 为 `{ text_asset_id: variant_id }`；`AssetRefPicker` 在传入 `onVariantRefsChange` 时，对已选且含多个 `variants` 的资产展示子形象 chip 条；胶片条预览跟随所选子形象
- **形象变体编辑**：角色/道具编辑弹窗可「添加子形象」/「删除」（主形象不可删）；类型可选 expression/pose/action/costume/other
- **剧本详情抽屉**（`ScriptDetailDrawer`）：关系图/谱系点击剧本节点时右侧滑出，展示正文全文、统计与剧情段落；当前工作台同剧本时可编辑
- **看板缩略图 URL**：`item.preview` 多为摘要文案；缩略图须用 `preview_url` 或 `images[]/media[].url`（`pickBoardMediaPreviewUrl` / `looksLikeMediaUrl`），禁止把中文 `preview` 当 `img.src`；`AssetImagePreview` 加载失败须回退暗房占位，禁止露出浏览器破图图标
- **子镜时段条**（`SubShotMediaLane`）：在子镜区间上双轨展示多画面（珊瑚）/ 多视频（信息蓝）占用块，点选高亮对应槽位
- **生图提示词**区块（角色/空镜/物品）：section 标题仅出现一次；锁定开关在 `.asset-prompt-toolbar`；正向/负向用 mono 眉标 `正向` / `负向`，禁止重复「生图 Prompt」标签
- 顶栏操作：`asset-detail-actions`，二次生成在关闭/编辑之前；**控件统一高度 2rem**，与 `btn-sm` / `asset-gen-badge--inline` 对齐
- 顶栏结构：`.asset-detail-header__top`（身份 + 按钮）+ 可选 `.asset-detail-header__status`（报错/成功**独占全宽第二行**）
- 标题：`.asset-detail-header__title` 单行省略，禁止挤成竖排字
- `video_clip`：**仅当存在真实媒体 URL**（`looksLikeMediaUrl`）时展示「关联视频」；文案摘要 preview 不得当视频
- 图片详情：`AssetImagePreview`（`enableLightbox` / `size=detail`）点击打开 `AssetImageLightbox` 大图预览（Esc / 遮罩关闭）
- 区块：默认 `asset-detail-section` 卡片；元数据 chip 区可用 `asset-detail-section--flush`

### 4.2 Drawer（分镜详情 · 镜内多轨，2026-07-12）

- 复用 `asset-detail-section` 与 section 标题样式
- **迷你时间轴**：`.shot-mini-timeline` — 配音轨（蓝）+ 画面轨（珊瑚）段块；选中态 `is-selected` 与下方卡片联动
- **分段卡片**：`.shot-segment-card` — 配音幕 `.shot-voice-act-card`、画面 `.shot-visual-card`（与剧本 frame 资产 1:1）；编辑表单 `.shot-segment-editor`
- 二次生成：按段内嵌 `AssetRegenerateButton`（`layout="compact"`），不再使用整镜 `AssetRegeneratePanel`
- 抽屉动画：`shot-drawer-in`；`prefers-reduced-motion` 时禁用
- **可调宽右侧抽屉**：左缘 `.svf-drawer-resize-edge` + `useResizableDrawerWidth`（分镜详情、Agent 添加工具、**资源列表**、**生成队列**）；宽度 `localStorage` 记忆，视口变化自动夹紧；≤768px 全宽且隐藏手柄
- **资源列表**（`BatchAssetStudioDrawer`）：复用分镜抽屉壳层；默认展示全部状态；类型/状态 chip 滤镜；缺媒体行琥珀描边；列表区独立纵向滚动（正文 `overflow:hidden`，避免 flex 塌缩空白）；底栏「生成缺失 / 重新生成所选」；进度条用 `--svf-accent` 胶片条，禁止外来进度组件皮肤
- **生成队列**（`GenerationQueueDrawer`）：与资源列表并列的右侧抽屉；`storageKey: svf-generation-queue-drawer-width`；分区展示 queued / running / recent；running 行高亮 `--svf-accent`；顶栏入口角标显示 `queued + running` 计数；禁止外来进度组件皮肤
- **看板 Tab 栏**（`.board-tab-bar`）：两侧返回/操作按钮与 Tab 文字垂直居中（`align-items: center`），禁止 `flex-end` 导致侧钮贴顶
- **剪辑 Tab + 执行计划共存**：`.script-panel-scroll:has(.edit-cinema) .plan-panel` 限高可滚（`max-height: min(28vh, 240px)`）；`.board-panel` / `.edit-cinema` 保留可视 `min-height`，禁止计划区把影院预览挤成 0 高
- **媒体看板音频**（`MediaBoard`）：`audio`/`tts` 用紧凑声纹条 + 内联 `<audio controls>`（`.media-board-card--audio`），禁止沿用图片/视频的 16:9 空缩略框

---

## 5. 二次生成 UI

**组件**：

| 组件 | 场景 |
|------|------|
| `AssetRegenerateButton` | 单资产 / 变体 / 顶栏 inline / **镜内分段卡片** |
| `AssetRegeneratePanel` | 图文资产详情等整页二次生成（分镜抽屉已改为按段按钮） |

**布局 prop**（`AssetRegenerateButton`）：

- `inline` — 顶栏，与关闭按钮并列
- `compact` — 变体列表行内小按钮
- `card` — 分镜卡片内（由 Panel 包裹）

**按钮样式**：`.asset-regenerate-btn` — 珊瑚描边 + 浅底；busy 时 `.asset-regenerate-btn--busy` 录制脉冲点。

**状态反馈**（禁止裸 `span.muted` / `board-error`）：

- 成功：`.asset-regenerate-status--success` + `role="status"`
- 失败：`.asset-regenerate-status--error` + `role="alert"`

**文案**（i18n `common.regenerate.*`）：

- 按钮用动词：**重新生成图片 / 配音 / 画面 / 视频**
- 进行中：**生成中…**
- 完成：**二次生成已完成**（或 API message）
- 分镜卡片 hint 说明「会做什么」，不用营销腔

**权限**：仅 `manualEditEnabled === true` 时展示；执行态/主编排中由后端 403/409，前端 disabled。

**生成中状态**（`AssetGenerationContext` + `AssetGeneratingBadge`）：

- WS：`image_gen_progress`（文字资产 ID）、`tts_gen_progress`（镜头 ID）驱动看板卡片徽章；`completed` / `assets_changed`（含 `asset_id`）清除状态
- 二次生成：`AssetRegenerateButton` 乐观标记；成功由 WS / 看板刷新剔除，失败时主动清除
- 看板 `refreshBoard` 后 `pruneFromBoard` 剔除已有预览图/配音的陈旧「生成中」标记
- 展示位置：图文卡片、媒体网格、分镜卡片、详情 Modal 顶栏

---

## 6. 按钮与操作层级

| 层级 | 类名 | 用途 |
|------|------|------|
| 主生成/确认 | `btn-primary` | 发送、保存、导出 |
| 次要 | `btn-secondary` | 关闭、编辑、打开文件夹 |
| 二次生成 | `asset-regenerate-btn` | 重新生成类操作（视觉区别于 secondary） |
| 危险 | `btn-danger` | 删除、不可逆 |

同一动作全流程名称一致（按钮 → toast/状态条）。

---

## 6.1 A2UI 提问卡片（`A2UIInlineCard`）

聊天流内嵌确认 / `ask_user_question`（`kind=generic`）/ 剧本需求补全（`kind=script_requirements`）表单。

| 元素 | 约束 |
|------|------|
| 路由 | `script_structure` → 结构卡；`generic` / `script_requirements` / `plan_approval` → **可编辑** `GenericQuestionCard`；仅 `video_generation_cost` → 费用只读卡（**禁止**把需求表单当费用卡渲染） |
| 签名 | 顶部 **2px 珊瑚取景器光条**（`.a2ui-viewfinder-bar`）；pending 时 `--pulse`，尊重 `prefers-reduced-motion` |
| 眉标 | mono uppercase「等待回答 / 等待确认」— **禁止**向用户暴露 raw `kind`（如 `generic`）；`script_requirements` 用「等待回答」 |
| 标题 | `--svf-font-display`，克制字号 |
| 选项 | `select` 且选项 ≤ 6 → `.a2ui-option-chip` 单选条；更多时用原生 select |
| 过期 | `status=expired` 只读 + 引导用户在对话中重述；倒计时用 mono `.a2ui-expiry-hint` |
| 文案 | 全部走 `settings:a2ui.*` i18n |

样式写在 `apps/web/src/index.css` 的 `.a2ui-inline-*` 段；颜色仅 `--svf-*`。

---

## 7. 动效

| 效果 | 类/动画 | reduced-motion |
|------|---------|----------------|
| 录制脉冲 | `rec-pulse` / `asset-regen-pulse` | 静态 opacity |
| A2UI 取景器光条 | `a2ui-viewfinder-bar--pulse` | 静态 opacity |
| 抽屉进入 | `shot-drawer-in` | `animation: none` |
| Hover 光晕 | box-shadow transition | 保留 |

**禁止**大面积 scroll-reveal、无关 page-load 动画。

---

## 8. 无障碍

- Modal：`role="dialog"`、`aria-modal="true"`、`aria-labelledby`
- 二次生成 busy：`aria-busy={true}`
- 焦点：`focus-visible` 2px accent outline
- 键盘：Esc 关闭详情（现有 overlay 点击/按钮逻辑）

---

## 9. 文案规范

- **Sentence case**，中文不用句号结尾的按钮文案
- 空状态说明**下一步**（「尚未生成关联图片」而非「暂无数据」）
- 错误说明**原因 + 可行动**（接口 message 优先）
- 不用「抱歉」「哎呀」等人格化道歉

---

## 10. 新增页面 Checklist

- [ ] 颜色/字体来自 `design-system.css` 变量
- [ ] 详情类 UI 使用 `AssetDetailShell` / `Header` / `Section`
- [ ] 二次生成使用 `AssetRegenerateButton` 或 `Panel`，不新写 fetch
- [ ] 状态反馈使用 `asset-regenerate-status--*`
- [ ] i18n 键写入 `zh-CN` + `en`
- [ ] 支持 `prefers-reduced-motion`
- [ ] 更新本文档（若引入新令牌或模式）

---

## 11. 相关文档

- 产品交互：`docs/superpowers/reference/product-plan.md` §4.6 详情页二次生成
- 仓库结构：`docs/superpowers/reference/code-design-plan.md`
- Edit Studio：`docs/superpowers/reference/edit-studio-plan.md`
