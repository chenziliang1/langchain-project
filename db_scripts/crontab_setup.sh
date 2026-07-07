#!/bin/bash
# ============================================
# GDELT ETL 定时任务设置脚本
# ============================================

# 用法:
#   chmod +x db_scripts/crontab_setup.sh
#   ./db_scripts/crontab_setup.sh

echo "📝 GDELT ETL 定时任务设置"
echo "========================"
echo ""

# 检查 Docker 容器是否运行
if ! docker ps | grep -q "gdelt_mysql\|gdelt_mcp"; then
    echo "⚠️ 警告: 未检测到 GDELT 容器运行"
    echo "   请先启动 Docker Compose: docker-compose up -d"
    echo ""
fi

# 创建日志目录
mkdir -p /tmp/gdelt_logs

# 生成 crontab 条目
cat << 'EOF'

推荐添加到 crontab 的配置:
========================

# GDELT ETL Pipeline - 每天凌晨2点执行
0 2 * * * cd /path/to/DBMSproject && docker exec -w /app gdelt_mcp python db_scripts/etl_pipeline.py >> /tmp/gdelt_logs/etl_$(date +\%Y\%m\%d).log 2>&1

# GDELT 数据库备份 - 每周日凌晨3点执行
0 3 * * 0 cd /path/to/DBMSproject && docker exec gdelt_mysql mysqldump -u root -prootpassword gdelt > /tmp/gdelt_logs/backup_$(date +\%Y\%m\%d).sql 2>&1

# 清理旧日志 - 每月1号执行
0 4 1 * * find /tmp/gdelt_logs -name "*.log" -mtime +30 -delete

EOF

# 提示用户
echo ""
echo "💡 操作步骤:"
echo "   1. 复制上面的配置"
echo "   2. 运行: crontab -e"
echo "   3. 粘贴配置并保存"
echo ""
echo "或者一键安装 (覆盖现有crontab):"
echo "   crontab -l > /tmp/crontab_backup_$(date +%Y%m%d) 2>/dev/null"
echo "   (cat /tmp/crontab_backup_* 2>/dev/null; echo ''; cat << 'CRON') | crontab -"
echo ''
echo '# GDELT ETL Pipeline'
echo "0 2 * * * cd $(pwd) && docker exec -w /app gdelt_mcp python db_scripts/etl_pipeline.py >> /tmp/gdelt_logs/etl_\$(date +\%Y\%m\%d).log 2>&1"
echo ''
echo "CRON"
echo ""
