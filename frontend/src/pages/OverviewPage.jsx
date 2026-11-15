// OverviewPage.jsx
// The automatic overview of one dataset: KPI cards, auto-selected charts,
// data quality (cleaning summary and missing values), statistics and a preview.

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApp } from "../AppContext.jsx";
import { api } from "../api.js";
import ChartView, { KpiCards } from "../components/ChartView.jsx";
import DataTable from "../components/DataTable.jsx";
import { ErrorBox, Loading } from "../components/States.jsx";
import { formatNumber, niceName } from "../format.js";
import { CleaningSummary } from "./DatasetsPage.jsx";

const TABS = ["Overview", "Data quality", "Statistics", "Data preview"];

export default function OverviewPage() {
  const { id } = useParams();
  const { setDatasetId } = useApp();
  const [data, setData] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(TABS[0]);

  useEffect(() => {
    setData(null);
    setPreview(null);
    setError("");
    setDatasetId(Number(id));
    api(`/api/datasets/${id}/overview`).then(setData).catch((problem) => setError(problem.message));
    api(`/api/datasets/${id}/preview?limit=25`).then(setPreview).catch(() => {});
  }, [id, setDatasetId]);

  if (error) return <div className="page"><ErrorBox message={error} /></div>;
  if (!data) return <div className="page"><Loading text="Loading the overview..." /></div>;

  const { dataset, overview } = data;
  const missingRows = overview.missing.filter((item) => item.missing > 0);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{dataset.name}</h1>
          <p>
            {formatNumber(dataset.row_count)} rows, {dataset.column_count} columns, from {dataset.source}
          </p>
        </div>
        <Link className="btn btn-primary" to="/ask">Ask a question</Link>
      </header>

      <KpiCards cards={overview.kpis} />

      <div className="tabs tabs-page">
        {TABS.map((name) => (
          <button key={name} className={tab === name ? "tab active" : "tab"} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="grid-2">
          {overview.charts.map((chart) => (
            <section className="card" key={chart.title}>
              <h3>{chart.title}</h3>
              <ChartView chart={chart} height={300} />
            </section>
          ))}
        </div>
      )}

      {tab === "Data quality" && (
        <>
          <section className="card">
            <h2>Cleaning summary</h2>
            <CleaningSummary summary={dataset.cleaning_summary} />
          </section>
          <section className="card">
            <h2>Missing values found in the file</h2>
            {missingRows.length === 0 ? (
              <p className="muted">No missing values were found.</p>
            ) : (
              <DataTable columns={["column", "missing values", "% of rows"]}
                         rows={missingRows.map((item) => [item.column, item.missing, item.percent])} />
            )}
            <p className="muted small">These were counted before cleaning. See the cleaning summary for how each was handled.</p>
          </section>
          <section className="card">
            <h2>Columns</h2>
            <DataTable
              initialRows={30}
              columns={["column", "type", "different values", "examples"]}
              rows={dataset.schema_info.columns.map((column) => [
                column.name, column.type, column.distinct_values, column.examples.join(", "),
              ])}
            />
          </section>
        </>
      )}

      {tab === "Statistics" && (
        <>
          <section className="card">
            <h2>Summary statistics</h2>
            <DataTable
              initialRows={30}
              columns={["column", "count", "mean", "median", "std deviation", "min", "max"]}
              rows={overview.summary_stats.map((s) => [niceName(s.column), s.count, s.mean, s.median, s.std, s.min, s.max])}
            />
          </section>
          <h2 className="section-title">Distributions</h2>
          <div className="grid-3">
            {overview.distributions.map((chart) => (
              <section className="card" key={chart.type + chart.title}>
                <h3>{chart.title}</h3>
                <ChartView chart={chart} height={220} />
              </section>
            ))}
          </div>
          {overview.correlations && (
            <section className="card">
              <h2>Correlations</h2>
              <p className="muted small">
                1 means two columns rise together, -1 means one rises when the other falls, 0 means no link.
              </p>
              <ChartView height={380} chart={{
                type: "heatmap",
                x: overview.correlations.columns.map(niceName),
                y: overview.correlations.columns.map(niceName),
                z: overview.correlations.matrix,
              }} />
            </section>
          )}
        </>
      )}

      {tab === "Data preview" && (
        <section className="card">
          <h2>First rows of the clean data</h2>
          {preview ? <DataTable columns={preview.columns} rows={preview.rows} initialRows={25} />
                   : <Loading text="Loading rows..." />}
        </section>
      )}
    </div>
  );
}
