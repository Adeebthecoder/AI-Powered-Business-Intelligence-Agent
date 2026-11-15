// ForecastPage.jsx
// Monthly forecast for the next 3 months. Shows the chart, the forecast
// values and the comparison of the models (MAE and RMSE on held-out months).

import { useEffect, useState } from "react";
import { useApp } from "../AppContext.jsx";
import { api, downloadReportForAnalysis } from "../api.js";
import ChartView, { KpiCards } from "../components/ChartView.jsx";
import { DatasetPicker, EmptyState, ErrorBox, Loading, NoDataset } from "../components/States.jsx";
import { formatDateTime, formatMonth, formatNumber, niceName } from "../format.js";

export default function ForecastPage() {
  const { datasetId } = useApp();
  const [options, setOptions] = useState(null);
  const [dateColumn, setDateColumn] = useState("");
  const [valueColumn, setValueColumn] = useState("");
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  // When the dataset changes: load its columns and its latest saved forecast.
  useEffect(() => {
    if (!datasetId) return;
    setLoading(true);
    setForecast(null);
    setError("");
    Promise.all([api(`/api/forecast/options/${datasetId}`), api(`/api/forecast/latest/${datasetId}`)])
      .then(([columnOptions, latest]) => {
        setOptions(columnOptions);
        setDateColumn(columnOptions.default_date || "");
        setValueColumn(columnOptions.default_value || "");
        setForecast(latest);
      })
      .catch((problem) => setError(problem.message))
      .finally(() => setLoading(false));
  }, [datasetId]);

  async function runForecast() {
    setRunning(true);
    setError("");
    try {
      setForecast(await api("/api/forecast", {
        method: "POST",
        body: { dataset_id: datasetId, date_column: dateColumn, value_column: valueColumn },
      }));
    } catch (problem) {
      setError(problem.message);
    } finally {
      setRunning(false);
    }
  }

  async function exportPdf() {
    setDownloading(true);
    try {
      await downloadReportForAnalysis(forecast.analysis.analysis_id);
    } catch (problem) {
      setError(problem.message);
    } finally {
      setDownloading(false);
    }
  }

  if (!datasetId) return <div className="page"><NoDataset /></div>;

  const canForecast = options && options.date_columns.length > 0 && options.value_columns.length > 0;
  const scores = forecast?.evaluation.scores || [];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Forecast</h1>
          <p>Monthly forecast for the next 3 months, with the model chosen by a fair test.</p>
        </div>
        <DatasetPicker />
      </header>

      {loading ? (
        <Loading text="Loading..." />
      ) : !canForecast ? (
        <EmptyState title="This dataset cannot be forecast"
                    text="A forecast needs one date column and one number column." />
      ) : (
        <>
          <section className="card">
            <div className="upload-row">
              <label className="field">
                <span>Date column</span>
                <select value={dateColumn} onChange={(event) => setDateColumn(event.target.value)}>
                  {options.date_columns.map((column) => <option key={column} value={column}>{niceName(column)}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Value to forecast</span>
                <select value={valueColumn} onChange={(event) => setValueColumn(event.target.value)}>
                  {options.value_columns.map((column) => <option key={column} value={column}>{niceName(column)}</option>)}
                </select>
              </label>
              <button className="btn btn-primary" onClick={runForecast} disabled={running}>
                {running ? "Training and testing models..." : forecast ? "Run again" : "Run forecast"}
              </button>
            </div>
            <ErrorBox message={error} />
          </section>

          {!forecast && !running && (
            <EmptyState title="No forecast yet"
                        text="Choose the columns above and press Run forecast. It takes a few seconds." />
          )}
          {running && <Loading text="Comparing models on the test period..." />}

          {forecast && !running && (
            <>
              <KpiCards cards={forecast.output.forecast.map((point) => ({
                label: `Forecast ${formatMonth(point.month)}`, value: point.value,
              }))} />

              <section className="card">
                <div className="card-title-row">
                  <h2>{forecast.analysis.chart.title}</h2>
                  <button className="btn btn-small" onClick={exportPdf} disabled={downloading}>
                    {downloading ? "Preparing PDF..." : "Download PDF"}
                  </button>
                </div>
                <ChartView chart={forecast.analysis.chart} height={360} />
                <p className="insight">{forecast.analysis.insight}</p>
              </section>

              <div className="grid-2">
                <section className="card">
                  <h2>Model comparison</h2>
                  <p className="muted small">
                    Trained on {forecast.evaluation.train_period}. Tested on {forecast.evaluation.test_period},
                    months the models never saw. Lower error is better.
                  </p>
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr><th>Model</th><th className="num">MAE</th><th className="num">RMSE</th></tr>
                      </thead>
                      <tbody>
                        {scores.map((score) => (
                          <tr key={score.model} className={score.model === forecast.model_name ? "row-best" : ""}>
                            <td>
                              {score.model}
                              {score.model === forecast.model_name && <span className="badge badge-success">Chosen</span>}
                            </td>
                            <td className="num">{formatNumber(score.mae)}</td>
                            <td className="num">{formatNumber(score.rmse)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted small">
                    MAE is the average size of the error. RMSE is similar but punishes big misses more.
                  </p>
                </section>

                <section className="card">
                  <h2>Saved prediction record</h2>
                  <dl className="facts">
                    <dt>Model name</dt><dd>{forecast.model_name}</dd>
                    <dt>Model version</dt><dd>{forecast.model_version}</dd>
                    <dt>Created</dt><dd>{formatDateTime(forecast.created_at)}</dd>
                    <dt>Prediction id</dt><dd>{forecast.prediction_id}</dd>
                  </dl>
                  <p className="muted small">
                    How leakage is avoided: the data is split by time, models are fitted only on the
                    earlier months, and the only inputs are the month number and the calendar month.
                  </p>
                </section>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
