-- ============================================
-- 空间索引 (SPATIAL INDEX) 管理脚本
-- ============================================

-- 1. 查看当前空间索引
SELECT 
    INDEX_NAME,
    COLUMN_NAME,
    INDEX_TYPE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'gdelt'
  AND TABLE_NAME = 'events_table'
  AND INDEX_TYPE = 'SPATIAL';

-- 2. 添加空间索引（如果还没有）
-- 注意：ActionGeo_Point 列必须是 NOT NULL 且有 SRID

-- 检查 ActionGeo_Point 列属性
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'gdelt'
  AND TABLE_NAME = 'events_table'
  AND COLUMN_NAME = 'ActionGeo_Point';

-- 3. 添加空间索引（主索引）
-- 如果还没有 idx_geo_point，执行以下命令：
-- ALTER TABLE events_table 
-- ADD SPATIAL INDEX idx_geo_point (ActionGeo_Point);

-- 4. 验证空间索引
SHOW INDEX FROM events_table WHERE Index_type = 'SPATIAL';

-- ============================================
-- 空间索引使用指南
-- ============================================

-- 使用 MBRContains 进行范围查询（利用空间索引）
-- 示例：查找 Washington DC 附近 100km 内的事件
EXPLAIN SELECT * FROM events_table
WHERE MBRContains(
    ST_GeomFromText('POLYGON((38  -77.5, 39 -77.5, 39 -76.5, 38 -76.5, 38 -77.5))', 4326),
    ActionGeo_Point
)
AND SQLDATE BETWEEN '2024-01-01' AND '2024-01-31';

-- 查看查询是否使用空间索引
-- 在 Extra 列应该看到 "Using where; Using index"

-- 5. 空间索引优化提示
-- - MBRContains 可以利用空间索引
-- - ST_Distance_Sphere 不能直接用索引，但可以在 MBRContains 后使用
-- - 复合查询时，先时间过滤再空间过滤效率最高
