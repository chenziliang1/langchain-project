-- ============================================
-- GDELT 数据库完整索引方案（总览参考版）
-- ============================================
-- 本文件汇总了所有推荐的索引，方便总览参考。
-- 实际执行请按 README.md 的顺序，分步骤使用增量脚本，
-- 避免重复创建导致报错。
--
-- 适用数据量: 1500万+
-- 最后更新:   2026-04-27
-- ============================================

-- ------------------------------------------------------------------
-- 基础索引（第一批：数据导入后立即执行）
-- 脚本: add_indexes.sql
-- ------------------------------------------------------------------
ALTER TABLE events_table ADD INDEX idx_sqldate (SQLDATE);
ALTER TABLE events_table ADD INDEX idx_actor1 (Actor1Name(20));
ALTER TABLE events_table ADD INDEX idx_actor2 (Actor2Name(20));
ALTER TABLE events_table ADD INDEX idx_goldstein (GoldsteinScale);
ALTER TABLE events_table ADD INDEX idx_lat (ActionGeo_Lat);
ALTER TABLE events_table ADD INDEX idx_long (ActionGeo_Long);
ALTER TABLE events_table ADD INDEX idx_date_actor (SQLDATE, Actor1Name(20));

-- ------------------------------------------------------------------
-- 复合索引（第二批：基础索引之后）
-- 脚本: all_indexes.sql 或单独执行
-- ------------------------------------------------------------------
ALTER TABLE events_table ADD INDEX idx_geo_date (ActionGeo_Lat, ActionGeo_Long, SQLDATE);
ALTER TABLE events_table ADD INDEX idx_date_geo (SQLDATE, ActionGeo_Lat, ActionGeo_Long);

-- ------------------------------------------------------------------
-- 搜索优化索引（第三批：Dashboard Filter / Explore 搜索场景）
-- 脚本: add_search_indexes.sql
-- ------------------------------------------------------------------
ALTER TABLE events_table ADD INDEX idx_country_code (ActionGeo_CountryCode);
ALTER TABLE events_table ADD INDEX idx_location_prefix (ActionGeo_FullName(50));
ALTER TABLE events_table ADD INDEX idx_event_root (EventRootCode);
ALTER TABLE events_table ADD INDEX idx_date_country (SQLDATE, ActionGeo_CountryCode);
ALTER TABLE events_table ADD INDEX idx_numarticles (NumArticles);

-- ------------------------------------------------------------------
-- 空间索引（第四批：需先修复 SRID 并确保列 NOT NULL）
-- 脚本: add_spatial_indexes.sql
-- ------------------------------------------------------------------
-- ALTER TABLE events_table ADD SPATIAL INDEX idx_geo_point (ActionGeo_Point);

-- ============================================
-- 验证
-- ============================================
SHOW INDEX FROM events_table;

SELECT
    table_name,
    round((data_length / 1024 / 1024 / 1024), 2) AS data_size_gb,
    round((index_length / 1024 / 1024 / 1024), 2) AS index_size_gb,
    round(((data_length + index_length) / 1024 / 1024 / 1024), 2) AS total_size_gb,
    table_rows
FROM information_schema.TABLES
WHERE table_schema = 'gdelt'
  AND table_name = 'events_table';

-- ============================================
-- 索引使用指南
-- ============================================
--
-- 1. 简单时间查询: 使用 idx_sqldate
--    WHERE SQLDATE BETWEEN '2024-01-01' AND '2024-01-31'
--
-- 2. 按演员查询: 使用 idx_actor1
--    WHERE Actor1Name LIKE 'USA%'
--
-- 3. 地理+时间查询: 使用 idx_geo_date 或 idx_date_geo
--    WHERE SQLDATE BETWEEN ... AND ActionGeo_Lat BETWEEN ...
--
-- 4. 地点名称过滤: 使用 idx_location_prefix
--    WHERE ActionGeo_FullName LIKE 'Washington%'
--
-- 5. 国家代码过滤: 使用 idx_country_code
--    WHERE ActionGeo_CountryCode = 'US'
--
-- 6. 跨月+地点复合: 使用 idx_date_country
--    WHERE SQLDATE BETWEEN ... AND ActionGeo_CountryCode = 'DC'
--
-- 7. 按热度排序: 使用 idx_numarticles
--    ORDER BY NumArticles DESC LIMIT 50
--
-- 8. 热力图聚合: 使用 idx_geo_date
--    先按日期过滤，再按地理聚合
--
-- 9. Dashboard 并行查询: 多个索引同时使用
