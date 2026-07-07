-- ============================================
-- GDELT 预计算表设计
-- 目的: 加速高频查询，支持洞察生成
-- 执行: docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/precompute_tables.sql
-- ============================================

-- ============================================
-- 1. 每日摘要表 (daily_summary)
-- 用途: 快速回答"今天发生了什么"
-- 更新频率: 每日凌晨 ETL
-- ============================================
CREATE TABLE IF NOT EXISTS daily_summary (
    date DATE PRIMARY KEY COMMENT '日期',
    
    -- 基础统计
    total_events INT DEFAULT 0 COMMENT '总事件数',
    conflict_events INT DEFAULT 0 COMMENT '冲突事件数 (Goldstein < -5)',
    cooperation_events INT DEFAULT 0 COMMENT '合作事件数 (Goldstein > 5)',
    avg_goldstein FLOAT COMMENT '平均 Goldstein 指数',
    avg_tone FLOAT COMMENT '平均 Tone (情绪)',
    
    -- Top实体 (JSON格式存储Top 10)
    top_actors JSON COMMENT '[{"name": "USA", "count": 1234}, ...]',
    top_locations JSON COMMENT '[{"name": "Washington", "count": 567}, ...]',
    
    -- 事件类型分布
    event_type_distribution JSON COMMENT '{"protest": 45, "attack": 12, ...}',
    
    -- 热点事件指纹列表
    hot_event_fingerprints JSON COMMENT '["US-20240115-WDC-001", ...]',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日事件摘要';


-- ============================================
-- 2. 事件指纹表 (event_fingerprints)
-- 用途: 业务可读的事件ID、LLM生成摘要
-- 更新频率: 每日凌晨 ETL 增量生成
-- ============================================
CREATE TABLE IF NOT EXISTS event_fingerprints (
    global_event_id BIGINT PRIMARY KEY COMMENT '原始 GlobalEventID',
    
    -- 业务ID: 国家-日期-地点-类型-序号
    -- 示例: US-20240115-WDC-PROTEST-001
    fingerprint VARCHAR(50) UNIQUE COMMENT '业务可读ID',
    
    -- LLM生成的内容
    headline VARCHAR(255) COMMENT '一句话标题',
    summary TEXT COMMENT '简短摘要',
    key_actors JSON COMMENT '["美国", "伊朗"]',
    event_type_label VARCHAR(50) COMMENT '"军事对峙"',
    severity_score FLOAT COMMENT '严重度 1-10',
    
    -- 元数据
    location_name VARCHAR(100) COMMENT '可读地点名',
    location_country VARCHAR(10) COMMENT '国家代码',
    
    -- 时间戳
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    llm_version VARCHAR(20) COMMENT '模型版本',
    
    INDEX idx_fingerprint (fingerprint),
    INDEX idx_location_country (location_country),
    INDEX idx_severity (severity_score),
    INDEX idx_generated (generated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件指纹表';


-- ============================================
-- 3. 地区每日统计表 (region_daily_stats)
-- 用途: 区域态势快速查询
-- 更新频率: 每日凌晨 ETL
-- ============================================
CREATE TABLE IF NOT EXISTS region_daily_stats (
    region_code VARCHAR(10) NOT NULL COMMENT '国家代码或自定义区域代码',
    region_name VARCHAR(100) COMMENT '可读名称',
    region_type ENUM('country', 'state', 'city', 'custom') DEFAULT 'country',
    date DATE NOT NULL COMMENT '日期',
    
    -- 统计数据
    event_count INT DEFAULT 0 COMMENT '事件数',
    conflict_intensity FLOAT COMMENT '冲突强度 (加权平均)',
    cooperation_intensity FLOAT COMMENT '合作强度',
    avg_tone FLOAT COMMENT '平均情绪',
    
    -- Top事件
    top_event_fingerprint VARCHAR(50) COMMENT '最热事件指纹',
    top_event_headline VARCHAR(255) COMMENT '最热事件标题',
    
    -- 主要参与方
    primary_actors JSON COMMENT '[{"name": "USA", "count": 100}, ...]',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    PRIMARY KEY (region_code, date),
    INDEX idx_date (date),
    INDEX idx_intensity (conflict_intensity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地区每日统计';


-- ============================================
-- 4. 地理网格热点表 (geo_heatmap_grid)
-- 用途: 地图热力图预计算
-- 更新频率: 每日凌晨 ETL
-- ============================================
CREATE TABLE IF NOT EXISTS geo_heatmap_grid (
    grid_id VARCHAR(50) PRIMARY KEY COMMENT '网格ID: LAT_38.5_LNG_-77.0',
    lat_grid FLOAT NOT NULL COMMENT '纬度网格 (0.5度)',
    lng_grid FLOAT NOT NULL COMMENT '经度网格 (0.5度)',
    
    date DATE NOT NULL COMMENT '日期',
    
    event_count INT DEFAULT 0 COMMENT '事件数',
    conflict_sum INT DEFAULT 0 COMMENT '冲突事件数',
    avg_goldstein FLOAT COMMENT '平均 Goldstein',
    avg_tone FLOAT COMMENT '平均 Tone',
    
    top_event_fingerprint VARCHAR(50) COMMENT '最热事件',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_location (lat_grid, lng_grid),
    INDEX idx_date (date),
    INDEX idx_conflict (conflict_sum)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地理网格热点';


-- ============================================
-- 5. 事件主题标签表 (event_themes)
-- 用途: 主题追踪、聚类
-- 更新频率: 手动/周度
-- ============================================
CREATE TABLE IF NOT EXISTS event_themes (
    theme_id INT AUTO_INCREMENT PRIMARY KEY,
    theme_name VARCHAR(100) NOT NULL COMMENT '"俄乌冲突", "气候变化"',
    theme_keywords JSON COMMENT '["Russia", "Ukraine", "NATO"]',
    
    -- 统计
    start_date DATE COMMENT '首次出现',
    end_date DATE COMMENT '最后出现',
    total_events INT DEFAULT 0 COMMENT '关联事件数',
    
    -- 代表事件
    representative_events JSON COMMENT '[fingerprint1, fingerprint2]',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_name (theme_name),
    INDEX idx_dates (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件主题标签';


-- ============================================
-- 6. 事件主题关联表 (event_theme_mapping)
-- 用途: 事件与主题的关联
-- ============================================
CREATE TABLE IF NOT EXISTS event_theme_mapping (
    global_event_id BIGINT NOT NULL,
    theme_id INT NOT NULL,
    relevance_score FLOAT COMMENT '相关度 0-1',
    
    PRIMARY KEY (global_event_id, theme_id),
    FOREIGN KEY (theme_id) REFERENCES event_themes(theme_id),
    INDEX idx_theme (theme_id),
    INDEX idx_relevance (relevance_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件主题关联';


-- ============================================
-- 7. 事件因果链表 (event_causal_links)
-- 用途: 存储LLM分析的因果关系
-- 更新频率: 异步生成
-- ============================================
CREATE TABLE IF NOT EXISTS event_causal_links (
    link_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    cause_event_id BIGINT COMMENT '原因事件ID',
    effect_event_id BIGINT COMMENT '结果事件ID',
    
    cause_fingerprint VARCHAR(50) COMMENT '原因事件指纹',
    effect_fingerprint VARCHAR(50) COMMENT '结果事件指纹',
    
    link_type ENUM('direct', 'indirect', 'correlation') DEFAULT 'correlation',
    causal_strength FLOAT COMMENT '因果强度 0-1',
    
    llm_reasoning TEXT COMMENT 'LLM推理过程',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_cause (cause_event_id),
    INDEX idx_effect (effect_event_id),
    INDEX idx_strength (causal_strength)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件因果链';


-- ============================================
-- 视图: 事件详情完整视图
-- 基于实际的 events_table 表结构
-- ============================================
CREATE OR REPLACE VIEW event_details AS
SELECT 
    e.GlobalEventID,
    f.fingerprint,
    f.headline,
    f.summary,
    e.SQLDATE,
    e.MonthYear,
    e.DATEADDED,
    e.Actor1Name,
    e.Actor1CountryCode,
    e.Actor1Type1Code,
    e.Actor2Name,
    e.Actor2CountryCode,
    e.Actor2Type1Code,
    e.EventCode,
    e.EventRootCode,
    e.QuadClass,
    e.GoldsteinScale,
    e.NumMentions,
    e.NumSources,
    e.NumArticles,
    e.AvgTone,
    e.ActionGeo_Type,
    e.ActionGeo_FullName,
    e.ActionGeo_CountryCode,
    e.ActionGeo_Lat,
    e.ActionGeo_Long,
    e.SOURCEURL,
    f.key_actors,
    f.event_type_label,
    f.severity_score,
    f.location_name
FROM events_table e
LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id;


-- ============================================
-- 初始化: 插入今日空数据（避免首次查询报错）
-- ============================================
INSERT IGNORE INTO daily_summary (date, total_events, conflict_events, cooperation_events)
VALUES (CURDATE(), 0, 0, 0);

-- ============================================
-- 数据导入日志表 (用于增量导入)
-- ============================================
CREATE TABLE IF NOT EXISTS _import_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL UNIQUE,
    file_date DATE,
    record_count INT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('success', 'failed', 'processing') DEFAULT 'success',
    error_message TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据导入日志';
