-- 修复空间数据 SRID 不一致问题
-- 错误: st_distance_sphere given two geometries of different srids: 4326 and 0

-- 1. 检查当前的 SRID 设置
SELECT 
    ST_SRID(ActionGeo_Point) as srid,
    COUNT(*) as count
FROM events_table
WHERE ActionGeo_Point IS NOT NULL
GROUP BY ST_SRID(ActionGeo_Point);

-- 2. 修复 SRID 为 0 的数据（设置为 4326）
UPDATE events_table
SET ActionGeo_Point = ST_GeomFromText(
    ST_AsText(ActionGeo_Point),
    4326
)
WHERE ActionGeo_Point IS NOT NULL
  AND ST_SRID(ActionGeo_Point) = 0;

-- 3. 验证修复结果
SELECT 
    ST_SRID(ActionGeo_Point) as srid,
    COUNT(*) as count
FROM events_table
WHERE ActionGeo_Point IS NOT NULL
GROUP BY ST_SRID(ActionGeo_Point);

-- 4. 测试查询（应该不再报错）
SELECT 
    GlobalEventID,
    SQLDATE,
    ST_Distance_Sphere(
        ActionGeo_Point,
        POINT(-77.0369, 38.9072)  -- Washington DC
    ) / 1000 AS distance_km
FROM events_table
WHERE ActionGeo_Point IS NOT NULL
  AND ST_Distance_Sphere(
      ActionGeo_Point,
      POINT(-77.0369, 38.9072)
  ) <= 100000  -- 100km
LIMIT 5;
