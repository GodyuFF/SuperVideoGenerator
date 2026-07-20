# 分镜（Shot）设计结构与逻辑说明

> 日期：2026-07-14  
> 用途：供产品/设计方审阅并回复「需要调整的部分」  
> 代码依据：`core/models/entities.py`、`core/edit/shot_validate.py`、`core/edit/sub_shot_produce.py`、`docs/superpowers/reference/product-plan.md` §8  
> 状态：**待你回复调整点**  
> 补充：2026-07-14 术语澄清（挂接视频=拼接片段≠成片；配音幕可转字幕）+ 剪辑一致性与展示编辑思考（§11）

---

## 0. 你遇到的报错（映射到规则）

镜头：`shot_9bd2f7d2baba`

| 报错 | 现行规则含义 |
|------|----------------|
| 分镜时长 `21320ms` 超过上限 `15000ms` | **已取消**：单镜 `duration_ms` 不再做 15s 硬上限；时长由配音/素材实测驱动 |
| 视频轨 0：片段 `svc_*` 与同轨片段重叠 | **同一 `video_tracks` 轨内**，按 `start_ms` 排序后，相邻 clip 不得时间重叠（`start < prev_end` 即判重叠） |

典型成因（供对照，非定论）：

- TTS 配音拉长后系统把 `duration_ms` 推到 >15s，但校验仍按 15s 卡死；或  
- 多子镜各自派生/绑定到 **同一 z0 视频轨** 的多个 `ShotVideoClip`，时段未拆开或重复绑定，导致重叠。

请在文末「回复区」标明：重叠是否允许、设计层/轨道层谁算权威等。（15s 硬上限已取消。）

---

## 1. 总览：一镜 = 一个镜内「小时间轴」

```
VideoPlan（剧本一份计划稿）
└── Shot[]（有序镜头，权威剪辑结构）
    ├── 元数据：id / order / duration_ms / title / summary / plan_note / review_* …
    ├── 【设计层】sub_shots[]          ← 剧本时间轴：描述「这段该有什么」
    ├── 【轨道层】video_tracks[]       ← 可剪辑画面：真正落地 media 的 clip
    ├── 【轨道层】audio_tracks[]       ← 可剪辑音频：voice / background
    └── 【轨道层】subtitles[]          ← 句级字幕（相对镜起点）
```

投影关系（现状）：

- 设计层可被 Agent / 用户编辑；  
- 无显式 `video_tracks` 时，系统可从 `sub_shots` **派生** z0 轨（每子镜 1 个待绑定 clip）；  
- 复核/生图/TTS/生视频后，轨道层绑定 `media_id`；  
- `core.edit.shot_flatten` 可把镜投影到全片 `EditTimeline`（OpenCut / FFmpeg）。

**原则（现状文案）**：以剪辑可控为核心；标准视频为产物形态；缺素材应显式报错，不静默降级。

---

## 2. 两层结构（必须分清）

### 2.1 设计层：`sub_shots[]`（子镜）

| 概念 | 说明 |
|------|------|
| 是什么 | 镜内**剧本时间轴**上的时段单元（「这一段画面怎么讲」） |
| 不是什么 | **不是**剧本 Tab 里的 `frame` 资产本身；二者解耦，通过 `images[].frame_asset_id` 引用 |
| 时间坐标 | `start_ms` / `end_ms`：**相对本镜起点** |
| 时长约束 | 子镜区间应落在 `[0, duration_ms]` 内（规划要求）；校验对「子镜区间自身」的硬检较弱，主要对齐画面时段与轨道 |

**单条子镜主要字段**

| 字段 | 含义 |
|------|------|
| `id` | `ssb_*` |
| `start_ms` / `end_ms` | 子镜占用时段（相对镜起点） |
| `description` | 该时段画面/动作描述 |
| `camera_motion` | 运镜 canonical（如 `static` / `ken_burns_in`） |
| `element_refs` | 构图引用桶：`character` / `scene` / `prop` / `frame`（ID 列表）；属画面构图语义，**不是**子镜挂接槽 |
| `produce_mode` | 产出意图：`still` \| `text2video` \| `img2video` |
| `produce_rationale` | 可选短理由（给 Agent/UI） |
| `images[]` | 挂接的**画面**槽（见下） |
| `videos[]` | 挂接的**视频片段**槽（拼接用，**不是**成片；见下） |

**`images[]`（挂接画面）**

| 字段 | 含义 |
|------|------|
| `id` | `ssi_*` |
| `kind` | `static` 静图意图 / `video` 图生视频意图 |
| `frame_asset_id` | 指向剧本私有 `TextAsset(type=frame)` |
| `media_id` | 已生成图片 media |
| `source_media_ids` | 参考图等 |
| `start_ms` / `end_ms` | **该张图占用时段**（相对镜起点；与子镜同坐标系）。`0+0` = 未显式设置 → 解析层回填为所属子镜区间 |
| 校验 | `sub.start ≤ img.start < img.end ≤ sub.end`；同子镜多图**允许重叠** |

**`videos[]`（挂接视频片段 — 产品澄清 2026-07-14）**

| 字段 | 含义 |
|------|------|
| `media_id` / `video_clip_asset_id` | **可拼接的视频片段**（`video_clip` 文字资产 + 生成的 mp4 media），供多段拼进轨道/全片 |
| **不是** | 剧本级 / 导出级 **成片**（`fin_*` / `compose_final` 产物）。UI 文案若写「关联已有成片」属于误导，应改为「片段」 |
| `start_ms` / `end_ms` | 文档写「相对子镜」与部分 schema 描述并存；落盘常见与镜时间轴混用 → **此处是历史模糊点，建议你明确** |
| `source_kind` | `video` / `still` |
| `camera_motion` / `source_frame_asset_id` | 运镜与来源画面（片段可由画面图生出） |

**挂接边界（现状）**

| 允许挂到子镜槽 | 不允许当作子镜主挂接 |
|----------------|----------------------|
| `frame`、`video_clip`（及对应 media） | `character` / `scene` / `prop` 作为 images/videos 主对象 |
| 角色只出现在**配音幕** `character_ref`（TTS 音色） | 角色形象仅可作生视频**参考**或 frame 的 `element_refs`，不是子镜槽类型 |

**`produce_mode` 与下游（现状）**

| 值 | 含义 | 下游倾向 |
|----|------|----------|
| `still` | 静图视频（静帧 + 运镜/剪辑） | editing / Ken Burns；常挂多 frame |
| `text2video` | 文生视频 | video_agent；常挂多 video_clip |
| `img2video` | 图生视频 | video_agent；常挂 frame + video_clip |

`produce_mode` 与 UI `videoGenMode` 三值对齐（历史 `still_edit`/`ai_video`/`hybrid` 读入时自动规范）。编辑 UI **始终**允许同子镜挂接多画面与多视频并编辑各自时段（`SubShotMediaLane` 可视化）；意图字段指导 Agent / 下游，不锁死挂接数量。

---

### 2.2 轨道层：真正可剪辑的时间轴

#### 视频轨 `video_tracks[]`

- 一条轨一个 `z_index`（越大越靠前，对应 OpenCut overlay）。  
- `clips[]`：`ShotVideoClip`，**相对镜起点** 的 `start_ms`/`end_ms`。  
- `source_kind=still`：底层是静图，但仍当「带时长的剪辑 clip」（无单独图片轨）。  
- `source_sub_shot_id`：可回溯到哪个子镜。  
- **同轨硬约束**：排序后不得重叠；clip 必须落在 `[0, duration_ms]`；`end > start`。

#### 音频轨 `audio_tracks[]`

- `kind=voice`：配音幕（文案 `text`、可选 `character_ref`、音色 `voice`、绑定 TTS `media_id`）。  
- `kind=background`：背景音。  
- 同轨同样：**不重叠**、落在镜内。

#### 字幕 `subtitles[]`

- 句级，相对镜起点；可选 `character` / `color`。  
- 可与配音文案不一致；支持「从配音音频 cues/ASR」生成。  
- 校验：时段合法且在镜内（**不**强制互不重叠）。

---

## 3. 时间坐标系（现状约定）

| 量 | 坐标系 |
|----|--------|
| `Shot.duration_ms` | 本镜总长（相对镜起点 0…duration）；**由音/视频绑定与轨片段自动推算**（UI 只读），服务端 PATCH 经 `reconcile_shot_duration_from_media` 同步 |
| `sub_shots[].start/end` | 相对镜起点 |
| `images[].start/end` | 相对镜起点（与子镜同系） |
| `video_tracks[].clips[].start/end` | 相对镜起点 |
| `audio_tracks[].clips[].start/end` | 相对镜起点 |
| `subtitles[].start/end` | 相对镜起点 |
| `videos[].start/end` | **文档与部分 schema 写「相对子镜」** → 待你确认统一成哪一种 |
| 全片 EditTimeline | 镜顺序累加后的绝对时间（投影层） |

看板展示还有派生：`timeline_start_ms` / `timeline_end_ms`、展示时长来源优先级（剪辑 > 视频 > 配音 > 计划）等，属于展示层，不等于改写 Shot 权威字段。

---

## 4. 流水线逻辑（谁写什么）

```
storyboard_agent
  create_shots → 填 sub_shots(+produce_mode/画面时段) + audio_tracks(voice) + 可选 subtitles
  create_frames / create_video_clips → 挂 frame / video_clip
  persist_plan → 写入 VideoPlan
       ↓
生图 / TTS / 生视频
  绑定 media_id；TTS sync 可拉长 duration、回填字幕、调整子镜分段
  （常派生/回填 video_tracks z0）
       ↓
storyboard_refine_agent（可选）
  review_note / camera_motion / restructure_ops
       ↓
用户 PATCH 或 OpenCut 写 EditTimeline
       ↓
editing_agent / 导出
```

**时长常见路径（现状）**

- Agent 初值：`duration_ms`（规划建议值；落盘后可由 TTS/素材实测拉长，**无硬上限**）。  
- 解析时可按各轨最大终点与显式值取较大者。  
- TTS 同步可能把镜长拉到配音时长 → **可能突破 15s**，随后被 `validate_shot_structure` 打回。  
- TTS 同步后子镜常按 `start_ms` **累加分段**（相邻首尾相接，末段落在有效镜长内）。

---

## 5. 结构校验清单（`validate_shot_structure`）

保存 / PATCH / 部分 Agent 落盘前会跑：

1. `duration_ms > 0`（**无**硬上限；原 15s 上限已移除）  
2. 至少有一个 `sub_shots` **或** 至少一个视频 clip  
3. 每条视频轨：clip 合法、同轨不重叠、不超镜界  
4. 每条音频轨：同上  
5. 字幕：合法且不超镜界  
6. 子镜 `images[]` 时段落在所属子镜内  

另有：

- `validate_shot_voice_content`：有子镜时要求 voice 轨非空文案（图文管线）  
- `validate_shots_render_ready`：导出前每个音视频 clip 必须有 `media_id`

---

## 6. 与全片剪辑的关系

| 层级 | 职责 |
|------|------|
| Shot 镜内多轨 | 分镜权威；看板编辑与 Agent 直接改这里 |
| EditTimeline | 全片剪辑轴；**仅** editing Tool / 用户 OpenCut PATCH 写入 |
| TTS sync | **不写** EditTimeline；只改 Shot 内 audio/字幕/时长/子镜分段等 |

---

## 7. UI 侧（对照理解）

分镜抽屉只读 / 编辑大致对应：

- 迷你时间轴：配音轨 + 画面轨段块  
- 配音幕 ↔ `audio_tracks(kind=voice).clips`  
- 子镜卡片 ↔ `sub_shots`（含 produce_mode、画面时段、frame/video 挂接）  
- 剪辑轴预览：仅当子镜与 `source_kind=video` 且已绑 media 的 clip 有交集时展示（静图 still 不展示「剪辑轴」块）

---

## 8. 已知模糊 / 张力点（请重点拍板）

请直接回复编号 + 你的选择或改法：

1. **15s 硬上限**  
   - 维持 15s（超时必须拆镜）？  
   - 放宽上限（多少）？  
   - TTS 拉长时自动拆镜 / 允许临时超上限但标记？

2. **同轨视频 clip「禁止重叠」**  
   - 维持（一层 z0 必须首尾相接）？  
   - 允许多 clip 叠化（则校验改规则，剪辑投影也要改）？  
   - 多子镜应强制分轨（z1/z2）还是强制串行在 z0？

3. **设计层 vs 轨道层权威**  
   - 保存时以 `sub_shots` 重算 `video_tracks`？  
   - 还是以 `video_tracks` 为准、`sub_shots` 只读描述？  
   - 双写如何防漂移（你这次重叠更像双写/派生未清）？

4. **`videos[].start_ms/end_ms` 坐标系**  
   - 统一为相对镜起点（与 images/sub_shots 一致）？  
   - 还是明确相对子镜起点并在校验中换算？

5. **超长配音与子镜分段**  
   - TTS >15s：拆多镜 / 压速 / 截断 / 允超上限？  
   - 子镜累加规则是否符合你的故事节奏预期？

6. **`produce_mode=hybrid`**  
   - 继续「仅意图」？  
   - 还是要规定 hybrid 时 images 时段如何映射到 still clip vs AI clip？

7. **挂接边界**  
   - 现「子镜只挂 frame/video_clip」是否保留？  
   - 是否需要「子镜直接挂角色形象」等例外？

8. **结构校验失败时的产品行为**  
   - 阻断保存并弹完整问题列表（现状偏此）？  
   - 允许保存为「脏状态」仅警告？  
   - Agent 落盘失败是否应自动 restructure？

---

## 9. 建议回复格式

请按下面模板回复（可直接改写）：

```text
【分镜结构】我看完 docs/superpowers/reference/shot-structure-and-logic.md

1. 15s 上限：……
2. 同轨重叠：……
3. 设计层/轨道层权威：……
4. videos[] 坐标系：……
5. TTS 超长：……
6. hybrid：……
7. 挂接边界：……
8. 校验失败 UX：……

另外针对 shot_9bd2f7d2baba：
- 我期望的正确结构是：……
- 系统下一步应自动：拆镜 / 拉长上限 / 清重叠 clip / ……

【一致性 & 展示】我看完 §11
9. 权威层选择：A / B / C（见 §11.3）
10. 配音→字幕：期望规则是……
11. 分镜抽屉 UI：优先改哪些面板……
```

---

## 10. 关键代码索引

| 主题 | 路径 |
|------|------|
| 领域模型 | `core/models/entities.py`（`Shot*`） |
| 结构校验 | `core/edit/shot_validate.py` |
| 画面时段 / produce_mode | `core/edit/sub_shot_produce.py` |
| 从子镜派生视频轨 | `core/llm/agent/llm_action.py` → `_derive_video_tracks_from_sub_shots` |
| 产品说明 | `docs/superpowers/reference/product-plan.md` §8 Shot 结构 |
| produce_mode 专项 | `docs/superpowers/specs/2026-07-14-subshot-image-timing-produce-mode-design.md` |
| 全片投影 | `core/edit/shot_flatten.py` → `EditTimeline` |

---

## 11. 剪辑一致性 & 展示编辑（思考稿，待拍板）

### 11.1 三层媒体语义（先钉死名词）

| 层级 | 是什么 | 典型资产 | 出现位置 |
|------|--------|----------|----------|
| **画面** | 静图 / 关键帧意图 | `frame` + image media | `sub_shots[].images[]` |
| **视频片段** | 图生/文生出的 **可拼接片断**，用于轨道拼接成片 | `video_clip` + video media | `sub_shots[].videos[]` → 绑定进 `video_tracks` |
| **成片** | 全片（或多镜导出）最终文件 | `fin_*` / export | **不进**子镜挂接槽；只在导出 / 成片面板 |

一致性推论：

1. 子镜「视频列表」= **选片段 / 生成片段**，文案禁止「成片」。  
2. `video_tracks` 上的 `source_kind=video` clip = 某一拼接片断在镜时间轴上的排期。  
3. OpenCut / FFmpeg 读的是 **投影后的 `EditTimeline`**（多镜片段 + 配音 + 字幕），不是某个子镜挂的单个 mp4。

### 11.2 今日一致性为何容易破

```
用户/Agent 改 sub_shots     ──派生/半同步──►  video_tracks
用户改配音/TTS 拉长 duration ──部分写回──►  audio_tracks + duration_ms
剪辑台改时间轴              ──回写？──►      EditTimeline（user_edited 时可不跟 Shot）
```

痛点：

| 问题 | 表现 |
|------|------|
| **双写无主从** | 设计层改了，轨道层旧 clip 时段未随之拆开 → 同轨重叠 / 超 15s |
| **片段 vs 轨** | `videos[]` 有 media，但 `video_tracks` 未重排或仍占满整子镜 |
| **配音与字幕两套源** | 幕文案 / TTS 音频 / 字幕 cues 可互相偏离；已有「从配音**音频**生字幕」，缺「从配音**幕文案**转字幕」 |
| **坐标系未统一** | `images[]` 相对镜；`videos[]` 文档含糊 → 校验与 UI 对不齐 |
| **成片误挂** | UI 若允许把 fin 当片段挂上，语义与导出链冲突 |

### 11.3 保证剪辑一致性的三种模型（请选）

**方案 A — 设计层权威（推荐默认生产流）**

- 写：`sub_shots` + `audio_tracks`（配音幕）+ `duration_ms`  
- 读：UI 剧本时间轴、Agent 规划  
- 派生：每次保存/复核通过后 **整镜重算** `video_tracks`（按子镜/画面时段铺 clip；片段 media 从 `videos[]` 注入）  
- `EditTimeline`：未 `user_edited` 时一律 `compile_timeline_from_shots`  
- 优点：分镜抽屉一处改完即一致；重叠/超长在派生阶段就能报或自动拆镜  
- 代价：剪辑台细调会被下次「从分镜重编译」覆盖（除非设锁）

**方案 B — 轨道层权威（推荐精剪流）**

- 写：OpenCut / 镜内迷你时间轴 → `video_tracks` / `audio_tracks` / `subtitles`  
- `sub_shots` 降为说明/意图快照，或「只读回顾」  
- 优点：精剪结果不被派生冲掉  
- 代价：Agent 再生图/换片段时必须 **显式重新挂轨**，不能静默改设计层当完成

**方案 C — 带锁的双层（折中）**

- 默认 A；用户在剪辑台改过某镜 → 该镜 `timeline_locked=true`，派生跳过该镜  
- 解锁 = 确认「用设计层覆盖轨道」  
- 与现有 `EditTimeline.user_edited` 思想对齐，下沉到 **镜级**

**建议**：生产默认 **A**；Studio 触达后该镜升 **C 的锁**。全片成片永远只读 `EditTimeline`（由未锁镜从 Shot 编译 + 已锁镜保留手改）。

统一规则（无论 A/B/C）：

1. **全片时间** = 镜序拼接；镜内时间一律 **相对本镜 0**。  
2. `images[]` / `videos[]` / 字幕 / 配音 clip **同一坐标系**（相对镜；跨子镜用绝对镜内 ms，不用「相对子镜 0」混用）。  
3. 片段时长 > 子镜窗：要么裁切（in/out），要么拉长子镜并触发镜时长重算（见 §8 TTS）。  
4. 同 z 轨默认不重叠；要叠化 → 升 z 或显式 transition（现状无则不要偷叠）。

### 11.4 配音幕 → 字幕（产品缺口）

现状：

- 配音幕：`audio_tracks` voice clip（`text` + `character_ref` + TTS media）  
- 字幕：独立 `subtitles[]`  
- 已有：**从配音音频**生成字幕（cues / WhisperX），**不用**幕文案  

缺口：**配音幕文案一键转为字幕行**（不依赖 ASR）——适合旁白定稿、音频未齐、或只要「字」不要对齐精度时。

建议能力（实现前请勾选规则）：

| 项 | 选项 |
|----|------|
| 触发 | 单幕按钮 / 整镜「幕→字幕」 |
| 文本源 | 只用 `clip.text`（默认） |
| 时间 | 按幕 `start_ms–end_ms` 整段一条；或按标点切句均分时段 |
| 角色色 | 抄 `character_ref` → 字幕 `character` / 默认色 |
| 冲突 | 覆盖已有字幕 / 仅补空 / 追加在末尾 |
| 与 ASR 关系 | 「幕转字幕」与「音频生字幕」并列；后者对齐口型更准，前者文案权威 |

一致性：幕改文案后，若字幕仍标「源自该幕」，可提示「字幕已过期，重新转换」；不自动静默改写（避免冲掉用户手改字幕）。

### 11.5 更好的展示与编辑（UX）

**分镜抽屉一眼三条带（推荐信息架构）**

```
┌ 时间标尺（0 … duration_ms）──────────────────────────┐
│ 画面带：子镜块 + 内嵌「本图时段」条                   │
│ 片段带：每个 video_clip 片段条（可拖 in/out）         │  ← 不是成片
│ 配音带：voice 幕条（角色色）                         │
│ 字幕带：句级条（可从幕转换 / 从音频生成）             │
└─────────────────────────────────────────────────────┘
下方：当前选中对象的属性（produce_mode / 挂接 frame|片段 / 幕文案…）
```

原则：

1. **一条时间尺**：所有层对齐同一镜坐标，消灭「列表数字对不齐」的感觉。  
2. **片段条 ≠ 成片**：标签用「片段 / Clip」，生成按钮「生成视频片段」；成片只出现在导出结果。  
3. **剪辑轴出现条件**（现状：有绑定视频片段且与子镜相交才显示）可保留，但空态应说明「尚无片段上轨，仍可先排画面与配音」。  
4. **配音幕卡片**：文案、角色、试听、以及「转为字幕」「从音频生成字幕」两个明确入口。  
5. **校验失败**：标尺上染色冲突区（重叠 / 超长），点条跳到对应幕/片段，而不是只 toast 一句。  
6. **Studio**：全片看拼接结果；回写仅当镜未锁或用户确认覆盖。

### 11.6 和当前报错的对读

`shot_9bd2f7d2baba`：多段 **片段** 挤进同一 z0 轨且时段未拆 → 重叠；配音拉长 → 超 15s。  
在方案 A 下：保存时按子镜重排片段轨 + TTS 策略（拆镜或放宽）应在派生阶段消掉两类错，而不是事后只校验。

---

*审阅后请按 §8 / §9 / §11 回复；确认后再改规则与实现。*
