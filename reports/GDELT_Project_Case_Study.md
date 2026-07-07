# GDELT Event Intelligence & Forecasting Platform

## 1. Situation 项目背景

这是一个基于 GDELT 2.0 数据集的事件智能分析平台，主要用于分析 2024 年北美地区的大规模新闻事件数据。项目把原始 GDELT CSV 数据导入 MySQL，并通过 FastAPI 后端、React 前端、LangChain Agent、ChromaDB 检索和 Transformer-Hawkes Process 预测模型，提供事件查询、趋势分析、地图热点、AI 问答和未来 7 天事件风险预测等功能。

做这个项目的原因是：GDELT 数据量很大，字段复杂，直接用 CSV 或手写 SQL 分析效率很低。用户如果想知道某个国家、地区、actor 或事件类型在某段时间内的趋势，需要进行大量筛选、聚合、可视化和解释。因此项目目标是把数据库系统、AI 分析和预测模型整合到一个可交互平台中，让用户可以通过 Dashboard、Forecast 和 Analyst Chat 三种方式探索事件数据。

项目主要解决了三个问题：

- 大规模事件数据难以手动查询和理解的问题。
- 传统 dashboard 只能展示历史数据，无法提供未来风险预测的问题。
- LLM 单独回答容易缺少数据依据的问题。

## 2. Task 我的职责

这是一个 Academic Team Project。我主要负责前端交互、后端 API 集成、数据库导入与优化、Forecast 页面、Transformer-Hawkes Process 预测模型接入，以及 Chat Agent 的数据工具整合。

我的重点工作方向更偏向 AI Engineer / Backend Engineer，包括：

- 设计和调试 FastAPI 数据接口，让 Dashboard、Forecast 和 Chat 能共享同一套数据服务。
- 将 GDELT CSV 数据批量导入 Docker MySQL，并建立查询索引、空间索引和预计算 summary tables。
- 实现 Forecast 页面，并将 PyTorch Transformer-Hawkes checkpoint 接入后端 API。
- 将 Chat Agent 从早期 MCP 工具调用方式调整为基于 LangChain 的工具调用和数据分析流程。
- 使用 ChromaDB 增强语义检索，让 Chat 回答可以结合结构化 SQL 查询和非结构化新闻上下文。
- 优化 Dashboard 刷新速度、地图 hotspot drilldown、location/actor 筛选、report export 和前端可用性。

## 3. Action 我做了什么

### Backend API and Data Service

- 使用 FastAPI 组织后端接口，将 Dashboard、Forecast、Chat Analysis 等功能拆分为清晰的 API endpoint。
- 使用 Pydantic 定义请求和响应结构，保证前后端数据格式一致。
- 通过 DataService 封装数据库访问逻辑，让 Dashboard、Chat Agent 和 Forecast 共用同一套 SQL 查询层，减少重复代码。
- 调试数据库连接、缺失表、schema 不匹配等问题，确保 Chat Agent 不再因为表不存在或字段不一致而返回错误。
- 为 Forecast API 增加 target、focus mode 和 event type 参数，使用户可以按 location、actor、country pair、actor pair、all/conflict/cooperation/protest 等维度进行预测。

### Database Import and Optimization

- 将 GDELT CSV 数据批量导入 Docker MySQL，避免把大型数据库和原始数据直接放在本地项目目录或上传到 GitHub。
- 建立日期、actor、location、country pair、event type 等查询索引，提高筛选和聚合性能。
- 增加 geospatial / spatial index，用于地图热点和地理位置查询。
- 创建并使用预计算表，例如 daily_summary、geo_heatmap_grid、event_fingerprints 和 region_daily_stats，使 Dashboard 查询不需要每次扫描完整 raw events table。
- 优化 Dashboard fast path，让常用时间范围、地图热点和 top actor 查询可以更快返回。

### Frontend Dashboard and Forecast UI

- 使用 React、TypeScript、Vite 构建三页式前端：Dashboard、Forecast 和 Analyst Chat。
- 在 Dashboard 中实现 KPI cards、daily event time series、conflict rate、top actors、representative events、geographic distribution map 和 Map Hotspot Drilldown。
- 修复地图点击后 drilldown 不刷新、点击 marker 后地图缩放被重置、location 显示 unknown、report export 中 unknown 未处理等问题。
- 将 Dashboard 和 Forecast 的职责拆分：Dashboard 只展示历史数据分析，Forecast 专门展示未来 7 天预测，避免页面内容重复和加载变慢。
- 在 Dashboard 和 Forecast 输入框中增加 Location / Actor 模式选择，并支持大小写不敏感输入，例如 Canada 和 canada 输出一致。
- 在 Forecast 页面中加入单一 forecast start date，而不是日期范围；系统自动读取预测日前的历史窗口并输出未来 7 天 forecast。

### Transformer-Hawkes Process Forecasting

- 使用 PyTorch 实现并接入 Transformer-Hawkes Process 模型，用于预测未来 7 天事件数量和风险区间。
- 模型服务先加载 30 天历史 lookback，计算 rolling features，然后将最近 14 天的 feature vectors 输入 Transformer encoder。
- Transformer 部分学习历史日期之间的注意力关系，Hawkes-style head 用来建模事件 spike 之后的 excitation 和 decay。
- 模型输出 low / median / high 预测区间，而不是只给一个单点预测，使 Forecast 页面可以展示不确定性。
- 支持多个预测维度，包括 global、country、actor、country pair、actor pair、event root 和 event code。
- 支持多种事件类型预测，包括 all events、conflict、cooperation 和 protest。
- 使用 rolling validation backtest 对模型进行评估，并与 7-day moving average baseline 进行对比。

### LangChain Agent and ChromaDB RAG

- 将 Chat Agent 调整为 LangChain-style tool calling 架构，使自然语言问题可以调用后端数据工具，而不是只依赖 LLM 自由生成。
- 使用 local/router 逻辑识别用户问题中的日期、actor、location、event type 和分析意图。
- 对需要精确统计的问题调用 SQL/FastAPI 工具，例如 get_dashboard、get_time_series、search_events、get_top_events 和 forecast tool。
- 对需要背景语义的问题接入 ChromaDB，通过 sentence-transformer embeddings 检索相关新闻上下文。
- 让 Chat 回答包含 data trace / tool trace，使用户可以看到回答基于哪些工具和数据生成。

### Testing, Debugging, and Deployment

- 使用 Docker Compose 管理 MySQL、FastAPI backend 和 React frontend，使项目可以在本地较稳定运行。
- 测试 Dashboard、Forecast 和 Chat 在不同日期、不同 actor/location、不同 event type 下的返回结果。
- 验证 Forecast 页面在历史数据不足时给出提示，例如 forecast start date 早于 2024-01-31 时提示用户选择更晚日期。
- 对比 all/conflict/cooperation/protest、location/actor 模式下的 forecast 和 evaluation 是否正确变化。
- 更新 README，使其他人可以通过 Docker Compose、数据导入脚本和模型 checkpoint 运行 Forecast 页面。

## 4. Result 项目结果

- 成功构建了一个完整的 GDELT 事件智能分析平台，包含 Dashboard、Forecast 和 Analyst Chat 三个核心模块。
- 支持 2024 年北美地区大规模事件数据分析，项目数据规模达到约 17M+ events 和 82M+ articles。
- Dashboard 支持快速查看事件总量、actor 排名、时间趋势、冲突比例、地图热点和代表性事件。
- Forecast 页面可以根据指定 forecast start date、location/actor target 和 event type 输出未来 7 天事件预测。
- Transformer-Hawkes Process 模型在 rolling backtest 中将 MAE 从 167.74 降低到 83.77，相比 7-day moving average baseline 约减少 50% 预测误差。
- Chat Agent 能结合 LangChain 工具调用、SQL 查询和 ChromaDB 语义检索生成更有数据依据的回答。
- 数据库通过预计算表和索引优化后，Dashboard 常用查询可以走 fast path，减少大表扫描带来的延迟。
- 项目可以通过 Docker Compose 启动，并支持用户自行导入 GDELT CSV 数据后运行 Forecast 和 Dashboard。

## 5. 我想突出的人设

这个项目最适合突出 AI Engineer / Backend Engineer 方向。

可以强调的能力包括：

- AI Engineering: 将 LLM Agent、RAG、ChromaDB 和 THP 预测模型整合到同一个数据分析系统中。
- Backend Engineering: 使用 FastAPI、Pydantic、shared SQL layer 和 DataService 设计可复用 API 架构。
- Database Engineering: 处理大规模 GDELT 数据导入、索引设计、预计算表和空间查询优化。
- Machine Learning: 使用 PyTorch Transformer-Hawkes Process 进行时间序列事件风险预测，并通过 MAE/RMSE/backtesting 评估模型。
- Full-stack Development: 使用 React、TypeScript、ECharts 和 Leaflet 构建可交互 Dashboard 和 Forecast UI。
- Deployment: 使用 Docker Compose 管理数据库、后端和前端服务，并通过 README 规范化运行流程。

## Interview Summary 面试简短讲法

This was an academic team project where I built a GDELT event intelligence and forecasting platform. The system imports large-scale 2024 North America GDELT event data into Dockerized MySQL, exposes FastAPI data services, and provides a React dashboard, LangChain-based analyst chat, ChromaDB semantic retrieval, and a PyTorch Transformer-Hawkes forecasting module. My main contributions were database import and indexing, FastAPI data APIs, dashboard and forecast UI integration, THP model deployment, and Chat Agent tool integration. The forecasting model reduced MAE from 167.74 to 83.77 compared with a 7-day moving-average baseline, which is about a 50% error reduction.

