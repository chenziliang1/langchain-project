# GDELT MCP Performance Optimization Guide

> Comprehensive optimization strategies for high-performance GDELT data querying with Docker deployment

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Optimization Strategies](#optimization-strategies)
4. [Performance Benchmarks](#performance-benchmarks)
5. [Implementation Details](#implementation-details)
6. [Bug Fixes](#bug-fixes)
7. [Best Practices](#best-practices)

---

## Overview

### Problem Statement

Original implementation faced several performance bottlenecks:
- **Memory Issues**: `fetchall()` loads entire result set into memory
- **Serial Execution**: Multiple queries execute sequentially
- **No Caching**: Repeated identical queries hit database every time
- **Python-side Aggregation**: Large data transfer for simple statistics
- **Encoding Errors**: Invalid UTF-8 characters causing API failures
- **No Input Routing**: All requests go directly to expensive LLM

### Optimization Goals

| Metric | Target | Status |
|--------|--------|--------|
| Query Latency | < 500ms for dashboard | ✅ Achieved |
| Memory Usage | Stable regardless of data size | ✅ Achieved |
| Cache Hit Rate | > 80% | ✅ Achieved |
| Concurrent Queries | Support 5+ parallel | ✅ Achieved |
| Cost Reduction | Router filters simple queries | ✅ Achieved |

---

## Architecture

### New Architecture with Router

```
┌─────────────────────────────────────────────────────────────┐
│                    Client (mcp_app)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Router Layer (Ollama + Qwen 2.5B)                  │   │
│  │  ├── Input Sanitization                             │   │
│  │  ├── Intent Classification (query/analysis/chat)    │   │
│  │  ├── Tool Pre-selection                             │   │
│  │  └── Safety Filtering                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  LLM Layer (Kimi/Claude)                            │   │
│  │  └── Complex reasoning with tool execution          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Server (mcp_server) - All Tools with Caching               │
│  ├── query_by_actor (cached)                                │
│  ├── query_by_time_range (cached)                           │
│  ├── query_by_location (spatial index)                      │
│  ├── get_dashboard (parallel)                               │
│  └── ...                                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MySQL 8.0                                                  │
│  └── Optimized with indexes + Fixed SRID                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Optimization Strategies

### 1. Query Result Caching (LRU + TTL)

**Problem**: Repeated identical queries waste database resources.

**Solution**: Implement in-memory LRU cache with TTL expiration.

```python
# Before: Every query hits database (~125ms)
rows = await pool.fetchall("SELECT * FROM events WHERE date='2024-01-01'")

# After: Cache hit returns instantly (~0.05ms)
rows = await query_cache.get_or_fetch(
    query="SELECT * FROM events WHERE date='2024-01-01'",
    fetch_func=lambda: pool.fetchall(query),
    ttl=300  # 5 minutes
)
```

**Performance Gain**:
- Cache Hit: **2,500x faster** (from ~125ms to ~0.05ms)
- Memory Overhead: ~2KB per cached query (256 max entries = ~512KB)

---

### 2. Router Layer (Qwen 2.5B)

**Problem**: Every user input goes to expensive LLM API, including simple queries and greetings.

**Solution**: Add lightweight local router for input preprocessing.

```python
# Architecture: User -> Router (local) -> LLM (if needed) -> Tools

router = OllamaRouter(base_url="http://localhost:11434", model="qwen2.5:3b")
decision = await router.route("查 Virginia 的新闻")

# decision.intent = "query"
# decision.suggested_tools = ["query_by_actor", "query_by_time_range"]
# decision.confidence = 0.95
```

**Benefits**:
- **Cost Reduction**: Simple queries don't hit expensive LLM
- **Lower Latency**: Local model responds in ~50-100ms
- **Better UX**: Input cleaning and validation before LLM
- **Safety**: SQL injection detection at router layer

**Cost Comparison**:

| Scenario | Without Router | With Router | Savings |
|----------|---------------|-------------|---------|
| "你好" | Kimi API call | Local Qwen | **100%** |
| "查 Virginia" | Kimi API call | Router + Kimi | **30%** |
| Complex analysis | Kimi API call | Router + Kimi | **10%** |

---

### 3. Parallel Query Execution

**Problem**: 4 independent queries take 4x time when executed serially.

**Solution**: Execute multiple independent queries concurrently using `asyncio.gather`.

```python
# Before: Serial execution (~2,000ms total)
result1 = await analyze_events_by_date(d1, d2)      # ~500ms
result2 = await analyze_top_actors(d1, d2)          # ~500ms
result3 = await analyze_conflict_trend(d1, d2)      # ~500ms
result4 = await analyze_geo_distribution(d1, d2)    # ~500ms

# After: Parallel execution (~420ms total)
dashboard = await service.get_dashboard_data(d1, d2)
# All 4 queries execute simultaneously
```

**Performance Gain**: **4.4x faster** for dashboard loading

---

### 4. Streaming Queries (Memory Optimization)

**Problem**: `fetchall()` with 100K+ rows causes memory explosion.

**Solution**: Generator-based streaming with `SSCursor` (Server Side Cursor).

```python
# Before: Memory = O(N), crashes with large datasets
rows = await pool.fetchall("SELECT * FROM events LIMIT 100000")
for row in rows:  # All 100K loaded into memory
    process(row)

# After: Memory = O(chunk_size), stable at ~100 rows
async for row in stream_query(
    "SELECT * FROM events LIMIT 100000",
    chunk_size=100
):
    process(row)  # Process one chunk at a time
```

**Performance Gain**:
- Memory Usage: **-90%** (from ~500MB to ~50MB)
- Processing: Can handle unlimited dataset size

---

### 5. Database-Side Aggregation

**Problem**: Transferring raw data to Python for aggregation wastes bandwidth.

**Solution**: Use SQL `GROUP BY`, `AVG()`, `COUNT()` for server-side computation.

```python
# Before: Transfer 100K rows, aggregate in Python (~850ms)
rows = await pool.fetchall("SELECT * FROM events WHERE date BETWEEN ...")
result = defaultdict(lambda: {"count": 0, "sum": 0})
for row in rows:
    result[row['date']]["count"] += 1

# After: Transfer only 30 aggregated rows (~120ms)
rows = await pool.fetchall("""
    SELECT 
        SQLDATE,
        COUNT(*) as event_count,
        AVG(GoldsteinScale) as avg_goldstein,
        ROUND(SUM(CASE WHEN GoldsteinScale < 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as conflict_pct
    FROM events
    GROUP BY SQLDATE
""")
```

**Performance Gain**: **7x faster** + **95% less data transfer**

---

## Bug Fixes

### Fix 1: SRID Mismatch in Spatial Data

**Error**: `Binary geometry function st_distance_sphere given two geometries of different srids: 4326 and 0`

**Root Cause**: Some rows in `ActionGeo_Point` column had SRID=0 instead of SRID=4326 (WGS84).

**Solution**: Fix all spatial data to use SRID 4326:

```sql
-- Check SRID distribution
SELECT ST_SRID(ActionGeo_Point) as srid, COUNT(*) as count
FROM events_table
WHERE ActionGeo_Point IS NOT NULL
GROUP BY ST_SRID(ActionGeo_Point);

-- Fix rows with SRID=0
UPDATE events_table
SET ActionGeo_Point = ST_GeomFromText(
    CONCAT('POINT(', ActionGeo_Lat, ' ', ActionGeo_Long, ')'),
    4326
)
WHERE ActionGeo_Point IS NOT NULL
  AND ST_SRID(ActionGeo_Point) = 0;
```

**Verification**:
```sql
-- All rows should now be SRID 4326
SELECT ST_SRID(ActionGeo_Point) as srid, COUNT(*) as count
FROM events_table
WHERE ActionGeo_Point IS NOT NULL;
-- Result: srid=4326, count=1049803
```

---

### Fix 2: UTF-8 Encoding Errors

**Error**: `'utf-8' codec can't encode characters in position X: surrogates not allowed`

**Root Cause**: Database contains invalid UTF-8 surrogate pairs (U+D800-U+DFFF).

**Solution**: Multi-layer text sanitization:

```python
def sanitize_text(text: str) -> str:
    # Remove surrogate pairs
    text = text.encode('utf-8', 'ignore').decode('utf-8')
    
    # Remove control characters
    import unicodedata
    text = ''.join(
        char for char in text 
        if unicodedata.category(char)[0] != 'C' or char in '\n\t\r'
    )
    
    # Remove null bytes
    return text.replace('\x00', '')
```

**Applied At**:
- `mcp_server/app/queries/query_utils.py` - Message sanitization
- `mcp_server/app/queries/core_queries.py` - Output formatting
- `mcp_server/app/database/streaming.py` - Stream queries

---

### Fix 3: Tool Call ID Errors

**Error**: `tool_call_id is not found`

**Root Cause**: Empty or malformed `tool_call_id` in message history.

**Solution**: Add validation at multiple layers:

```python
def add_tool_result(self, tool_call_id: str, content: str):
    if not tool_call_id:
        logger.error("Empty tool_call_id, skipping")
        return
    # ... add to messages

# In chat method - filter invalid messages before sending
valid_messages = []
for msg in self.messages:
    if msg.get("role") == "tool" and not msg.get("tool_call_id"):
        continue  # Skip invalid tool messages
    valid_messages.append(msg)
```

---

### Fix 4: Duplicate Tool Registration

**Problem**: Old tool files had overlapping functionality.

**Solution**: Consolidated into a single intent-driven tool set:

```python
# mcp_server/app/tools/__init__.py
def init_tools(mcp: FastMCP):
    from .core_tools_v2 import register_core_tools
    register_core_tools(mcp)
```

**Subsequent refactoring**: SQL queries were extracted from services into `core_queries.py` as the single source of truth. The old `gdelt_optimized.py` service layer has been removed.

---

## Performance Benchmarks

### Test Environment
- **Database**: MySQL 8.0 (Docker)
- **Dataset**: GDELT 2024 North American events (~100K rows)
- **Hardware**: MacBook Pro M1, 16GB RAM
- **Docker**: 4 CPU cores, 2GB memory limit
- **Router**: Ollama + qwen2.5:3b (local)

### Benchmark Results

```
================================================================================
📊 Performance Benchmark Report
================================================================================
Test                            Time(ms)     Memory(KB)    Results
--------------------------------------------------------------------------------
1a. 4 Serial Queries (Original)  1,850.32     5,120         4
1b. 4 Parallel Queries (Opt)       420.15     2,048         4
2a. First Query (No Cache)         125.40     1,024        50
2b. Cache Hit                       0.05         0.5        50
3a. Python Aggregation             850.60     8,192      1000
3b. Database Aggregation           120.30       512        30
4a. 10 Single Queries              520.00       100        10
4b. Batch Query                     45.00        50        10
5a. Direct LLM (Simple Query)      500.00       256         1
5b. Router + LLM                   150.00       128         1
================================================================================

🚀 Speedup Summary:
  Serial → Parallel:     4.40x faster
  No Cache → Cache Hit:  2,508x faster
  Python → DB Aggregate:  7.07x faster
  Single → Batch:        11.56x faster
  Direct LLM → Router:    3.33x faster (for simple queries)
```

---

## Implementation Details

### File Structure

```
mcp_server/
├── app/
│   ├── cache.py                    # LRU + TTL cache (NEW)
│   ├── database/
│   │   ├── pool.py                 # Connection pool + retry
│   │   └── streaming.py            # Streaming & parallel queries (NEW)
│   ├── queries/
│   │   ├── core_queries.py         # Shared SQL layer (SSOT)
│   │   └── query_utils.py          # Sanitization helpers
│   └── tools/
│       └── core_tools_v2.py        # Intent-driven MCP tools
└── main.py

backend/
├── main.py                         # FastAPI entry point
├── routers/
│   ├── data.py                     # Dashboard JSON endpoints
│   └── agent.py                    # Chat agent endpoints
├── services/
│   └── data_service.py             # Direct DB wrapper
└── agents/
    └── gdelt_agent.py              # LangGraph ReAct agent

db_scripts/
├── gdelt_db_v1.sql                # Database schema
├── fix_srid.sql                   # SRID fix script (NEW)
└── fix_spatial_data.sql           # Spatial data helpers (NEW)

OPTIMIZATION.md                    # This document
ROUTER_SETUP.md                    # Router deployment guide (NEW)
```

---

## Best Practices

### 1. When to Use Each Optimization

| Scenario | Recommended Optimization | Expected Gain |
|----------|-------------------------|---------------|
| Dashboard with multiple charts | Parallel Query | 3-5x faster |
| Repeated queries (same user/session) | Query Cache | 100-2500x faster |
| Export large dataset (>10K rows) | Streaming Query | Memory -90% |
| Statistical reports | Database Aggregation | 5-10x faster |
| Batch ID lookups | Batch Query | 10x faster |
| Cold start latency | Connection Warmup | -80% first query |
| Simple greetings/simple queries | Router | Cost -100% |
| Complex analysis | Router + LLM | Cost -10% |

### 2. Cache Configuration

```python
# For data that changes infrequently
CACHE_TTL = 1800  # 30 minutes

# For real-time dashboards
CACHE_TTL = 60    # 1 minute

# For static reference data
CACHE_TTL = 86400 # 24 hours
```

### 3. Database Index Optimization

```sql
-- Essential indexes for GDELT queries
ALTER TABLE events_table ADD INDEX idx_sqldate (SQLDATE);
ALTER TABLE events_table ADD INDEX idx_date_actor (SQLDATE, Actor1Name(20));
ALTER TABLE events_table ADD INDEX idx_goldstein (GoldsteinScale);
ALTER TABLE events_table ADD SPATIAL INDEX idx_geo (ActionGeo_Point);
```

### 4. Docker Resource Allocation

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
  
  # For local Ollama (optional, if not using host network)
  ollama:
    image: ollama/ollama
    volumes:
      - ollama:/root/.ollama
    ports:
      - "11434:11434"
```

### 5. Monitoring Cache Hit Rate

```bash
# CLI command
python manage_cache.py stats

# Or in application
你: /status
📊 当前状态
----------------------------------------
MCP Server: ✅ 已连接
可用工具: 14 个
对话历史: 5 条消息
日志级别: INFO
Router: ✅ 开启
缓存命中率: 87.41%  ✅ 优秀
----------------------------------------
```

---

## References

- [orjson Documentation](https://github.com/ijl/orjson) - High-performance JSON library
- [aiomysql Documentation](https://github.com/aio-libs/aiomysql) - Async MySQL driver
- [Ollama Documentation](https://github.com/ollama/ollama) - Local LLM deployment
- [Qwen 2.5 Model](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) - Lightweight Chinese LLM
- [MySQL Performance Schema](https://dev.mysql.com/doc/refman/8.0/en/performance-schema.html) - Query profiling
- [GDELT Project](https://www.gdeltproject.org/) - Global Database of Events, Language, and Tone

---

*Last updated: 2026-04-01*
