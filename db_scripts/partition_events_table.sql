-- ============================================
-- events_table 分区改造
-- 目的: 按日期分区，提升时间范围查询性能
-- 注意: 这是一个耗时操作，建议在低峰期执行
-- ============================================

-- 查看当前表结构
-- DESCRIBE events_table;
-- SHOW CREATE TABLE events_table;

-- ============================================
-- 方案1: 创建新的分区表并迁移数据（推荐）
-- ============================================

-- Step 1: 创建分区表结构
CREATE TABLE IF NOT EXISTS events_table_partitioned (
    GlobalEventID BIGINT,
    PRIMARY KEY (GlobalEventID, Year),
    SQLDATE DATE NOT NULL,
    MonthYear INT,
    Year INT,
    FractionDate FLOAT,
    Actor1Code VARCHAR(255),
    Actor1Name VARCHAR(255),
    Actor1CountryCode VARCHAR(10),
    Actor1KnownGroupCode VARCHAR(255),
    Actor1EthnicCode VARCHAR(255),
    Actor1Religion1Code VARCHAR(255),
    Actor1Religion2Code VARCHAR(255),
    Actor1Type1Code VARCHAR(255),
    Actor1Type2Code VARCHAR(255),
    Actor1Type3Code VARCHAR(255),
    Actor2Code VARCHAR(255),
    Actor2Name VARCHAR(255),
    Actor2CountryCode VARCHAR(10),
    Actor2KnownGroupCode VARCHAR(255),
    Actor2EthnicCode VARCHAR(255),
    Actor2Religion1Code VARCHAR(255),
    Actor2Religion2Code VARCHAR(255),
    Actor2Type1Code VARCHAR(255),
    Actor2Type2Code VARCHAR(255),
    Actor2Type3Code VARCHAR(255),
    IsRootEvent INT,
    EventCode VARCHAR(10),
    EventBaseCode VARCHAR(10),
    EventRootCode VARCHAR(10),
    QuadClass INT,
    GoldsteinScale FLOAT,
    NumMentions INT,
    NumSources INT,
    NumArticles INT,
    AvgTone FLOAT,
    Actor1Geo_Type INT,
    Actor1Geo_FullName VARCHAR(255),
    Actor1Geo_CountryCode VARCHAR(10),
    Actor1Geo_ADM1Code VARCHAR(10),
    Actor1Geo_ADM2Code VARCHAR(10),
    Actor1Geo_Lat FLOAT,
    Actor1Geo_Long FLOAT,
    Actor1Geo_FeatureID VARCHAR(255),
    Actor2Geo_Type INT,
    Actor2Geo_FullName VARCHAR(255),
    Actor2Geo_CountryCode VARCHAR(10),
    Actor2Geo_ADM1Code VARCHAR(10),
    Actor2Geo_ADM2Code VARCHAR(10),
    Actor2Geo_Lat FLOAT,
    Actor2Geo_Long FLOAT,
    Actor2Geo_FeatureID VARCHAR(255),
    ActionGeo_Type INT,
    ActionGeo_FullName VARCHAR(255),
    ActionGeo_CountryCode VARCHAR(10),
    ActionGeo_ADM1Code VARCHAR(10),
    ActionGeo_ADM2Code VARCHAR(10),
    ActionGeo_Lat FLOAT,
    ActionGeo_Long FLOAT,
    ActionGeo_FeatureID VARCHAR(255),
    DATEADDED BIGINT,
    SOURCEURL TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE (Year)
(
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION pfuture VALUES LESS THAN MAXVALUE
);

-- Step 2: 从原表迁移数据（分批进行，避免锁表太久）
-- 注意: 这一步可能需要几分钟到几小时，取决于数据量
-- INSERT INTO events_table_partitioned SELECT * FROM events_table;

-- Step 3: 重命名表
-- RENAME TABLE events_table TO events_table_backup, 
--              events_table_partitioned TO events_table;

-- Step 4: 删除备份表（确认无误后执行）
-- DROP TABLE events_table_backup;

-- ============================================
-- 方案2: 按月分区（如果数据跨多个月份）
-- ============================================
/*
CREATE TABLE events_table_partitioned_monthly LIKE events_table;

ALTER TABLE events_table_partitioned_monthly
PARTITION BY RANGE COLUMNS(SQLDATE)
(
    PARTITION p202401 VALUES LESS THAN ('2024-02-01'),
    PARTITION p202402 VALUES LESS THAN ('2024-03-01'),
    PARTITION p202403 VALUES LESS THAN ('2024-04-01'),
    PARTITION p202404 VALUES LESS THAN ('2024-05-01'),
    PARTITION p202405 VALUES LESS THAN ('2024-06-01'),
    PARTITION p202406 VALUES LESS THAN ('2024-07-01'),
    PARTITION p202407 VALUES LESS THAN ('2024-08-01'),
    PARTITION p202408 VALUES LESS THAN ('2024-09-01'),
    PARTITION p202409 VALUES LESS THAN ('2024-10-01'),
    PARTITION p202410 VALUES LESS THAN ('2024-11-01'),
    PARTITION p202411 VALUES LESS THAN ('2024-12-01'),
    PARTITION p202412 VALUES LESS THAN ('2025-01-01'),
    PARTITION pfuture VALUES LESS THAN MAXVALUE
);
*/

-- ============================================
-- 分区维护命令
-- ============================================

-- 查看分区信息
-- SELECT 
--     PARTITION_NAME, 
--     TABLE_ROWS,
--     FROM_DAYS(PARTITION_DESCRIPTION) as partition_range
-- FROM INFORMATION_SCHEMA.PARTITIONS 
-- WHERE TABLE_NAME = 'events_table_partitioned';

-- 添加新分区（每年执行一次）
-- ALTER TABLE events_table_partitioned ADD PARTITION (
--     PARTITION p2026 VALUES LESS THAN (2027)
-- );

-- 分析分区表
-- ANALYZE TABLE events_table_partitioned;

-- 优化分区表
-- OPTIMIZE TABLE events_table_partitioned;
