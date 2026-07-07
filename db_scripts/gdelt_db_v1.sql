-- 创建数据库
CREATE DATABASE IF NOT EXISTS gdelt;
USE gdelt;

-- 创建事件表
CREATE TABLE IF NOT EXISTS events_table (
    GlobalEventID BIGINT PRIMARY KEY,
    SQLDATE DATE NOT NULL,
    MonthYear INT,
    DATEADDED DATETIME,
    Actor1Name VARCHAR(255),
    Actor1CountryCode CHAR(3),
    Actor1Type1Code VARCHAR(10),
    Actor2Name VARCHAR(255),
    Actor2CountryCode CHAR(3),
    Actor2Type1Code VARCHAR(10),
    EventCode VARCHAR(10),
    EventRootCode VARCHAR(10),
    QuadClass INT,
    GoldsteinScale FLOAT,
    AvgTone FLOAT,
    NumArticles INT,
    NumMentions INT,
    NumSources INT,
    ActionGeo_Type INT,
    ActionGeo_FullName TEXT,
    ActionGeo_CountryCode CHAR(2),
    ActionGeo_Lat DECIMAL(10, 7),
    ActionGeo_Long DECIMAL(10, 7),
    SOURCEURL TEXT,
    ActionGeo_Point POINT SRID 4326
) ENGINE=InnoDB;


-- 索引在 all_indexes.sql 中统一创建
-- 空间索引在 add_spatial_indexes.sql 中创建（需先导入数据并修复 SRID）