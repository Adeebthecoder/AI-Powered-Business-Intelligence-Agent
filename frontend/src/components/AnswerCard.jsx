// AnswerCard.jsx
// Shows one answer from the system. Used on the Ask page and in History.
// What it shows depends on the answer's status:
//   success        insight, chart, result table, "Show SQL", "Download PDF"
//   clarification  the question the system asks back
//   blocked        why the safety check stopped the query
//   error          a friendly error message

import { useState } from "react";
import { downloadReportForAnalysis } from "../api.js";
import ChartView from "./ChartView.jsx";
import DataTable from "./DataTable.jsx";

export default function AnswerCard({ answer }) {
  const [showSql, setShowSql] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  async function handleDownload() {
    setDownloading(true);
    setDownloadError("");
    try {
      await downloadReportForAnalysis(answer.analysis_id);
    } catch (error) {
      setDownloadError(error.message);
    } finally {
      setDownloading(false);
    }
  }

  if (answer.status === "clarification") {
    return (
      <div className="answer answer-clarify">
        <span className="answer-tag">I need a little more detail</span>
        <p>{answer.message}</p>
      </div>
    );
  }

  if (answer.status === "blocked") {
    return (
      <div className="answer answer-blocked">
        <span className="answer-tag">Blocked by the safety check</span>
        <p>{answer.message}</p>
        {answer.sql && <pre className="sql">{answer.sql}</pre>}
        <p className="muted small">Nothing was run. This attempt was written to the safety log.</p>
      </div>
    );
  }

  if (answer.status === "error") {
    return (
      <div className="answer answer-error">
        <span className="answer-tag">Could not answer</span>
        <p>{answer.message}</p>
      </div>
    );
  }

  const result = answer.result || { columns: [], rows: [] };
  const hasChart = answer.chart && answer.chart.type !== "table";

  return (
    <div className="answer">
      <div className="answer-meta">
        {answer.cached && <span className="chip" title="Reused a saved answer. No AI call was made.">Saved answer · 0 AI calls</span>}
        {!answer.cached && answer.operation === "nl_query" && (
          <span className="chip">{answer.llm_calls} AI call{answer.llm_calls === 1 ? "" : "s"}</span>
        )}
        <span className="chip">
          {answer.insight_source === "llm" ? "Insight by AI, numbers verified" : "Automatic summary"}
        </span>
      </div>

      <p className="insight">{answer.insight}</p>
      {answer.message && <p className="note">{answer.message}</p>}

      {hasChart && <ChartView chart={answer.chart} />}

      {result.rows.length > 0 && !(answer.chart?.type === "kpi") && (
        <DataTable columns={result.columns} rows={result.rows} />
      )}
      {result.rows.length === 0 && <p className="muted">The query returned no rows.</p>}

      <div className="answer-actions">
        {answer.sql && (
          <button className="btn btn-small" onClick={() => setShowSql(!showSql)}>
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
        )}
        <button className="btn btn-small" onClick={handleDownload} disabled={downloading}>
          {downloading ? "Preparing PDF..." : "Download PDF"}
        </button>
      </div>
      {showSql && <pre className="sql">{answer.sql}</pre>}
      {downloadError && <p className="error-text">{downloadError}</p>}
    </div>
  );
}
