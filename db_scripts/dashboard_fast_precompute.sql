-- Fast dashboard precompute helpers.
-- Usage:
--   docker exec -i gdelt_mysql mysql -uroot -prootpassword gdelt < db_scripts/dashboard_fast_precompute.sql

SET SESSION sql_log_bin = 0;

SET @daily_summary_total_articles_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'daily_summary'
    AND COLUMN_NAME = 'total_articles'
);
SET @daily_summary_total_articles_ddl := IF(
  @daily_summary_total_articles_exists = 0,
  'ALTER TABLE daily_summary ADD COLUMN total_articles BIGINT DEFAULT 0',
  'SELECT 1'
);
PREPARE daily_summary_total_articles_stmt FROM @daily_summary_total_articles_ddl;
EXECUTE daily_summary_total_articles_stmt;
DEALLOCATE PREPARE daily_summary_total_articles_stmt;

UPDATE daily_summary ds
JOIN (
  SELECT SQLDATE, SUM(NumArticles) AS total_articles
  FROM events_table FORCE INDEX (idx_sqldate)
  GROUP BY SQLDATE
) src ON src.SQLDATE = ds.date
SET ds.total_articles = COALESCE(src.total_articles, 0);

CREATE TABLE IF NOT EXISTS representative_events_daily (
  SQLDATE DATE NOT NULL,
  event_bucket VARCHAR(20) NOT NULL DEFAULT 'all',
  rank_num INT NOT NULL,
  GlobalEventID BIGINT NOT NULL,
  Actor1Name VARCHAR(255),
  Actor2Name VARCHAR(255),
  ActionGeo_FullName VARCHAR(255),
  ActionGeo_CountryCode VARCHAR(10),
  EventRootCode VARCHAR(10),
  GoldsteinScale FLOAT,
  NumArticles INT,
  NumSources INT,
  AvgTone FLOAT,
  SOURCEURL TEXT,
  heat_score DOUBLE NOT NULL,
  PRIMARY KEY (SQLDATE, event_bucket, rank_num, GlobalEventID),
  KEY idx_bucket_heat (event_bucket, heat_score DESC),
  KEY idx_event_id (GlobalEventID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELETE FROM representative_events_daily WHERE event_bucket = 'all';

INSERT INTO representative_events_daily (
  SQLDATE, event_bucket, rank_num, GlobalEventID,
  Actor1Name, Actor2Name, ActionGeo_FullName, ActionGeo_CountryCode,
  EventRootCode, GoldsteinScale, NumArticles, NumSources, AvgTone, SOURCEURL,
  heat_score
)
SELECT
  SQLDATE, 'all', rank_num, GlobalEventID,
  Actor1Name, Actor2Name, ActionGeo_FullName, ActionGeo_CountryCode,
  EventRootCode, GoldsteinScale, NumArticles, NumSources, AvgTone, SOURCEURL,
  heat_score
FROM (
  SELECT
    e.SQLDATE,
    ROW_NUMBER() OVER (
      PARTITION BY e.SQLDATE
      ORDER BY COALESCE(e.NumArticles, 0) * ABS(COALESCE(e.GoldsteinScale, 0)) DESC, e.GlobalEventID DESC
    ) AS rank_num,
    e.GlobalEventID,
    e.Actor1Name,
    e.Actor2Name,
    e.ActionGeo_FullName,
    e.ActionGeo_CountryCode,
    e.EventRootCode,
    e.GoldsteinScale,
    e.NumArticles,
    e.NumSources,
    e.AvgTone,
    e.SOURCEURL,
    COALESCE(e.NumArticles, 0) * ABS(COALESCE(e.GoldsteinScale, 0)) AS heat_score
  FROM events_table e FORCE INDEX (idx_sqldate)
) ranked
WHERE rank_num <= 25;

CREATE TABLE IF NOT EXISTS geo_heatmap_location_labels (
  precision_level INT NOT NULL,
  lat_grid DECIMAL(10,4) NOT NULL,
  lng_grid DECIMAL(10,4) NOT NULL,
  sample_location VARCHAR(255) NOT NULL,
  event_count INT NOT NULL,
  PRIMARY KEY (precision_level, lat_grid, lng_grid),
  KEY idx_precision_count (precision_level, event_count DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELETE FROM geo_heatmap_location_labels WHERE precision_level = 2;

INSERT INTO geo_heatmap_location_labels (
  precision_level, lat_grid, lng_grid, sample_location, event_count
)
SELECT
  2 AS precision_level,
  lat_grid,
  lng_grid,
  ActionGeo_FullName AS sample_location,
  event_count
FROM (
  SELECT
    ROUND(ActionGeo_Lat, 2) AS lat_grid,
    ROUND(ActionGeo_Long, 2) AS lng_grid,
    ActionGeo_FullName,
    COUNT(*) AS event_count,
    ROW_NUMBER() OVER (
      PARTITION BY ROUND(ActionGeo_Lat, 2), ROUND(ActionGeo_Long, 2)
      ORDER BY COUNT(*) DESC, ActionGeo_FullName ASC
    ) AS rank_num
  FROM events_table FORCE INDEX (idx_date_geo)
  WHERE ActionGeo_Lat IS NOT NULL
    AND ActionGeo_Long IS NOT NULL
    AND ActionGeo_FullName IS NOT NULL
    AND ActionGeo_FullName <> ''
  GROUP BY ROUND(ActionGeo_Lat, 2), ROUND(ActionGeo_Long, 2), ActionGeo_FullName
) ranked_locations
WHERE rank_num = 1;
