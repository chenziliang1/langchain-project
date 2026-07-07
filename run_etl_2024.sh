#!/bin/bash
# ============================================
# GDELT 2024年全年数据 ETL 简单脚本
# 用途: 顺序处理2024年每一天的数据
# 执行: ./run_etl_2024.sh
# ============================================

# 配置
CONTAINER="gdelt_app"
LOG_DIR="/tmp/gdelt_etl_2024"

# 创建日志目录
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "🚀 GDELT 2024年全年 ETL"
echo "=========================================="
echo ""

# 检查容器
if ! docker ps | grep -q "$CONTAINER"; then
    echo "❌ 容器 $CONTAINER 未运行"
    echo "请先运行: docker-compose up -d"
    exit 1
fi

# 总天数
TOTAL=366  # 2024年是闰年
CURRENT=0

# 从1月1日到12月31日
for MONTH in $(seq -w 1 12); do
    # 获取该月天数
    case $MONTH in
        01|03|05|07|08|10|12) DAYS=31 ;;
        04|06|09|11) DAYS=30 ;;
        02) DAYS=29 ;;  # 闰年
    esac
    
    echo "📅 处理 2024年${MONTH}月 (${DAYS}天)..."
    
    for DAY in $(seq -w 1 $DAYS); do
        DATE="2024-${MONTH}-${DAY}"
        CURRENT=$((CURRENT + 1))
        
        LOG_FILE="$LOG_DIR/${DATE}.log"
        
        # 检查是否已处理
        if [ -f "$LOG_FILE" ] && grep -q "ETL完成" "$LOG_FILE" 2>/dev/null; then
            echo "  [$CURRENT/$TOTAL] $DATE ✓ (已处理)"
            continue
        fi
        
        # 执行 ETL
        echo -n "  [$CURRENT/$TOTAL] $DATE ... "
        
        if docker exec -w /app "$CONTAINER" python db_scripts/etl_pipeline.py "$DATE" > "$LOG_FILE" 2>&1; then
            if grep -q "ETL完成" "$LOG_FILE"; then
                echo "✅ 成功"
            elif grep -q "无数据" "$LOG_FILE"; then
                echo "⚪ 无数据"
            else
                echo "❌ 失败"
            fi
        else
            echo "❌ 失败"
        fi
        
        # 每10天暂停0.5秒，避免数据库压力过大
        if [ $((CURRENT % 10)) -eq 0 ]; then
            sleep 0.5
        fi
    done
    
    echo ""
done

echo "=========================================="
echo "✅ 处理完成"
echo "=========================================="

# 统计
SUCCESS=$(grep -l "ETL完成" $LOG_DIR/*.log 2>/dev/null | wc -l)
NODATA=$(grep -l "无数据" $LOG_DIR/*.log 2>/dev/null | wc -l)
FAILED=$((TOTAL - SUCCESS - NODATA))

echo "总计: $TOTAL 天"
echo "成功: $SUCCESS 天"
echo "无数据: $NODATA 天"
echo "失败: $FAILED 天"
echo "日志: $LOG_DIR/"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "失败的日期:"
    for f in $LOG_DIR/*.log; do
        if ! grep -q "ETL完成\|无数据" "$f" 2>/dev/null; then
            echo "  - $(basename $f .log)"
        fi
    done
fi
