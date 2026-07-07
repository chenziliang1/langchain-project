import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface EventTypeItem {
  event_type: string;
  event_count: number;
}

interface GeoItem {
  country_code: string;
  event_count: number;
}

interface Props {
  eventTypes: EventTypeItem[];
  geoDistribution: GeoItem[];
}

const TYPE_COLORS: Record<string, string> = {
  'Public Statement': '#3b82f6',
  'Yield': '#06b6d4',
  'Investigate': '#8b5cf6',
  'Demand': '#f59e0b',
  'Disapprove': '#f97316',
  'Reject': '#ef4444',
  'Threaten': '#dc2626',
  'Protest': '#eab308',
  'Other': '#9ca3af',
};

export default function DistributionCharts({ eventTypes, geoDistribution }: Props) {
  const typeRef = useRef<HTMLDivElement>(null);
  const geoRef = useRef<HTMLDivElement>(null);
  const typeChart = useRef<echarts.ECharts | null>(null);
  const geoChart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!typeRef.current || !geoRef.current) return;

    if (!typeChart.current) {
      typeChart.current = echarts.init(typeRef.current);
    }
    if (!geoChart.current) {
      geoChart.current = echarts.init(geoRef.current);
    }

    // Event Types donut chart
    const totalType = eventTypes.reduce((sum, q) => sum + q.event_count, 0);
    const typeOption: echarts.EChartsOption = {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          const pct = totalType > 0 ? ((params.value / totalType) * 100).toFixed(1) : '0';
          return `<div style="font-weight:600">${params.name}</div>
                  <div>Events: ${params.value.toLocaleString()}</div>
                  <div>Share: ${pct}%</div>`;
        },
      },
      legend: {
        orient: 'vertical',
        right: 10,
        top: 'center',
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { fontSize: 11 },
      },
      series: [
        {
          name: 'Event Type',
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['35%', '50%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 6,
            borderColor: '#fff',
            borderWidth: 2,
          },
          label: { show: false },
          emphasis: {
            label: {
              show: true,
              fontSize: 13,
              fontWeight: 'bold',
            },
          },
          data: eventTypes.map((q) => ({
            value: q.event_count,
            name: q.event_type,
            itemStyle: { color: TYPE_COLORS[q.event_type] || '#9ca3af' },
          })),
        },
      ],
    };

    // Geo distribution horizontal bar chart
    const topGeo = geoDistribution.slice(0, 8);
    const geoOption: echarts.EChartsOption = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = params[0];
          return `<div style="font-weight:600">${p.name}</div>
                  <div>Events: ${p.value.toLocaleString()}</div>`;
        },
      },
      grid: {
        left: 60,
        right: 20,
        top: 10,
        bottom: 10,
      },
      xAxis: {
        type: 'value',
        axisLabel: { fontSize: 10 },
        splitLine: { lineStyle: { color: '#f0f0f0' } },
      },
      yAxis: {
        type: 'category',
        data: topGeo.map((a) => a.country_code).reverse(),
        axisLabel: { fontSize: 11 },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: topGeo.map((a) => a.event_count).reverse(),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#34d399' },
              { offset: 1, color: '#059669' },
            ]),
            borderRadius: [0, 4, 4, 0],
          },
          barWidth: 16,
        },
      ],
    };

    typeChart.current.setOption(typeOption, true);
    geoChart.current.setOption(geoOption, true);

    const handleResize = () => {
      typeChart.current?.resize();
      geoChart.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    const resizeObserver = new ResizeObserver(() => {
      typeChart.current?.resize();
      geoChart.current?.resize();
    });
    if (typeRef.current) resizeObserver.observe(typeRef.current);
    if (geoRef.current) resizeObserver.observe(geoRef.current);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
    };
  }, [eventTypes, geoDistribution]);

  return (
    <div className="dashboard-grid" style={{ marginTop: 16 }}>
      <div className="panel">
        <h3>Event Type Distribution</h3>
        <div ref={typeRef} style={{ width: '100%', height: 260 }} />
      </div>
      <div className="panel">
        <h3>Top Locations</h3>
        <div ref={geoRef} style={{ width: '100%', height: 260 }} />
      </div>
    </div>
  );
}
