# GDELT 数据库脚本运行指南

> 所有脚本按以下顺序执行。**顺序很重要**，前置步骤未完成时执行后续脚本会报错或性能极差。

---

## 一、建库 + 建表（第 1 步）

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `gdelt_db_v1.sql` | 创建数据库 `gdelt` 和 `events_table` 空表 | **首次部署时执行一次** |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword < db_scripts/gdelt_db_v1.sql
```

---

## 二、导入原始数据（第 2 步）

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `import_event.py` | 将 `data/` 目录下的 CSV 导入 `events_table` | 建表后执行 |

```bash
python db_scripts/import_event.py
```

> 导入完成后建议：检查数据总量、`SQLDATE` 字段是否有值、`ActionGeo_Lat/Long` 是否为 NULL。

---

## 三、添加基础索引（第 3 步）

**必须先导入数据再建索引**，空表建索引无意义且会拖慢导入。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `add_indexes.sql` | 添加最基础、最优先的索引（日期、Actor、经纬度、复合索引） | **数据导入后立即执行** |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/add_indexes.sql
```

包含的索引：
- `idx_sqldate` — 日期范围查询（所有时间过滤都依赖它）
- `idx_actor1` / `idx_actor2` — Actor 名称过滤/分组
- `idx_goldstein` — 冲突/合作分类
- `idx_lat` / `idx_long` — 地理坐标过滤
- `idx_date_actor` — 日期 + Actor 复合查询

---

## 四、修复空间数据（第 4 步，可选）

如果后续需要使用空间索引（`SPATIAL INDEX`）或地理距离计算，先修复坐标列。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `fix_spatial_data.sql` | 清洗 `ActionGeo_Lat/Long` 异常值，填充 `ActionGeo_Point` 列 | 基础索引之后 |
| `fix_srid.sql` | 确保 `ActionGeo_Point` 的 SRID = 4326 | `fix_spatial_data.sql` 之后 |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/fix_spatial_data.sql
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/fix_srid.sql
```

---

## 五、添加搜索优化索引（第 5 步，推荐）

用于加速 **Dashboard Filter 搜索**（输入地点/演员后点 Search）和 **Explore 面板** 查询。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `add_search_indexes.sql` | 补充地点名称、国家代码、事件根代码、排序字段索引 | 基础索引之后，随时可补 |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/add_search_indexes.sql
```

包含的索引（增量）：
- `idx_country_code` — `ActionGeo_CountryCode` 精确匹配（DC、US 等）
- `idx_location_prefix` — `ActionGeo_FullName` 前缀匹配（`LIKE 'Washington%'`）
- `idx_event_root` — `EventRootCode` 分类过滤（Protest/Conflict）
- `idx_date_country` — 日期 + 国家复合索引（跨月+地点过滤）
- `idx_numarticles` — `NumArticles` 排序（避免大量数据 filesort）

> 这些索引专门解决"跨三个月搜 DC 慢"的问题。

---

## 六、添加空间索引（第 6 步，可选）

只有需要精确地理范围查询（如"华盛顿附近 100km"）时才需要。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `add_spatial_indexes.sql` | 添加 `SPATIAL INDEX` 并附使用示例 | 空间数据修复之后 |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/add_spatial_indexes.sql
```

---

## 七、表分区（第 7 步，可选，大数据量推荐）

当单表超过 **2000 万行** 或查询经常跨月份扫描大量数据时，按日期分区能显著降低扫描量。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `partition_events_table.sql` | 创建按月/按年分区的新表结构 | 数据导入后，低峰期执行 |

```bash
# 脚本里是注释掉的命令，需要手动按步骤执行
cat db_scripts/partition_events_table.sql
```

> ⚠️ 分区操作会锁表，建议在低峰期执行，且需要先建新表→导数据→重命名表。

---

## 八、创建预计算表（第 8 步）

用于加速 Dashboard 的 **Fast Path**（毫秒级响应）。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `precompute_tables.sql` | 创建 `daily_summary`、`event_fingerprints`、`region_daily_stats`、`geo_heatmap_grid` 等预计算表 | 基础索引之后即可 |

```bash
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/precompute_tables.sql
```

---

## 九、运行 ETL 填充预计算表（第 9 步，需定期执行）

预计算表创建后是空的，需要 ETL 脚本填充数据。

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `etl_pipeline.py` | 每日摘要、事件指纹、地区统计、地理网格 | **首次全量跑 + 每日增量跑** |
| `parallel_etl_pipeline.py` | 并行版 ETL，速度更快 | 数据量大时用 |

```bash
# 首次：跑历史数据（示例：跑 2024-01 整月）
python db_scripts/etl_pipeline.py 2024-01-01
python db_scripts/etl_pipeline.py 2024-01-02
# ...

# 日常：跑昨天（crontab 每天凌晨 2 点）
python db_scripts/etl_pipeline.py
```

> 只有 `daily_summary` 和 `geo_heatmap_grid` 有数据后，Dashboard 才会走 Fast Path。

---

## 十、其他维护脚本

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `backfill_fingerprints_parallel.py` | 批量生成历史事件指纹 | 首次部署或补历史数据 |
| `build_knowledge_base.py` | 构建 ChromaDB 向量知识库 | RAG 搜索功能需要时 |
| `check_db_status.py` | 检查数据库状态、表大小、索引情况 | 日常巡检 |
| `data_view.py` | 快速查看表结构和样本数据 | 调试 |
| `crontab_setup.sh` | 设置 ETL 定时任务 | 部署完成后一次 |

---

## 快速执行顺序（首次部署）

```bash
# 1. 建库建表
docker exec -i gdelt_mysql mysql -u root -prootpassword < db_scripts/gdelt_db_v1.sql

# 2. 导入 CSV
python db_scripts/import_event.py

# 3. 基础索引
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/add_indexes.sql

# 4. 搜索优化索引（解决跨月+地点慢的问题）
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/add_search_indexes.sql

# 5. 预计算表
docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt < db_scripts/precompute_tables.sql

# 6. 跑 ETL（至少跑你要查询的日期范围）
python db_scripts/etl_pipeline.py 2024-01-01

# 7. 检查状态
python db_scripts/check_db_status.py
```

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `add_indexes.sql` | **第一批必跑**的基础索引 |
| `add_search_indexes.sql` | **第二批推荐跑**的搜索优化索引（增量） |
| `add_spatial_indexes.sql` | 空间索引（可选） |
| `all_indexes.sql` | 所有索引的**总览参考版**，不建议直接执行（会重复创建） |
| `indexes.sql` | 旧版索引文件，内容已合并到 `add_indexes.sql` + `add_search_indexes.sql` |
