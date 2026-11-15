// ChartView.jsx
// Draws one chart with Plotly from the chart description sent by the backend.
//
// The backend decides WHICH chart to show (see chart_selector.py). This file
// only turns that description into Plotly settings. Chart description:
//   { type, title, x_label, y_label, x: [...], series: [{ name, values: [...] }] }

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import { formatCompact, formatNumber, niceName } from "../format.js";

const ACCENT = "#4338CA";
// The first colour is the accent. The others are only used when one chart
// has several series (lines or grouped bars) that must be told apart.
const PALETTE = ["#4338CA", "#0EA5A4", "#F59E0B", "#E11D48", "#64748B", "#7C3AED", "#16A34A", "#0284C7"];
const PIE_SHADES = ["#4338CA", "#6366F1", "#818CF8", "#A5B4FC", "#C7D2FE", "#E0E7FF", "#94A3B8", "#CBD5E1"];

const BASE_LAYOUT = {
  font: { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 12, color: "#334155" },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  margin: { l: 56, r: 16, t: 12, b: 48 },
  hoverlabel: { bgcolor: "#0F172A", font: { color: "#FFFFFF" } },
  legend: { orientation: "h", y: 1.12, x: 0 },
  xaxis: { gridcolor: "#EEF2F7", zeroline: false, automargin: true },
  yaxis: { gridcolor: "#EEF2F7", zerolinecolor: "#CBD5E1", automargin: true },
};

function buildPlot(chart) {
  const series = chart.series || [];
  const many = series.length > 1;
  const layout = JSON.parse(JSON.stringify(BASE_LAYOUT));
  layout.showlegend = many;
  let traces = [];

  if (chart.type === "bar" || chart.type === "histogram") {
    const horizontal = chart.orientation === "h";
    traces = series.map((item, index) => ({
      type: "bar",
      name: item.name,
      orientation: horizontal ? "h" : "v",
      x: horizontal ? item.values : chart.x,
      y: horizontal ? chart.x : item.values,
      marker: { color: many ? PALETTE[index % PALETTE.length] : ACCENT },
      hovertemplate: horizontal ? "%{y}<br>%{x:,.2f}<extra></extra>" : "%{x}<br>%{y:,.2f}<extra></extra>",
    }));
    layout.barmode = "group";
    if (chart.type === "histogram") layout.bargap = 0.03;
    if (horizontal) {
      layout.yaxis.autorange = "reversed"; // biggest bar on top
      layout.margin.l = 8;
      layout.xaxis.title = { text: chart.y_label || "" };
    } else {
      layout.xaxis.type = chart.type === "histogram" ? "linear" : "category";
      layout.xaxis.title = { text: chart.x_label || "" };
      layout.yaxis.title = { text: chart.y_label || "" };
    }
  } else if (chart.type === "line") {
    const looksLikeDates = chart.x.every((value) => /^\d{4}-\d{2}-\d{2}/.test(String(value)));
    traces = series.map((item, index) => ({
      type: "scatter",
      mode: chart.x.length > 40 ? "lines" : "lines+markers",
      name: item.name,
      x: chart.x,
      y: item.values,
      connectgaps: false,
      line: { color: PALETTE[index % PALETTE.length], width: 2.5, dash: item.dashed ? "dash" : "solid" },
      marker: { size: 6 },
      hovertemplate: "%{x}<br>%{y:,.2f}<extra>" + (many ? item.name : "") + "</extra>",
    }));
    layout.xaxis.type = looksLikeDates ? "date" : "category";
    layout.xaxis.title = { text: chart.x_label || "" };
    layout.yaxis.title = { text: chart.y_label || "" };
  } else if (chart.type === "pie") {
    traces = [{
      type: "pie",
      labels: chart.x,
      values: series[0].values,
      hole: 0.5,
      sort: false,
      marker: { colors: PIE_SHADES, line: { color: "#FFFFFF", width: 2 } },
      textinfo: "label+percent",
      hovertemplate: "%{label}<br>%{value:,.2f} (%{percent})<extra></extra>",
    }];
    layout.margin = { l: 16, r: 16, t: 12, b: 12 };
    layout.showlegend = false;
  } else if (chart.type === "scatter") {
    traces = [{
      type: "scatter",
      mode: "markers",
      x: chart.x,
      y: series[0].values,
      marker: { color: ACCENT, size: 8, opacity: 0.7 },
    }];
    layout.xaxis.title = { text: chart.x_label || "" };
    layout.yaxis.title = { text: chart.y_label || "" };
  } else if (chart.type === "heatmap") {
    traces = [{
      type: "heatmap",
      x: chart.x,
      y: chart.y,
      z: chart.z,
      zmin: -1,
      zmax: 1,
      colorscale: [[0, "#E11D48"], [0.5, "#F8FAFC"], [1, "#4338CA"]],
      text: chart.z.map((row) => row.map((value) => value.toFixed(2))),
      texttemplate: "%{text}",
      hovertemplate: "%{y} and %{x}<br>correlation %{z}<extra></extra>",
      colorbar: { thickness: 10, len: 0.9 },
    }];
    layout.margin = { l: 8, r: 8, t: 12, b: 8 };
    layout.yaxis.autorange = "reversed";
  }
  return { traces, layout };
}

// KPI cards are plain HTML, not a Plotly chart.
export function KpiCards({ cards }) {
  return (
    <div className="kpi-row">
      {cards.map((card) => (
        <div className="kpi" key={card.label}>
          <span className="kpi-label">{niceName(card.label)}</span>
          <span className={`kpi-value${typeof card.value === "number" ? "" : " kpi-text"}`} title={typeof card.value === "number" ? formatNumber(card.value) : undefined}>
            {card.kind === "text" || card.label.toLowerCase() === "year"
              ? String(card.value)
              : formatCompact(card.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ChartView({ chart, height = 320 }) {
  const container = useRef(null);
  const isPlot = chart && !["kpi", "table"].includes(chart.type);

  useEffect(() => {
    if (!isPlot || !container.current) return undefined;
    const node = container.current;
    const { traces, layout } = buildPlot(chart);
    Plotly.react(node, traces, { ...layout, height }, { displayModeBar: false, responsive: true });
    return () => Plotly.purge(node);
  }, [chart, height, isPlot]);

  if (!chart) return null;
  if (chart.type === "kpi") return <KpiCards cards={chart.cards} />;
  if (chart.type === "table") return null;
  return <div ref={container} className="chart" style={{ minHeight: height }} />;
}
