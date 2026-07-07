-- 添加性能优化索引（不包括空间索引）
-- 在数据导入完成后执行

-- 1. 日期索引（最关键！所有时间范围查询都依赖这个）
ALTER TABLE events_table ADD INDEX idx_sqldate (SQLDATE);

-- 2. Actor1 名称索引（加速 GROUP BY Actor1Name）
ALTER TABLE events_table ADD INDEX idx_actor1 (Actor1Name(20));

-- 3. Actor2 名称索引
ALTER TABLE events_table ADD INDEX idx_actor2 (Actor2Name(20));

-- 4. GoldsteinScale 索引（加速冲突/合作分析）
ALTER TABLE events_table ADD INDEX idx_goldstein (GoldsteinScale);

-- 5. 经纬度索引（加速地理范围查询，虽然不是空间索引）
ALTER TABLE events_table ADD INDEX idx_lat (ActionGeo_Lat);
ALTER TABLE events_table ADD INDEX idx_long (ActionGeo_Long);

-- 6. 复合索引（常用查询组合）
-- 日期 + Actor 组合查询
ALTER TABLE events_table ADD INDEX idx_date_actor (SQLDATE, Actor1Name(20));

-- 验证索引
SHOW INDEX FROM events_table;

-- 查看表大小
SELECT 
    table_name,
    round(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.TABLES
WHERE table_schema = 'gdelt' 
  AND table_name = 'events_table';
