# Deep Dive Report 技术文档（中文版）

> **文档版本**: 2.0  
> **最后更新**: 2026-05-03  
> **项目**: GDELT Analysis Platform (Virginia Tech)

---

## 目录

1. [功能概述](#1-功能概述)
2. [架构与数据流](#2-架构与数据流)
3. [技术栈](#3-技术栈)
4. [后端组件详解](#4-后端组件详解)
5. [前端组件详解](#5-前端组件详解)
6. [API 接口](#6-api-接口)
7. [数据模型](#7-数据模型)
8. [执行流程逐步拆解](#8-执行流程逐步拆解)
9. [GKG BigQuery 集成](#9-gkg-bigquery-集成)
10. [配置与环境变量](#10-配置与环境变量)
11. [已知问题与修复记录](#11-已知问题与修复记录)
12. [文件索引](#12-文件索引)

---

## 1. 功能概述

Deep Dive Report（深度分析报告）在基础 AI 摘要之上，提供三层数据增强：

| 模块 | 数据来源 | 展示内容 |
|------|---------|---------|
| Storyline | MySQL 事件数据 + GKG 主题数据 | 时间轴、参与者演变、地点演变、主题趋势 |
| News Coverage | 事件 SOURCEURL 实时抓取 + ChromaDB 回退 | 原始新闻标题、内容摘要、来源链接 |
| GKG Insights | Google BigQuery (GDELT GKG 公开数据集) | 相关人物、组织、媒体主题、情感趋势 |

---

## 2. 架构与数据流

```
用户点击 Deep Dive Report
        |
        v
POST /api/v1/analyze/event-report
        |
        v
EnhancedReportGenerator.generate_event_report()
        |
        +--► _gather_news_coverage()  ──► NewsScraper (HTTP 抓取)
        +--► _gather_related_news()   ──► NewsScraper (批量抓取)
        +--► _gather_gkg_data()       ──► GKGClient (BigQuery)
        |
        v
build_full_storyline()  (时间轴 + 参与者 + 主题)
        |
        v
_format_enhanced_data()  (组装 LLM prompt)
        |
        v
LLM (LangChain) 生成叙事报告
        |
        v
返回 JSON 给前端
        |
        v
EventReportPanel 渲染 (摘要 + Storyline + News + GKG)
```

三个数据收集任务通过 `asyncio.gather()` 并行执行。

---

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.13, FastAPI, Uvicorn |
| LLM 框架 | LangChain, LangChain-OpenAI |
| HTTP 客户端 | aiohttp |
| HTML 解析 | BeautifulSoup4 |
| 向量数据库 | ChromaDB |
| 大数据查询 | google-cloud-bigquery |
| 认证 | google-oauth2 (service account) |
| 前端 | React 18, TypeScript, Vite |
| 图标 | Lucide React |

---

## 4. 后端组件详解

### 4.1 Enhanced Reporter

文件: `backend/agents/enhanced_reporter.py`

核心方法:

| 方法 | 功能 |
|------|------|
| `generate_event_report()` | 总调度 |
| `_find_primary_event()` | 从 step results 定位主事件（支持带后缀 key） |
| `_find_related_events()` | 从 step results 定位相关事件 |
| `_gather_news_coverage()` | 抓取主事件新闻 |
| `_gather_related_news()` | 批量抓取相关事件新闻 |
| `_gather_gkg_data()` | 查询 BigQuery |
| `_extract_events_for_storyline()` | 扁平化事件列表 |
| `_format_enhanced_data()` | 格式化 LLM prompt |
| `_parse_report_text()` | 解析 LLM 输出 |

### 4.2 Storyline Builder

文件: `backend/services/storyline_builder.py`

纯函数，无外部依赖:

| 函数 | 功能 |
|------|------|
| `build_full_storyline()` | 主入口，返回完整故事线 |
| `build_timeline()` | 按时间排序，计算重要性评分，提取里程碑 |
| `build_entity_evolution()` | 追踪参与者/地点演变 |
| `build_theme_evolution()` | 分析主题趋势 |
| `build_narrative_arc()` | 生成叙事弧线文本 |

重要性评分 (0-10):
- 媒体报道量: max 4 分
- Goldstein 强度: max 3 分
- 指纹严重度: 原始值
- 有标题+摘要: +1 分

### 4.3 News Scraper

文件: `backend/services/news_scraper.py`

- 内存 URL 缓存（TTL 1 小时）
- 最大 5 并发抓取
- 超时: 12s 总计 / 5s 连接
- 内容限制: 150-8000 字符，最大 5MB
- 智能提取: article → main → role='main' → 所有 p 标签按 class 打分
- ChromaDB 回退

### 4.4 GKG Client

文件: `backend/services/gkg_client.py`

成本控制:
- 强制 `_PARTITIONTIME` 过滤
- Dry-run 估算字节数
- 单次限制 1GB，每日限额 10GB
- 结果缓存 TTL 1 小时

查询方法:

| 方法 | 说明 |
|------|------|
| `get_event_gkg_records()` | 单日 GKG 记录 |
| `get_entity_themes()` | 实体主题查询，最多 7 天 |
| `get_cooccurring_entities()` | 共现实体查询，单日 |
| `get_tone_timeline()` | 情感趋势查询，最多 14 天 |

---

## 5. 前端组件详解

| 组件 | 文件 | 功能 |
|------|------|------|
| ExplorePanel | `frontend/src/components/ExplorePanel.tsx` | 渲染 Quick/Deep Dive 按钮 |
| EventReportPanel | `frontend/src/components/EventReportPanel.tsx` | 报告主容器 |
| StorylineTimeline | `frontend/src/components/StorylineTimeline.tsx` | 时间轴/参与者/主题 三标签 |
| NewsCoveragePanel | `frontend/src/components/NewsCoveragePanel.tsx` | 新闻来源列表 |
| GKGInsightCards | `frontend/src/components/GKGInsightCards.tsx` | GKG 数据卡片 |

---

## 6. API 接口

### POST `/api/v1/analyze/event-report`

请求体:
```json
{
  "data": {
    "event_detail_0": { "type": "event_detail", "data": { ... } },
    "similar_events_1": { "type": "similar_events", "data": [ ... ] }
  },
  "prompt": "可选自定义提示词",
  "include_storyline": true,
  "include_news": true,
  "include_gkg": true
}
```

响应:
```json
{
  "ok": true,
  "report": {
    "summary": "AI 生成的叙事报告...",
    "key_findings": ["发现 1", "发现 2"],
    "storyline": { "timeline": {...}, "entity_evolution": {...}, "theme_evolution": {...}, "narrative_arc": "..." },
    "news_coverage": { "headline": "...", "sources": [...], "has_content": true },
    "gkg_insights": { "cooccurring": {...}, "themes": {...}, "tone_timeline": [...] },
    "generated_at": "2026-05-03T01:28:30"
  },
  "elapsed_ms": 23531.8
}
```

### POST `/api/v1/analyze/storyline`

独立接口，仅获取 storyline 数据（不调用 LLM）。

---

## 7. 数据模型

### 后端 (Pydantic)

定义在 `backend/schemas/responses.py`:

| 模型 | 说明 |
|------|------|
| `EventReportRequest` | 请求体 |
| `EventReportResponse` | 响应体 |
| `EnhancedReportOutput` | 完整报告输出 |
| `StorylineData` | 故事线数据 |
| `NewsCoverageData` | 新闻覆盖数据 |
| `GKGInsightData` | GKG 洞察数据 |

### 前端 (TypeScript)

定义在 `frontend/src/types/index.ts`:

| 接口 | 说明 |
|------|------|
| `EnhancedReportResult` | 完整报告结果 |
| `StorylineData` | 故事线 |
| `NewsCoverageData` | 新闻覆盖 |
| `GKGInsightData` | GKG 洞察 |
| `TimelineEventItem` | 时间轴事件项 |

---

## 8. 执行流程逐步拆解

### 8.1 触发

用户点击 Deep Dive Report → 前端发送:
```ts
api.generateEventReport(result.data, result.plan.report_prompt)
```

`result.data` 的 key 是带后缀的（如 `event_detail_0`、`similar_events_1`）。

### 8.2 后端接收

`analyze.py` 调用 `EnhancedReportGenerator.generate_event_report()`。

### 8.3 阶段一: 并行数据收集

```python
news_coverage, related_news, gkg_data = await asyncio.gather(
    self._gather_news_coverage(data),
    self._gather_related_news(data),
    self._gather_gkg_data(data),
)
```

#### A. News Coverage

1. `_find_primary_event(data)` 扫描 key:
   - 先找 `"event_detail"` — 找不到
   - 再找 `"events"`, `"top_events"`, `"hot_events"` — 找不到
   - 扫描前缀: `"event_detail_0"` — 匹配！取出 `item["data"]`

2. `NewsScraper.fetch_for_event(primary_event)`:
   - 从 `event_data.SOURCEURL` 取 URL
   - 检查内存缓存
   - `aiohttp GET` 请求（伪装 Chrome User-Agent）
   - BeautifulSoup 解析 HTML，提取 `<article>` / `<main>` 内的 `<p>` 标签
   - 内容过滤: 150-8000 字符
   - 失败则 ChromaDB 回退

#### B. Related News

1. `_find_related_events(data)` 扫描 key:
   - 找 `"similar_events"` — 找不到
   - 扫描前缀: `"similar_events_1"` — 匹配！

2. `NewsScraper.fetch_for_events(related_events)`:
   - 批量并发抓取（共享 session，最多 5 并发）

#### C. GKG Data

1. 检查 `self._gkg.available` — 需要 `google-cloud-bigquery` 包和 GCP 凭证

2. `_find_primary_event(data)` 找到主事件

3. 提取 `SQLDATE` 和 `Actor1Name`

4. 并发查询三个接口:
   - `get_cooccurring_entities(actor, date, limit=30)`
   - `get_entity_themes(actor, (date, date+2), limit=50)`
   - `get_tone_timeline(actor, (date, date+2))`

5. 每个查询的成本保护:
   - 验证 `_PARTITIONTIME` 过滤存在
   - Dry-run 估算字节数
   - 检查 1GB/查询 和 10GB/日限额
   - 执行查询（30秒超时）
   - 记录消耗，缓存结果

### 8.4 阶段二: Storyline 构建

```python
events = self._extract_events_for_storyline(data)
# 扫描所有 key（含前缀）收集事件，按 GlobalEventID 去重

gkg_themes = gkg_data.get("themes") if gkg_data else None
storyline = build_full_storyline(events, gkg_themes)
```

内部:
- `build_timeline()`: 排序 → 计算 significance → 提取 milestones
- `build_entity_evolution()`: 统计 actor/location 的首次/末次出现、事件数、合作者、角色推断
- `build_theme_evolution()`: 分析 GKG 主题趋势（无 GKG 则返回空）
- `build_narrative_arc()`: 生成文本摘要

### 8.5 阶段三: 格式化 LLM 输入

```python
narrative_input = self._format_enhanced_data(data, news_coverage, related_news, storyline, gkg_data)
```

组装结构:
```
=== EVENT DATA ===
PRIMARY: Date: ... | Location: ... | Actors: ...

=== NEWS COVERAGE ===
Primary Headline: ...
Sources: N
Primary Article Content: ...

=== STORYLINE ===
Story Period: ...
Total Events: N
Key Milestones: ...
Key Actors: ...

=== MEDIA KNOWLEDGE GRAPH INSIGHTS ===
Related People: ...
Media Themes: ...
```

截断到 8000 字符。

### 8.6 阶段四: LLM 生成报告

```python
messages = [
    SystemMessage(content=ENHANCED_REPORT_SYSTEM_PROMPT),
    HumanMessage(content=f"{user_prompt}\n\n{narrative_input}\n\nWrite the report:"),
]
response = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=120.0)
```

System Prompt 要求:
- 清晰的新闻体写作
- 引用具体日期、名称、数字
- 不使用 JSON
- 数据稀疏时直接说明

### 8.7 阶段五: 解析与返回

```python
summary, findings = self._parse_report_text(text)
# 按行遍历，遇到 "Key Finding" / "Findings" 等标记进入 findings 模式

return EnhancedReportResult(
    summary=summary,
    key_findings=findings,
    storyline=storyline,
    news_coverage=news_coverage,
    gkg_insights=gkg_data,
)
```

### 8.8 阶段六: 前端渲染

```tsx
// EventReportPanel.tsx
const hasStoryline = !!report.storyline;
const hasNews = !!report.news_coverage?.has_content;
const hasGKG = !!report.gkg_insights;

// 渲染:
// 1. 摘要段落
// 2. 关键发现列表
// 3. 数据徽章: Storyline | News Coverage | GKG Insights
// 4. StorylineTimeline 组件（三标签页）
// 5. NewsCoveragePanel（来源列表）
// 6. GKGInsightCards（人物/组织/主题/情感图）
```

---

## 9. GKG BigQuery 集成

### 9.1 GKG 是什么

GDELT Global Knowledge Graph (GKG) 是独立于 Events 数据库的数据集，包含:
- V2Persons: 新闻中提到的人物
- V2Orgs: 组织
- V2Themes: 主题（如 PROTEST, ECON_INFLATION）
- V2Tone: 情感分数
- V2Locations: 地点

公开数据集: `gdelt-bq.gdeltv2.gkg_partitioned`

### 9.2 为什么需要 GCP 认证

GKG 数据集**免费**，但 Google Cloud 要求认证才能访问 BigQuery:

**方案一: Service Account（生产推荐）**
1. 创建 GCP 项目
2. 启用 BigQuery API
3. 创建 Service Account，授予 `BigQuery Data Viewer` + `BigQuery Job User`
4. 下载 JSON key
5. 设置 `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`

**方案二: Application Default Credentials（本地开发）**
```bash
gcloud auth application-default login
```

### 9.3 成本

| 项目 | 费用 |
|------|------|
| GKG 数据集 | 免费 |
| BigQuery 按需计费 | $5/TB |
| 每日限额 | 10GB (~$0.05/天) |
| 单次查询限额 | 1GB |
| 无分区过滤 | ~3.6TB/查询 (~$18) |

### 9.4 配置步骤

1. 创建 GCP 项目并启用 BigQuery API
2. 创建 Service Account 并下载 key
3. `.env` 中添加:
```bash
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gkg-service-account.json
BIGQUERY_PROJECT_ID=your-gcp-project-id
```
4. Docker 挂载 secrets 目录
5. 验证: 查看后端日志 `[GKGClient] BigQuery client initialized`

### 9.5 无 GCP 的降级行为

- `gkg_client.available` 返回 `false`
- `_gather_gkg_data()` 返回 `None`
- `theme_evolution` 返回空数组
- 前端显示: "GKG BigQuery data not available. Configure GCP credentials..."
- Deep Dive 仍可生成 Summary + Storyline + News Coverage

---

## 10. 配置与环境变量

### 必需

| 变量 | 说明 |
|------|------|
| `KIMI_CODE_API_KEY` | LLM API key（或 `OPENAI_API_KEY`, `MOONSHOT_API_KEY`） |

### 可选（GKG 专用）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GOOGLE_APPLICATION_CREDENTIALS` | — | GCP Service Account JSON 路径 |
| `BIGQUERY_PROJECT_ID` | — | GCP 项目 ID |
| `BIGQUERY_DAILY_GB_LIMIT` | 10 | 每日查询预算 (GB) |
| `BIGQUERY_QUERY_TIMEOUT_SEC` | 30 | 查询超时 |
| `GKG_CACHE_TTL_SEC` | 3600 | 结果缓存 TTL |

---

## 11. 已知问题与修复记录

### 问题 1: Key 匹配失败导致数据为空

**状态**: 已修复 (2026-05-03)

**现象**: News Coverage、Storyline 始终为空

**根因**: 代码查找 `"event_detail"`、`"similar_events"` 等 key，但实际 key 是 `"event_detail_0"`、`"similar_events_1"`（带后缀）

**修复**: 添加 `_find_primary_event()` 和 `_find_related_events()` 方法，同时扫描精确 key 和前缀 key

**修改文件**: `backend/agents/enhanced_reporter.py`

### 问题 2: `dict` 对象没有 `narrative_arc` 属性

**状态**: 已修复 (2026-05-03)

**根因**: `build_full_storyline()` 返回 dict，但代码把它当对象调用 `.to_dict()` 和 `.narrative_arc`

**修复**: 改为兼容写法:
```python
storyline.get("narrative_arc") if isinstance(storyline, dict) else storyline.narrative_arc
```

**修改文件**: `backend/agents/enhanced_reporter.py`

### 问题 3: 缺少 `google-cloud-bigquery` 包

**状态**: 已修复 (2026-05-03)

**现象**: GKG 初始化失败: `cannot import name 'bigquery' from 'google.cloud'`

**修复**: 在 Docker 容器中安装
```bash
docker exec gdelt_backend pip install google-cloud-bigquery
```

**注意**: 容器重启后需重新安装（未写入 Dockerfile）

### 问题 4: Docker 代码同步

**现象**: 主机代码修改后容器内未生效

**解决**: 修改后重启容器
```bash
docker restart gdelt_backend
```

---

## 12. 文件索引

### 后端

| 文件 | 行数 | 用途 |
|------|------|------|
| `backend/agents/enhanced_reporter.py` | ~520 | 主报告生成器 |
| `backend/services/storyline_builder.py` | 435 | 故事线构建 |
| `backend/services/news_scraper.py` | 445 | 新闻抓取 |
| `backend/services/gkg_client.py` | 731 | BigQuery 客户端 |
| `backend/routers/analyze.py` | 251 | API 路由 |
| `backend/schemas/responses.py` | 511 | Pydantic 模型 |

### 前端

| 文件 | 行数 | 用途 |
|------|------|------|
| `frontend/src/components/ExplorePanel.tsx` | 508 | 主探索 UI |
| `frontend/src/components/EventReportPanel.tsx` | 106 | 报告容器 |
| `frontend/src/components/StorylineTimeline.tsx` | 365 | 时间轴组件 |
| `frontend/src/components/NewsCoveragePanel.tsx` | 116 | 新闻面板 |
| `frontend/src/components/GKGInsightCards.tsx` | 156 | GKG 卡片 |
| `frontend/src/api/client.ts` | 118 | API 客户端 |
| `frontend/src/types/index.ts` | 285 | TypeScript 类型 |
