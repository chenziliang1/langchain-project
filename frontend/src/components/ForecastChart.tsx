import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface HistoryPoint {
  date: string;
  event_count: number;
  avg_goldstein?: number;
  avg_tone?: number;
}

interface ForecastPoint {
  date: string;
  expected_events: number;
  low_events: number;
  median_events: number;
  high_events: number;
  risk_score?: number;
  risk_level?: string;
}

interface Props {
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  title?: string;
}

export default function ForecastChart({ history, forecast, title = 'History & Forecast' }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const allDates = [...history.map((h) => h.date), ...forecast.map((f) => f.date)];
    const shortDates = allDates.map((d) => d.slice(5));

    const historyData = allDates.map((date) => {
      const found = history.find((h) => h.date === date);
      return found ? found.event_count : null;
    });

    const forecastMedian = allDates.map((date) => {
      const found = forecast.find((f) => f.date === date);
      return found ? found.median_events : null;
    });

    const forecastLow = allDates.map((date) => {
      const found = forecast.find((f) => f.date === date);
      return found ? found.low_events : null;
    });

    const forecastHigh = allDates.map((date) => {
      const found = forecast.find((f) => f.date === date);
      return found ? found.high_events : null;
    });

    const splitIndex = history.length;

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const idx = params[0]?.dataIndex ?? 0;
          const fullDate = allDates[idx] ?? '';
          let html = `<div style="font-weight:600;margin-bottom:4px">${fullDate}</div>`;
          params.forEach((p: any) => {
            if (p.value == null) return;
            html += `<div style="display:flex;align-items:center;gap:6px">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color}"></span>
              <span>${p.seriesName}:</span>
              <span style="font-weight:600">${Math.round(p.value).toLocaleString()}</span>
            </div>`;
          });
          return html;
        },
      },
      legend: {
        data: ['Historical', 'Forecast', 'Confidence Band'],
        bottom: 0,
        textStyle: { fontSize: 12 },
      },
      grid: {
        left: 56,
        right: 56,
        top: 48,
        bottom: 72,
      },
      xAxis: {
        type: 'category',
        data: shortDates,
        axisLabel: {
          fontSize: 11,
          rotate: 35,
          interval: Math.max(0, Math.floor(shortDates.length / 10)),
        },
        axisTick: { alignWithLabel: true },
      },
      yAxis: {
        type: 'value',
        name: 'Events',
        axisLabel: { fontSize: 11 },
        nameTextStyle: { fontSize: 12, padding: [0, 0, 0, -30] },
        splitLine: { lineStyle: { color: '#f0f0f0' } },
      },
      series: [
        {
          name: 'Historical',
          type: 'bar',
          data: historyData.map((v, i) => (i < splitIndex ? v : null)),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#60a5fa' },
              { offset: 1, color: '#2563eb' },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 28,
          animationDelay: (idx: number) => idx * 20,
        },
        {
          name: 'Forecast',
          type: 'line',
          data: forecastMedian.map((v, i) => (i >= splitIndex - 1 ? v : null)),
          smooth: true,
          symbol: 'circle',
          symbolSize: 8,
          itemStyle: { color: '#059669', borderWidth: 2, borderColor: '#fff' },
          lineStyle: { width: 3, shadowColor: 'rgba(5,150,105,0.3)', shadowBlur: 8 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(5,150,105,0.2)' },
              { offset: 1, color: 'rgba(5,150,105,0)' },
            ]),
          },
        },
        {
          name: 'Confidence Band',
          type: 'line',
          data: forecastHigh.map((v, i) => (i >= splitIndex - 1 ? v : null)),
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 0 },
          areaStyle: {
            color: 'rgba(5,150,105,0.08)',
            origin: 'start',
          },
          stack: 'band',
        },
        {
          name: '_low',
          type: 'line',
          data: forecastLow.map((v, i) => (i >= splitIndex - 1 ? v : null)),
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 0 },
          areaStyle: {
            color: 'rgba(255,255,255,0.92)',
            origin: 'start',
          },
          stack: 'band',
        },
      ],
      animationEasing: 'elasticOut',
      animationDelayUpdate: (idx: number) => idx * 5,
    };

    chartInstance.current.setOption(option, true);

    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', handleResize);
    const resizeObserver = new ResizeObserver(() => chartInstance.current?.resize());
    if (chartRef.current) resizeObserver.observe(chartRef.current);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
    };
  }, [history, forecast]);

  return (
    <div className="panel">
      <h3>{title}</h3>
      <div ref={chartRef} style={{ width: '100%', height: 400 }} />
    </div>
  );
}
