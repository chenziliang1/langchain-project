#!/bin/bash
# Docker 容器内并行补全指纹
# 用法: ./backfill_docker.sh [workers] [start_date] [end_date]

WORKERS=${1:-8}
START_DATE=${2:-"2024-01-01"}
END_DATE=${3:-"2024-12-31"}

echo "=================================="
echo "🐳 Docker 容器内指纹补全"
echo "=================================="
echo "Workers: $WORKERS"
echo "日期范围: $START_DATE ~ $END_DATE"
echo ""

# 检查容器
if ! docker ps | grep -q "gdelt_app"; then
    echo "❌ 容器 gdelt_app 未运行"
    exit 1
fi

# 将脚本复制到容器
docker cp backfill_fingerprints_parallel.py gdelt_app:/app/

# 在容器内执行
docker exec -w /app gdelt_app python backfill_fingerprints_parallel.py \
    --workers $WORKERS \
    --start $START_DATE \
    --end $END_DATE

echo ""
echo "✅ 补全完成"
