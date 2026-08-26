import { BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useImperativeHandle, useRef } from "react";
import type { Ref } from "react";

// Only the pieces these charts need are registered, so the bundle carries a donut and a
// bar chart rather than all of ECharts.
echarts.use([
  PieChart,
  BarChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  TitleComponent,
  CanvasRenderer,
]);

export interface ChartHandle {
  /** The chart as a PNG data URL, at 2x for a usable screenshot. Background is passed in
   *  because the canvas itself is transparent and a transparent PNG is unreadable when
   *  pasted into a light document. */
  toPng: (background: string) => string | null;
}

interface Props {
  option: echarts.EChartsCoreOption;
  height: number;
  handleRef?: Ref<ChartHandle>;
  ariaLabel?: string;
}

/**
 * Thin ECharts host.
 *
 * Two things it takes care of that a naive wrapper gets wrong: it resizes with its
 * container (the dashboard is a flex layout, so the element's width changes without the
 * window ever resizing), and it replaces the option wholesale on every update rather
 * than merging, so a breakdown with fewer categories than the last one doesn't leave the
 * old slices behind.
 */
export default function EChart({ option, height, handleRef, ariaLabel }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const chart = echarts.init(hostRef.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(hostRef.current);

    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  useImperativeHandle(
    handleRef,
    () => ({
      toPng: (background: string) =>
        chartRef.current?.getDataURL({
          type: "png",
          pixelRatio: 2,
          backgroundColor: background,
        }) ?? null,
    }),
    []
  );

  return <div ref={hostRef} style={{ width: "100%", height }} role="img" aria-label={ariaLabel} />;
}
