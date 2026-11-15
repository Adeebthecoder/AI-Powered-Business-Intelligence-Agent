// ReportsPage.jsx
// All PDF reports created so far, with download and delete buttons.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadReport } from "../api.js";
import { EmptyState, ErrorBox, Loading } from "../components/States.jsx";
import { formatDateTime } from "../format.js";

export default function ReportsPage() {
  const [reports, setReports] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    setError("");
    api("/api/reports").then(setReports).catch((problem) => setError(problem.message));
  }, []);

  useEffect(load, [load]);

  async function download(report) {
    setBusyId(report.report_id);
    setError("");
    try {
      await downloadReport(report.report_id);
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(report) {
    if (!window.confirm("Delete this report?")) return;
    try {
      await api(`/api/reports/${report.report_id}`, { method: "DELETE" });
      setReports((list) => list.filter((item) => item.report_id !== report.report_id));
    } catch (problem) {
      setError(problem.message);
    }
  }

  if (error && !reports) return <div className="page"><ErrorBox message={error} onRetry={load} /></div>;
  if (!reports) return <div className="page"><Loading text="Loading reports..." /></div>;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Reports</h1>
          <p>
            PDF reports with the question, result table, chart, insight, SQL, dataset name and time.
            Create one with the Download PDF button on any answer.
          </p>
        </div>
      </header>
      <ErrorBox message={error} />

      {reports.length === 0 ? (
        <EmptyState title="No reports yet"
                    text="Ask a question, then press Download PDF on the answer."
                    action={<Link className="btn btn-primary" to="/ask">Ask a question</Link>} />
      ) : (
        <section className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Report</th><th>Dataset</th><th>Created</th><th></th></tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.report_id}>
                    <td><strong>{report.report_title}</strong></td>
                    <td className="muted">{report.dataset_name}</td>
                    <td className="nowrap">{formatDateTime(report.created_at)}</td>
                    <td className="actions">
                      <button className="btn btn-small btn-primary" onClick={() => download(report)}
                              disabled={busyId === report.report_id}>
                        {busyId === report.report_id ? "Downloading..." : "Download"}
                      </button>
                      <button className="btn btn-small btn-danger" onClick={() => remove(report)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
