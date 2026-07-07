-- ============================================================================
-- Dashboard Search Optimized Indexes (增量索引)
-- ============================================================================
-- 执行时机: 在基础索引(add_indexes.sql)已跑完后，再执行本文件
-- 作用:    加速 Dashboard Filter / Explore 搜索场景（地点+时间+排序）
--
-- 如果以下索引已存在，MySQL 8.0 会报错，可以用 IF NOT EXISTS 或先 DROP 再 ADD
-- ============================================================================

-- 1. Country code 精确匹配（DC、US、CA 等短代码过滤）
-- 场景: WHERE ActionGeo_CountryCode = 'DC'
-- 加速: query_search_events, query_geo_events 的 exact match 分支
CREATE INDEX IF NOT EXISTS idx_country_code ON events_table(ActionGeo_CountryCode);

-- 2. Location name 前缀匹配（LIKE 'Washington%'）
-- 场景: WHERE ActionGeo_FullName LIKE 'DC%' OR LIKE '%, DC%'
-- 加速: location_hint 模糊搜索
CREATE INDEX IF NOT EXISTS idx_location_prefix ON events_table(ActionGeo_FullName(50));

-- 3. Event root code 分类过滤（Protest/Conflict 等）
-- 场景: WHERE EventRootCode = '14'
-- 加速: event_type='protest' 过滤
CREATE INDEX IF NOT EXISTS idx_event_root ON events_table(EventRootCode);

-- 4. 日期 + Country 复合索引（常见过滤组合）
-- 场景: WHERE SQLDATE BETWEEN '2024-01-01' AND '2024-03-31' AND ActionGeo_CountryCode = 'DC'
-- 加速: 跨月份 + 地点过滤，减少回表
CREATE INDEX IF NOT EXISTS idx_date_country ON events_table(SQLDATE, ActionGeo_CountryCode);

-- 5. NumArticles 排序索引（NEW - 2026-04-27）
-- 场景: ORDER BY NumArticles DESC, ABS(GoldsteinScale) DESC LIMIT 50
-- 加速: search_events / geo_events 的结果排序，避免大量数据 filesort
CREATE INDEX IF NOT EXISTS idx_numarticles ON events_table(NumArticles);

-- ============================================================================
-- 验证索引
-- ============================================================================
SHOW INDEX FROM events_table;

-- 查看表大小
SELECT
    table_name,
    round((data_length / 1024 / 1024 / 1024), 2) AS data_size_gb,
    round((index_length / 1024 / 1024 / 1024), 2) AS index_size_gb,
    round(((data_length + index_length) / 1024 / 1024 / 1024), 2) AS total_size_gb,
    table_rows
FROM information_schema.TABLES
WHERE table_schema = 'gdelt'
  AND table_name = 'events_table';
