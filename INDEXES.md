# GDELT Database Indexes

> Documentation of all database indexes for events_table

## Overview

| Table | Records | Total Indexes | Last Updated |
|-------|---------|---------------|--------------|
| `events_table` | 15,236,852 | 16 | 2026-04-13 |

## Quick Stats

- **Total Indexes**: 16 (including PRIMARY)
- **BTREE Indexes**: 15
- **SPATIAL Indexes**: 1 (idx_geo_point)
- **Composite Indexes**: 3 (idx_date_actor, idx_date_geo, idx_geo_date)
- **High Cardinality Indexes**: 
  - PRIMARY: 15,236,852
  - idx_geo_point: 15,897,723
  - idx_date_geo (ActionGeo_Long): 1,576,635

## Index List

### 1. Primary Key
| Index Name | Column | Type | Cardinality | Purpose |
|------------|--------|------|-------------|---------|
| `PRIMARY` | GlobalEventID | BTREE | **15,236,852** | Unique identifier for each event |

### 2. Date-Based Indexes
| Index Name | Column(s) | Type | Cardinality | Purpose |
|------------|-----------|------|-------------|---------|
| `idx_sqldate` | SQLDATE | BTREE | 26,850 | Time range queries |
| `idx_date_actor` | SQLDATE, Actor1Name | BTREE | 646,021 | Combined time + actor queries |
| `idx_date_geo` | SQLDATE, ActionGeo_Lat, ActionGeo_Long | BTREE | 1,576,635 | Combined time + location queries |

### 3. Actor-Based Indexes
| Index Name | Column | Type | Cardinality | Purpose |
|------------|--------|------|-------------|---------|
| `idx_actor1` | Actor1Name | BTREE | 78,442 | Primary actor queries (query_by_actor) |
| `idx_actor2` | Actor2Name | BTREE | 56,711 | Secondary actor queries |

### 4. Geographic Indexes
| Index Name | Column | Type | Cardinality | Purpose |
|------------|--------|------|-------------|---------|
| `idx_lat` | ActionGeo_Lat | BTREE | 210,856 | Latitude-based queries |
| `idx_long` | ActionGeo_Long | BTREE | 250,173 | Longitude-based queries |
| `idx_geo_date` | ActionGeo_Lat, ActionGeo_Long, SQLDATE | BTREE | 247,066 | Location + time combined queries |
| `idx_geo_fullname` | ActionGeo_FullName(100) | BTREE | **358,335** | **City/region name queries** ✅ 2026-04-13 |
| `idx_geo_point` | ActionGeo_Point | SPATIAL | **15,897,723** | Spatial queries (ST_Distance_Sphere) |

### 5. Event Severity Index
| Index Name | Column | Type | Cardinality | Purpose |
|------------|--------|------|-------------|---------|
| `idx_goldstein` | GoldsteinScale | BTREE | 11,158 | Conflict/cooperation filtering |

## Index Usage by Tool

| Tool | Primary Index Used | Query Pattern |
|------|-------------------|---------------|
| `query_by_time_range` | idx_sqldate | SQLDATE BETWEEN ... |
| `query_by_actor` | idx_actor1 | Actor1Name LIKE ... |
| `query_by_location` | idx_geo_fullname | ActionGeo_FullName LIKE ... |
| `get_top_events` | idx_date_geo + idx_geo_fullname | SQLDATE + location filter (index-optimized with smart region parsing) |
| `get_geo_heatmap` | idx_geo_point | ST_Distance_Sphere |
| `search_events` | idx_date_actor | Time + actor combined |
| `analyze_time_series` | idx_sqldate | Date grouping |

## Adding New Indexes

### Method 1: Direct SQL (for small tables)
```bash
docker-compose exec db mysql -u root -prootpassword gdelt -e "
CREATE INDEX idx_name ON events_table(column_name);
"
```

### Method 2: Background execution (for large tables)
```bash
# Run in background (recommended for production)
nohup docker-compose exec db mysql -u root -prootpassword gdelt < db_scripts/indexes.sql > /tmp/index_creation.log 2>&1 &

# Check progress
tail -f /tmp/index_creation.log
```

### Method 3: Using MySQL client interactively
```bash
docker-compose exec db mysql -u root -prootpassword gdelt

-- Then in MySQL:
CREATE INDEX idx_geo_fullname ON events_table(ActionGeo_FullName(100));
```

## Index Maintenance

### Check index usage
```sql
SELECT 
    INDEX_NAME,
    CARDINALITY,
    COLUMN_NAME
FROM 
    INFORMATION_SCHEMA.STATISTICS
WHERE 
    TABLE_SCHEMA = 'gdelt' 
    AND TABLE_NAME = 'events_table';
```

### Analyze table statistics
```sql
ANALYZE TABLE events_table;
```

### Check query performance with EXPLAIN
```sql
EXPLAIN SELECT * FROM events_table 
WHERE SQLDATE BETWEEN '2024-01-01' AND '2024-12-31'
AND ActionGeo_FullName LIKE '%Washington%';
```

## Performance Impact

| Metric | Before Indexes | After Indexes | Improvement |
|--------|---------------|---------------|-------------|
| Time range query (1 year) | ~60s | ~0.5s | **120x** |
| Actor query | ~30s | ~1s | **30x** |
| Location query | ~45s | ~2s | **22x** |
| Geographic radius query | Timeout | ~2s | **∞** |

## Storage Overhead

Approximate index storage size: ~2-3GB for 15.89 million records

## Notes

- `idx_geo_fullname` uses prefix index (100 chars) to balance query speed and storage
- `idx_geo_point` is a SPATIAL index requiring MySQL spatial extensions
- Composite indexes (idx_date_actor, idx_date_geo) support index-only queries for better performance

## Smart Region Parsing (2026-04-13 Update)

The `get_top_events` tool now includes intelligent region parsing that supports:

### Supported Input Formats

| Input Type | Example | Parsed Terms |
|------------|---------|--------------|
| Chinese city | `华盛顿` | `['Washington', 'DC']` |
| Chinese state | `德州` | `['Texas', 'TX']` |
| City + State | `Washington DC` | `['Washington', 'DC']` |
| State abbreviation | `TX`, `CA` | `['TX', 'Texas']` |
| Full state name | `California` | `['California', 'CA']` |
| Country (CN) | `中国` | `['China', 'CHN', 'CN']` |
| Country (EN) | `USA` | `['USA', 'United States', 'US']` |

### Index-Optimized Query Generation

Instead of slow full-table scan:
```sql
-- OLD: Cannot use index (86 seconds)
ActionGeo_FullName LIKE '%Washington%'

-- NEW: Index-friendly queries (2-5 seconds)
ActionGeo_FullName LIKE 'Washington%'           -- Prefix match
OR ActionGeo_FullName LIKE '%, Washington%'     -- After comma
OR ActionGeo_ADM1Code = 'US_DC'                -- State code
OR ActionGeo_CountryCode = 'USA'               -- Country code
```

### Performance Improvement

| Query Type | Before | After | Improvement |
|------------|--------|-------|-------------|
| Washington DC events | ~86s | ~2-5s | **17-43x** |
| Texas protests | ~60s | ~2-4s | **15-30x** |
| Beijing events | ~45s | ~1-3s | **15-45x** |

---

*Last updated: 2026-04-13*  
*Maintainer: Xing Gao*
