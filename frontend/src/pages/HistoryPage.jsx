// HistoryPage.jsx
// Every question asked so far (and every forecast). Click a row to open the
// full answer again. Opening a saved answer costs no AI call.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import AnswerCard from "../components/AnswerCard.jsx";
import { EmptyState, ErrorBox, Loading, StatusBadge } from "../components/States.jsx";
import { formatDateTime } from "../format.js";

export default function HistoryPage() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);
  const [openItem, setOpenItem] = useState(null);
  const [filter, setFilter] = useState("all");

  const load = useCallback(() => {
    setError("");
    api("/api/history").then(setItems).catch((problem) => setError(problem.message));
  }, []);

  useEffect(load, [load]);

  async function toggle(item) {
    if (openId === item.analysis_id) {
      setOpenId(null);
      return;
    }
    setOpenId(item.analysis_id);
    setOpenItem(null);
    try {
      setOpenItem(await api(`/api/history/${item.analysis_id}`));
    } catch (problem) {
      setError(problem.message);
    }
  }

  async function remove(item) {
    if (!window.confirm("Delete this item from history?")) return;
    try {
      await api(`/api/history/${item.analysis_id}`, { method: "DELETE" });
      setItems((list) => list.filter((entry) => entry.analysis_id !== item.analysis_id));
    } catch (problem) {
      setError(problem.message);
    }
  }

  if (error && !items) return <div className="page"><ErrorBox message={error} onRetry={load} /></div>;
  if (!items) return <div className="page"><Loading text="Loading history..." /></div>;

  const visible = items.filter((item) => filter === "all" || item.status === filter);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>History</h1>
          <p>Every question and forecast is saved here with its result, chart and SQL.</p>
        </div>
        <label className="picker">
          <span>Show</span>
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">Everything</option>
            <option value="success">Answered</option>
            <option value="clarification">Needs detail</option>
            <option value="blocked">Blocked</option>
            <option value="error">Errors</option>
          </select>
        </label>
      </header>
      <ErrorBox message={error} />

      {items.length === 0 ? (
        <EmptyState title="Nothing here yet" text="Questions you ask will appear here."
                    action={<Link className="btn btn-primary" to="/ask">Ask a question</Link>} />
      ) : visible.length === 0 ? (
        <EmptyState title="No items match this filter" />
      ) : (
        <div className="history-list">
          {visible.map((item) => (
            <div className="history-item card" key={item.analysis_id}>
              <button className="history-head" onClick={() => toggle(item)}
                      aria-expanded={openId === item.analysis_id}>
                <StatusBadge status={item.status} />
                <span className="history-question">{item.question}</span>
                <span className="history-meta">
                  {item.operation === "forecast" ? "Forecast" : "Question"} · {item.dataset_name} · {formatDateTime(item.timestamp)}
                </span>
              </button>
              {openId === item.analysis_id && (
                <div className="history-body">
                  {openItem ? <AnswerCard answer={openItem} /> : <Loading text="Loading the answer..." />}
                  <button className="btn btn-small btn-danger" onClick={() => remove(item)}>
                    Delete from history
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
