# 周任务系统设计说明（给 Cursor 直接生成）

## 产品定位
个人周任务工作台：以「周」为节奏设置模板任务，按大类/子类创建，支持临时灵感任务，首页看本周/本月重点，第三页看完成与分布统计。

视觉参考：左侧深色导航 + 右侧暖米色卡片工作区（接近附图 Console 风格），信息密度中等，卡片可筛选。

技术建议（前端为主）：
- Vite + React + TypeScript
- Tailwind CSS
- Zustand 或 React Context 做本地状态
- 数据先用 localStorage，结构预留后续接 API
- 路由：`/` 首页、`/tasks` 任务预览与编辑、`/stats` 数据统计、`/months` 月度规划与历史

---

## 信息架构

```
/                 首页：本周重点、本月概览、要点、本周模板进度
/tasks            任务工作台：大类→子类→任务列表，预览/编辑/新建
/stats            统计：完成率、按周、按大类、按来源（模板/自定义）
/months           月度规划 + 历史月/周回看（可预排下月及更远）
```

侧栏导航：
- 首页
- 任务工作台
- 月度 / 历史
- 数据统计
- 底部显示当前周次，例如 `第 38 周 · 2026-09-15 ~ 2026-09-21`

---

## 分类体系（taxonomy）

大类固定 6 个。子类可配置，默认如下。

### 1. 软件开发
- 前端 UI / 交互
- 组件与设计系统
- 接口联调
- 性能与体验
- Bug 修复
- 工程化 / 工具链
- 代码评审与重构
- 发版与验收

### 2. 工作内容
- 会议与对齐
- 文档与方案
- 进度跟进
- 跨部门协作
- 周报 / 复盘
- 招聘 / 面试
- 行政事务

### 3. web3 操盘
- 行情观察
- 仓位管理
- 链上数据
- 风险控制
- 交易复盘
- 宏观 / 事件驱动
- 策略实验

### 4. web3 运营
- 内容策划
- 社区运营
- KOL / 合作
- 活动与空投
- 数据看板
- 品牌与叙事
- 用户增长

### 5. 海外运营
- 多语言内容
- 海外社媒
- 增长实验
- 本地化适配
- 渠道投放
- 用户反馈
- 合作拓展

### 6. 其他思路
- 灵感收集
- 学习笔记
- 实验想法
- 长期项目
- 临时插入

任务来源：
- `template`：每周套用的模板任务
- `custom`：灵感或临时插入

任务状态：`todo` | `doing` | `done` | `dropped`

优先级：`P0` | `P1` | `P2`

星级（可选，用于模板重要度）：1–5

---

## 数据模型

```ts
type CategoryId =
  | 'dev'
  | 'work'
  | 'web3-trade'
  | 'web3-ops'
  | 'overseas-ops'
  | 'ideas'

interface SubCategory {
  id: string
  categoryId: CategoryId
  name: string
}

interface TaskTemplate {
  id: string
  title: string
  categoryId: CategoryId
  subCategoryId: string
  defaultPriority: 'P0' | 'P1' | 'P2'
  stars: 1 | 2 | 3 | 4 | 5
  notes?: string
  weekdayHint?: number[] // 1-7，建议执行日
  enabled: boolean
}

interface Task {
  id: string
  weekId: string          // '2026-W38'
  title: string
  categoryId: CategoryId
  subCategoryId: string
  source: 'template' | 'custom'
  templateId?: string
  status: 'todo' | 'doing' | 'done' | 'dropped'
  priority: 'P0' | 'P1' | 'P2'
  dueDate?: string        // ISO date
  points?: string[]       // 要点 / 验收点
  notes?: string
  createdAt: string
  completedAt?: string
}

interface WeekNote {
  weekId: string
  monthKey: string        // '2026-09'
  highlights: string[]    // 本周要点
}

interface MonthPlan {
  monthKey: string        // '2026-09' | '2026-10' | ...
  title?: string
  goals: string[]         // 本月主线，首页只读前 3 条
  items: MonthItem[]
  status: 'planned' | 'active' | 'archived'
}

interface MonthItem {
  id: string
  title: string
  categoryId: CategoryId
  subCategoryId?: string
  priority: 'P0' | 'P1' | 'P2'
  targetWeekId?: string   // 预拆到哪一周，可空
  rolledFromMonthKey?: string
  status: 'planned' | 'split' | 'done' | 'dropped'
}
```

每周一（或进入新周时）根据启用的模板生成该周任务副本，已存在的不重复生成。自定义任务随时插入到当前周。

---

## 页面 1：首页 `/`

布局：顶栏周切换 + 三列/两行卡片。

区块：
1. **本周主要任务**（最多 6–8 条）
   - 取本周 `P0` + 进行中 + 未完成模板任务
   - 每条显示：标题、大类标签、子类、状态、来源（模板/自定义）
2. **本月主要任务 / 目标**
   - 展示本月跨周仍未完成的 P0，以及 `WeekNote.monthGoals`
3. **本周要点**
   - 可编辑的 3–6 条短句（类似附图「好情况 / 坏情况」那种情景卡，但改成任务要点）
   - 建议 3 张情景卡：`本周必须完成` / `可延后` / `灵感待插入`
4. **本周进度条**
   - 完成数 / 总数，模板完成率 vs 自定义完成率
5. **快捷入口**
   - 生成本周模板任务
   - 新建自定义任务
   - 进入任务工作台

交互：
- 周选择器：上一周 / 本周 / 下一周
- 勾选完成可在首页直接改状态
- 要点支持行内编辑并保存到 `WeekNote`

---

## 页面 2：任务预览与编辑 `/tasks`

对标附图结构，但内容换成任务：

左列：大类列表
- 显示大类名、星级汇总（该大类本周任务数）、未完成数
- 选中后中间列切换

中列：子类列表 + 筛选
- 搜索框
- 筛选：全部星级 / 来源（模板、自定义）/ 状态
- 每个子类显示本周任务数

右列：任务详情工作区
- 顶部：当前子类名称
- 任务卡片列表，每张卡：
  - 标题、优先级、状态、来源、截止日期
  - 要点列表（checklist）
  - 备注
  - 操作：编辑、完成、删除、转为模板
- 底部或右侧抽屉：新建/编辑表单

新建任务表单字段：
- 标题（必填）
- 大类 / 子类（必填）
- 来源：模板套用 / 自定义
- 优先级、截止日期
- 要点（可动态增删）
- 备注
- 若来源是模板：选择已有模板或「保存为新模板」

模板管理（同页次级面板即可，不必第四页）：
- 启用/停用模板
- 编辑默认优先级与星级
- 「应用到本周」按钮

预览模式：
- 默认列表预览
- 点卡片进入编辑态（右侧抽屉或页内展开）

---

## 页面 3：数据统计 `/stats`

时间范围：本周 / 本月 / 近 8 周 / 自定义。

图表与指标（可用 Recharts 或纯 CSS 条形图先做）：
1. 总览卡片：创建数、完成数、完成率、自定义占比
2. 按周完成趋势（柱状或折线）
3. 按大类分布（堆叠条或环形）
4. 按子类 Top 10（完成数）
5. 模板任务 vs 自定义任务完成对比
6. 明细表：日期、周次、任务名、大类、子类、来源、状态、完成时间

支持导出 CSV（可选）。

---

## 默认周模板示例（方便生成演示数据）

软件开发 / 前端 UI：
- 本周核心页面交互走查
- 任务卡片状态与筛选打通

软件开发 / 发版与验收：
- 周五体验验收清单

工作内容 / 周报与复盘：
- 写本周复盘（3 条成果 + 1 条阻塞）

web3 操盘 / 行情观察：
- 每日开盘前 15 分钟观察（可拆成 5 条日常，或一条带要点）

web3 运营 / 内容策划：
- 产出 1 条主内容提纲

海外运营 / 海外社媒：
- 更新本周英文动态日历

其他思路 / 灵感收集：
- 收录本周未消化灵感（自定义入口）

---

## UI 规范

颜色：
- 侧栏：`#1c1917` 近黑棕
- 背景：`#f3efe6` 暖米
- 卡片：`#fffdf8`
- 主强调：`#c2410c` 或深琥珀描边（选中大类）
- 标签：大类各一色（蓝/青/紫/绿/橙/灰）

组件：
- 大类按钮：左色条 + 名称 + 计数
- 任务卡：圆角 16px，浅边框，状态胶囊
- 筛选芯片：全部 / 模板 / 自定义 / 仅未完成

文案语言：中文界面。

---

## Cursor 生成时的实现顺序
1. 先写 `src/data/taxonomy.ts` 和 mock `tasks.ts`
2. 搭 Layout + 三路由
3. 做 Tasks 页（最像附图，也是主工作流）
4. 做首页聚合
5. 做统计页
6. 接 localStorage 持久化与「生成本周模板」逻辑

不要上后端。状态变化必须立刻反映到首页和统计。

---

## 按天落周模板（解决「一键生成太笼统」）

现有周笔记习惯：`第N周.md` 里按 **周五 → 周一** 写「高能执行期」。系统应对齐这个结构，而不是只生成一包本周任务。

### 核心原则
1. 模板默认挂在星期几，一键生成后直接落到对应天。
2. 没指定日期的任务进「待排期」池，点一下星期芯片就能坐下。
3. 每日例行（如行情观察）用「重复：工作日」一次配置，生成 5 条实例，而不是 5 个模板。
4. 一天建议上限：P0 ≤ 2，总任务 ≤ 5。超了在该列顶部给浅警告。

### 模板新增字段

```ts
type Weekday = 1 | 2 | 3 | 4 | 5 | 6 | 7  // 周一=1

interface TaskTemplate {
  // ...原字段
  scheduleKind: 'once' | 'weekdays' | 'customDays'
  weekdays: Weekday[]     // once 通常 1 天；weekdays 默认 [1,2,3,4,5]
  slot?: 'morning' | 'focus' | 'wrap'  // 可选时段：开盘前 / 高能 / 收尾
}
```

任务实例增加：`weekday`, `date`, `slot`。

### 一键生成规则
- 进入新周或点「生成本周模板」：
  - `once` → 在指定那天生成 1 条
  - `weekdays` → 周一到周五各生成 1 条（同一 templateId，不同 date）
  - `customDays` → 只在勾选的那几天生成
- 已存在的 `(templateId + date)` 不重复生成
- 生成后仍可拖到别的天；拖动只改这一条实例，不影响模板

### 便捷操作（按使用频率）

| 操作 | 做法 |
|---|---|
| 落到某天 | 任务卡上 一 二 三 四 五 芯片，单击即切换 |
| 改到另一天 | 在「本周日程」五列之间拖拽 |
| 每天都要做 | 模板设为「工作日重复」，或任务菜单「复制到本周剩余工作日」 |
| 先不想排 | 丢进右侧「待排期 / 灵感」；首页「灵感」列与此同步 |
| 今天只看今天 | 日程板顶部切换：五列全周 / 仅今天 |
| 对齐周笔记 | 导出或预览为 `第N周.md`：周五在上、周一在下（与现有 Obsidian/笔记顺序一致） |
| 一天太满 | 卡上显示「移到明天」；或一键把非 P0 推到待排期 |

### 任务板改成双视图
工作台顶部增加视图切换：
- **分类视图**：大类 → 子类（原来的三栏，适合归档和按主题找）
- **日程视图（默认）**：待排期 + 周一至周五（高能执行期）

日程视图列顺序两种模式可切：
- 执行序：周一 → 周五（做任务时用）
- 笔记序：周五 → 周一（对照 `第N周.md` 时用）

### 推荐默认模板（按天，可直接当种子数据）

| 模板 | 类型 | 落到 |
|---|---|---|
| 行情观察（15 分钟） | 工作日重复 | 每天上午 |
| 进度跟进 | 工作日重复 | 每天下午收尾 |
| 内容策划 1 条提纲 | once | 周二 focus |
| 前端主任务块 | once | 周一、周三 focus（customDays） |
| 社区/海外更新 | once | 周四 |
| 交易复盘 | once | 周五 wrap |
| 周报/复盘 | once | 周五 wrap |
| 发版验收 | once | 周五 |
| 会议与对齐 | once | 周一 morning |
| 灵感收集（收件箱） | once | 待排期，不占星期 |

「必须 / 可延后 / 灵感」不要再和子类名重复展示：  
- 必须 = 本周已排期且 P0/P1  
- 可延后 = 已排期但 P2，或可从当天移走  
- 灵感 = 待排期自定义任务  

### 首页如何跟着变
- 进度按「本周已排期任务」计，待排期不计入分母（避免 0/10 这种虚高）
- 「本周主任务」只显示已挂到某天的 P0
- 增加一行「今日」：今天列的 3–5 条，比整周更先看

### Cursor 实现要点
1. `taxonomy.ts` 外再加 `templates.ts`（带 weekdays / scheduleKind）
2. 任务板默认渲染周日程五列 + 待排期
3. 芯片改日、拖拽改日、复制到剩余工作日 三个动作必须有
4. 生成函数：`applyTemplatesToWeek(weekId)` 按 date 去重
5. 可选：`exportWeekMarkdown(weekId)` 输出与图二相同的周五→周一结构

---

## 操作流程（先于 UI 细节）

截图里的问题不是缺按钮，是三种工作混在一起：
生成没有按天落下 → 全堆待排期 → 每张卡同时露出改日/复制/明天/待排/编辑/完成 → 首页又把待排期再列一遍。

先规定人怎么用。

### 三种工作分开

| 工作 | 频率 | 人实际在做的事 |
|---|---|---|
| 配置模板 | 偶尔 | 规定「这类事默认周几、要不要每天重复」 |
| 排期 | 每周一次，约 3 分钟 | 生成 + 把少数没落点的灵感拖进某天 |
| 执行 | 每天 | 只看今天，完成或推到明天 |

首页和任务板默认都只服务「执行」。配置进抽屉。排期用一个明确入口打开，用完关掉。

### 一周只用记 4 步

**开周（排期）**
1. 点「生成本周」
2. 检查五列是否已经有任务；待排期应几乎为空
3. 某天超过 5 条，把非 P0 拖走
4. 关掉排期，进入执行

生成后若待排期仍超过 3 条，去改模板的默认星期，不要在卡片上点五个芯片。

**每天（执行，默认）**
1. 打开先看「今天」
2. 做完勾选
3. 做不完按「明天」

执行时不需要看见：一二三四五、复制剩余日、待排、编辑。

**随时（捕捉）**
一行标题丢进待排期。不进完成率。想做了再「排到今天」。

**收周（周五）**
未完成：丢弃 / 推下周同一天 / 回待排期。不必重新摆五列。

### 生成后应长这样（验收标准）

- 周一：会议对齐、前端主块、行情观察
- 周二：内容策划、行情观察
- 周三：前端主块、行情观察
- 周四：海外或社区、行情观察
- 周五：复盘、验收、行情观察
- 待排期：最多 1 条灵感

现在截图是 8 条全在待排期，根因是模板没带星期，不是交互不够。

### 三种模式卡片上分别留什么

执行：标题、完成、明天。其它进 `···`  
排期：拖到某一列，或待排期多选「放到周二」。不要每张卡 5 个星期按钮  
配置：模板表，一行一条（名称 / 重复类型 / 默认星期 / 开关）

### 首页只留 4 块

1. 今天（最大，主操作）
2. 本周进度（仅已排期）+ 入口「排期本周」
3. 整周 P0（没有就隐藏）
4. 本月主线（只读，最多 3 条）

待排期长列表和五列都不要放首页。周末文案写「周末可休息，需要就去排期」，不要空的「今日列」。

### 任务板默认不是五列空板

默认三列：**今天 / 明天 / 待排期**。  
点「整周」才展开五列。执行时空着的周二到周五只会让人觉得没排上。

### 给 Cursor 的顺序
1. 先修模板种子，生成必须落到具体星期
2. 加 `mode: execute | plan | setup`，执行模式藏排期按钮
3. 首页改成今天优先
4. 任务板默认今天/明天/待排期
5. 再做整周拖拽

---

## 月度预排与历史回看

任务系统必须能看过去、排现在、预写下月及更远月份。周仍是执行单元，月是规划单元。不要让用户在月视图里点每日完成。

### 层级

```
月度主线（可写到 12 个月以后）
  └ 预拆到某周（可选）
       └ 开周时生成本周任务（执行、勾选、统计）
```

跨月的周（如 9/29–10/5）归入 **开始日所在月**，月页上两头各露半周即可。

### 页面 `/months`

左侧：年份 + 月份列表（已有计划的月加点）。可点到明年、后年，不设截止。

右侧三种状态同一套布局：

1. **未来月（下月及更远）** — 规划  
   - 写 3–7 条主线  
   - 添加月任务（大类/子类/优先级）  
   - 可选「放到第 N 周」，不填就留在月池  
   - 不生成每日格子，不计入本周完成率

2. **本月** — 规划 + 执行入口  
   - 上：本月主线  
   - 中：未拆到周的月池  
   - 下：本月各周缩略（完成数/P0），点周进入 `/tasks?week=`  
   - 「拆进本周」把月任务变成当前周任务，`source` 记 `month`

3. **历史月** — 只读回看  
   - 主线、各周完成率、完成/未完成/丢弃列表  
   - 默认不可改完成状态（避免改历史）  
   - 未完成可「结转到下月」或「结转到某周」

顶部切换：`规划 | 历史`。历史也可用统计页的时间筛选进入同一数据。

### 和现有页怎么接

- 首页「本月主线」= 当前 `MonthPlan.goals`，点「编辑月计划」去 `/months`  
- 开周生成：本周模板 + 已指定 `targetWeekId` 的月任务  
- 收周未完成：丢弃 / 推下周 / 退回本月池 / 结转下月  
- 统计默认本月，可切近 8 周、任意历史月、自定义区间  
- 周选择器除上一周/下一周外，提供月份跳转（进那个月的第一周或月页）

### 操作流程（补在原 4 步之外）

**月末或月初（规划，约 10 分钟）**  
打开下月 → 写下主线 → 把能确定的事标到第几周 → 其余留月池。更远月份只写主线即可，不必拆周。

**开周**  
生成本周 = 周模板 + 本周已挂上的月任务。月池里没拆的不自动进来。

**看历史**  
月页切历史，或统计选月份。看「那个月设过什么、完成了什么」。

### 约束
- 可预排任意未来月，但执行仍只发生在「当前周」  
- 历史默认只读  
- 月任务未拆周前不进完成率  
- localStorage 按 `monthKey` / `weekId` 分桶，方便以后换 API

### 给 Cursor
加路由 `/months`、`MonthPlan` 数据、月列表可点未来月、历史月只读、开周合并 `targetWeekId === 当前周` 的月任务、首页主线改为读 MonthPlan。先做月列表 + 主线编辑 + 跳周，拆周和结转放第二步。


## UI 优化（结构已全，只改观感和密度）

原则：暖米色工作区保持，减少「说明文案 + 工具条 + 空列」同时抢视线。执行时安静，排期时才亮。

### 全局
- 顶栏只留：标题 + 周次 + 三个页签。流程那句灰字可删。
- 页内长说明默认不显示。
- 一屏只留 1 个实心主按钮（日程页「生成本周」，首页「排期本周」）。
- 圆角 14–16px，描边 `#eadfd0`，选中才用琥珀描边。
- 待排期超载用列头一句提示，不要整列红框。

### 日程页
- 工具芯片收成一行：左视图，右生成+模板，禁止折成两排。
- 列头只要 `周一  2`，P0 用小橙点。
- 空列淡字「投放任务」，不要 `-`。
- 卡片：标题 + 一行 meta；hover 才出完成/明天。
- 待排期列略窄；数字 8 放列头即可。

### 分类页
- 栏宽 `200 / 240 / 1fr`，填满右栏留白。
- 大类选中用左色条，不要重框。
- 子类计数 0 降到 45% 透明。
- 右栏卡片补「未排期 / 已在周三」。

### 首页
- 周末主卡改一行，不要半屏空白。
- 本月主线标题完整两行，不要 `仓位…`。
- 「重新填格」改文字链；捕捉输入并进进度卡，少一块卡片。

### 贴给 Cursor
保持信息架构，只做视觉：删重复说明、收敛工具条、待排期不整列报警、卡片 hover 再出操作、周末主卡改一行、分类 0 计数弱化、全站一个实心主按钮。

---

## 未来周预览 / 生成，与「某一天的那一条」编辑

排期页必须能离开本周：预览下周、下下周，以及月计划里挂过的更远周。生成也是对着 **当前正在看的那一周**，不是永远只生成「此刻的自然周」。

### 周切换（日程页顶栏左侧，工具条同一行）

```
〈  2026 第 37 周  8/31–9/6  〉     [本周] [下周] [选周]
```

- 左右箭头按周翻，可翻到任意未来周、历史周  
- 「选周」打开小日历，点日期落到那周  
- 看的不是自然本周时，主按钮文案改成 **「生成这一周」**，不要写死「生成本周」  
- 未生成过的未来周：五列空 + 中央短句「这一周还没生成」+ 主按钮  
- 已生成的未来周：可预览、可改排期、可改单条细则；首页「今天」仍只显示自然日

生成规则与本周相同：模板默认星期 + 该 `weekId` 上的月任务。已存在 `(templateId + date)` 不覆盖用户改过的实例。

「重新填格」只填空位，不重置已编辑的那一天那一条。

### 排期选项保持常驻（不要进执行就藏光）

日程工具条右侧 **始终** 保留这些，用文字/描边，不要靠模式藏掉：

- 生成这一周  
- 重新填格（只补缺）  
- 模板配置  
- 今天 / 整周  
- 一→五 / 五→一  

卡片上常驻的排期入口要少而稳：`移到 ▾`（待排、一、二、三、四、五）和 `复制到…`。不要五个芯片平铺，但选项必须在。拖到另一列同样有效。

### 编辑细则 = 某一天的任务实例，不是改模板

点卡片打开居中弹窗（不要跳分类页，不要改全局模板）。

弹窗标题：`周五 · 复盘 · 2026-09-04` 或 `周一 · 行情观察 · 2026-09-01`  
副标题：`第 36 周 · 8/31–9/6`

可改字段（只写进这一条 `Task`）：
- 标题、要点、备注、优先级、状态  
- 日期 / 星期（改了就换列）  
- 时段：上午 / 高能 / 收尾  
- 来源只读：模板 / 月计划 / 自定义  

底部两个可选动作，默认折叠：
- 「同步回模板」——以后周按新细则生成  
- 「只改这一天」——默认，不影响模板、不影响其他天的「行情观察」

每日重复拆出来的五条是五个实例。改周三那条，周一、周二不动。

### 板子高度

看板区 `min-height: calc(100vh - 顶栏)`，列背景拉满。不要卡片只有两行、下面半屏空白。列内滚动，页面不出现大块空米底。

### 给 Cursor
1. 日程页加 weekId 切换，生成函数吃当前 weekId  
2. 未来周可预览、可生成、可编辑实例  
3. 点卡片开弹窗，编辑绑定 `task.id`，默认不同步模板  
4. 排期动作常驻：移到、复制、生成这一周、填格、模板  
5. 列高撑满视口

---

## AI 生成本周任务 / 事后归纳

AI 是 **排期助手 + 复盘秘书**，不是新的任务源、不是聊天首页。  
所有 AI 产出必须能映射进现有看板字段（`weekId`、大类/子类、星期、优先级、要点），且 **预览 → 用户确认 → 才写入 localStorage**。

与手工能力的关系：

| 已有能力 | AI 不应替代 |
|---|---|
| 「生成这一周」+ 模板池 + 填格 | 模板默认星期、catalog 常驻待排 |
| 点卡片弹窗改单条实例 | 默认「只改这一天」 |
| 同步回模板 | 仅用户显式点击才改模板配置 |

AI 只补：**空位建议**、**未完成位的替换草案**、**收周/收月文字归纳**。

---

### 入口（描边按钮，不占实心主按钮位）

| 位置 | 按钮 | 说明 |
|---|---|---|
| 日程工具条 | `AI 生成本周` / `AI 生成这一周` | 文案随当前 `boardWeek` 变化，与「生成本周」并列、ghost 描边 |
| 收周视图 / 周五流程 | `AI 收周归纳` | 仅在 `boardFlow=close` 或首页收周入口出现 |
| 月度 · 历史月 | `AI 归纳本月` | 历史态只读预览，确认后写入 `MonthPlan.review` |
| 统计页 | `AI 一句话` | 对当前筛选区间生成摘要，**不写任务** |

不要单独开 `/ai` 页，不要自由对话。

---

### 数据模型扩展

```ts
/** LLM 返回、前端预览用的草案行（尚未写入 TaskStore） */
interface AiTaskDraft {
  tempId: string              // 预览列表内临时 id
  title: string
  categoryId: string
  subcategoryId: string
  priority: 'must' | 'defer' | 'inspiration'  // 对齐现有 P0/P1/灵感
  daySlot: 0 | 1 | 2 | 3 | 4 | 5 | 6         // 0=待排
  slot?: 'morning' | 'focus' | 'wrap'
  notes?: string                // 要点/验收，写入 Task.notes
  scheduleKind?: 'once' | 'weekdays' | 'days' // 例行：weekdays 合并为一条草案
  weekdays?: number[]           // scheduleKind=days 时用
  sourceHint?: 'template' | 'month' | 'custom' | 'carry'  // 只读展示
  replaceTaskId?: string        // 「替换未完成位」模式下指向将被覆盖的 task.id
}

interface AiWeekDraftResponse {
  weekId: string
  summary?: string              // 一两句排期说明
  items: AiTaskDraft[]
  warnings?: string[]           // 超限、taxonomy 修正等
}

interface WeekReview {
  weekId: string
  wins: string[]                // 成果，建议 3 条
  blockers: string[]            // 阻塞，建议 1 条
  carryTitles: string[]         // 建议结转的任务标题
  aiGeneratedAt?: string
  editedAt?: string
}

interface MonthReview {
  monthKey: string
  goalRetrospect: string[]      // 主线兑现情况
  carryToNext: string[]       // 建议结转下月
  summary?: string              // 一段话
  aiGeneratedAt?: string
}
```

存储键建议：

- `tr_tasks_ai_draft_v1` — 仅缓存最后一次预览（可选，刷新可丢）
- `WeekNote` 增字段 `review?: WeekReview`
- `MonthPlan` 增字段 `review?: MonthReview`
- 统计页摘要：只显示在 UI，默认不落盘；用户点「保存到月复盘」才写入

---

### AI 生成本周 — 流程

```
点「AI 生成…」→ 组装 context → POST 后端/本地 LLM
  → 打开预览弹窗（禁止直接写盘）
  → 用户删改/改星期
  → 「写入空位」或「替换未完成模板位」
  → upsertTask + 可选 refresh 看板
```

预览弹窗布局：

```
┌─ AI 草案 · 第 37 周 ────────────────────────┐
│ 说明：基于模板+月主线+待排灵感，补 4 条空位   │
├─────────────────────────────────────────────┤
│ 周一                                        │
│  □ 前端主块 · dev/ui · P0 · 高能  [改][删]  │
│ 周二 …                                      │
│ 待排                                        │
│  □ …                                        │
├─────────────────────────────────────────────┤
│ ⚠ 周三已有 5 条，以下 1 条需手动删          │
│ [写入空位]  [替换未完成模板位]  [取消]       │
└─────────────────────────────────────────────┘
```

交互细则：

- 按 `daySlot` 分组；`0` 组标题「待排」
- 每行可改：标题、星期下拉、优先级、大类/子类（taxonomy 白名单）
- 行内删除 = 本次不写入
- **写入空位**：仅 `instanceKey` 不冲突且该日 `dayLoad` 未超限的草案
- **替换未完成模板位**：仅替换 `status=todo` 且 `kind=template` 的同 `templateKey`+`daySlot` 实例；**已完成 / 自定义任务不碰**
- 写入后关闭弹窗，toast 写入条数

---

### 读入上下文（`buildAiWeekContext(weekId)`）

后端与前端共用同结构 JSON，便于以后 API 化：

```ts
interface AiWeekContext {
  weekId: string
  weekRange: string             // 8/31–9/6
  isNaturalCurrentWeek: boolean
  taxonomy: { categories: Category[]; subcategories: SubCategory[] }
  templates: TaskTemplate[]     // getEffectiveTemplates()
  monthGoals: string[]          // 当前月 MonthPlan.goals
  monthItemsForWeek: MonthItem[] // targetWeekId === weekId
  catalogBacklog: { templateKey; title; notes }[]
  customBacklog: { title; notes; priority }[]
  scheduledSummary: { daySlot; title; priority; status; kind }[]
  lastWeekOpen?: { title; daySlot; priority }[]  // 可选：上周未完成已排期
  dayLimits: { p0: 2; total: 5 }
}
```

**不要**把整库 tasks 全量塞给模型；只给摘要 + 白名单 id。

---

### LLM 输出约束（写进 system prompt）

1. **taxonomy 白名单**：`categoryId` / `subcategoryId` 必须来自 context，禁止发明新大类  
2. **标题**：必须是具体事项（「写登录页错误态走查」），禁止仅输出子类名（「前端 UI/交互」）  
3. **日负载**：每天 P0（must）≤ 2，总条数 ≤ 5；超限条目放 `warnings` 或 `daySlot=0`  
4. **例行任务**：「行情观察」类用一条 `scheduleKind: weekdays` + `weekdays:[1,2,3,4,5]`，**不要**生成五个不同标题  
5. **与模板关系**：优先 **补空位**（该 `templateKey+daySlot` 不存在实例）；非必要不新增与模板重复的主题  
6. **输出 JSON only**：符合 `AiWeekDraftResponse` schema，不要 markdown 包裹

示例（片段）：

```json
{
  "weekId": "2026-W37",
  "summary": "补周二内容策划细则、周三前端联调验收点",
  "items": [
    {
      "tempId": "d1",
      "title": "内容策划：本周主帖提纲 3 条",
      "categoryId": "ops",
      "subcategoryId": "ops.content",
      "priority": "must",
      "daySlot": 2,
      "slot": "focus",
      "notes": "提纲含钩子/CTA/发布时间"
    }
  ]
}
```

---

### API 契约（Console 零构建栈）

```http
POST /api/tasks/ai/draft-week
Body: AiWeekContext
Response: { success, draft: AiWeekDraftResponse, error? }

POST /api/tasks/ai/apply-week
Body: { weekId, mode: 'fill_empty' | 'replace_open_tpl', items: AiTaskDraft[] }
Response: { success, applied: number, skipped: number, errors? }

POST /api/tasks/ai/summarize-week
Body: { weekId, tasks, weekNote, monthGoals? }
Response: { success, review: WeekReview }

POST /api/tasks/ai/summarize-month
Body: { monthKey, monthPlan, weeksSummary[] }
Response: { success, review: MonthReview }
```

前端 `tasks.js` 调用方式与 `app.js` 的 `api()` 一致。  
**Phase 0（无后端）**：可用 `TasksAi.mockDraftWeek(context)` 规则生成 2–3 条演示草案，UI 与写入路径先打通。

Job 化（可选）：若 LLM 慢，返回 `{ job_id }` + 轮询，与 console 其它 Job 同模式。

---

### 写入策略（与 `applyWeeklyTemplate` 对齐）

| 模式 | 行为 |
|---|---|
| `fill_empty` | 对每个 draft：若无同 `instanceDedupKey(weekId, templateKey, daySlot)` 且 dayLimit 通过 → `upsertTask`；catalog 池 **不删** |
| `replace_open_tpl` | 仅当目标位存在 `todo` 的 template 实例 → 更新 title/notes/priority/slot；否则 fallback 到 fill_empty |
| 两者 | **不**改 `templateApplied` 时间戳逻辑；**不**动 `templateCatalog` 行；**不**改 `status=done` |

写入字段映射：

```ts
makeTask({
  weekKey: weekId,
  title, notes, categoryId, subcategoryId,
  priority, daySlot, slot,
  kind: draft.sourceHint === 'month' ? 'month' : 'custom', // AI 新增默认 custom
  templateKey: '',  // AI 草案除非用户勾选「同步为模板」否则不带 templateKey
})
```

---

### AI 归纳 — 收周

**触发**：收周列表页 / 首页「收周」流程末尾。

**读入**：该周已完成+未完成已排期任务、现有 `WeekNote.highlights`、月主线前 3 条。

**输出** `WeekReview`：

- `wins`：3 条成果（动词开头、可验证）
- `blockers`：1 条阻塞（若无则空数组）
- `carryTitles`：建议结转的任务标题（对应收周「推下周 / 月池 / 结转下月」）

**写入**：预览弹窗可编辑 → 保存到 `WeekNote.review`；可选一键把 `carryTitles` 转成收周列表高亮。

**禁止**：修改任何 `task.status=done` 的历史记录；禁止 AI 自动勾选完成。

---

### AI 归纳 — 收月

**触发**：月度页 · 历史月 / 本月收束时 `AI 归纳本月`。

**读入**：`MonthPlan.goals`、`items` 各状态、该月各周 `weekProgress` 摘要、未完成 items。

**输出** `MonthReview`：

- `goalRetrospect`：每条主线一句兑现情况（完成 / 部分 / 未动）
- `carryToNext`：建议结转到下月的标题（与「未完成结转到下月」按钮联动，**不自动结转**）
- `summary`：2–4 句总述

**写入**：`MonthPlan.review`；历史月默认只读，用户点「编辑后保存」才更新。

---

### AI 归纳 — 统计页

**触发**：统计页工具条 `AI 一句话`。

**读入**：当前 `statsPeriod` + `statsAnchor` 下的完成率、大类分布、Top 子类。

**输出**：一段中文摘要（≤120 字），例如：「9 月完成率 62%，dev 占 40%，模板完成优于自定义。」

**不写任务、不写 WeekNote**，除非用户显式「保存到月复盘」。

---

### 预览 UI 规范

- 与任务细则弹窗同组件族：`dialog.corpus-dialog.tsk-dialog`  
- 宽度略宽：`max-width: 560px`，草案列表可滚动  
- 分组标题用 `DAY_NAME[daySlot]`，待排用「待排 · 模板池」  
- 警告用 `.tsk-flow-hint.warn`，与看板日限提示一致  
- 主操作：`写入空位`（primary）；次操作：`替换未完成模板位`（ghost）；取消关闭不写入  

---

### 不要做

- 不经预览直接 `upsertTask`  
- 修改历史月已完成态、统计分母  
- 发明 taxonomy 外大类/子类  
- 用 AI 替代「模板配置」抽屉（weekdays / scheduleKind 仍手工）  
- 单独 AI 聊天页、长报告占半屏  
- 让 AI 删除用户已有任务（最多建议「替换未完成位」）

---

### 实现顺序与验收

**Phase 1 — 起草 + 写入（优先）**

1. `buildAiWeekContext` + `mockDraftWeek`（无 API 可演示）  
2. 日程栏 `AI 生成这一周` 按钮 + 预览弹窗  
3. `applyAiWeekDraft(mode)` 对接 `dayLimitWarning` / `instanceDedupKey`  
4. 验收：预览可删改；写入空位不覆盖已完成；catalog 待排仍在  

**Phase 2 — 收周归纳**

5. `AI 收周归纳` → `WeekReview` 预览 → 写入 `WeekNote.review`  
6. 验收：不改 task 完成态  

**Phase 3 — 月/统计归纳 + 真 LLM**

7. 月页 `AI 归纳本月` → `MonthReview`  
8. 统计页一句话摘要  
9. `POST /api/tasks/ai/*` 接 console 已有 LLM 配置（与 signals 等同 provider）  

**Phase 1 最小验收场景**

- 当前周已生成，周三空 1 槽 → AI 补 1 条具体任务 → 写入后周三列可见  
- 周三已满 5 条 → AI 草案带 warning，写入时跳过或改待排  
- 点取消 → localStorage 无变化  





