// States.jsx
// Small building blocks used on every page: loading spinner, empty state,
// error box, status badge and the dataset picker.

import { Link } from "react-router-dom";
import { useApp } from "../AppContext.jsx";

export function Loading({ text = "Loading..." }) {
  return (
    <div className="state" role="status">
      <div className="spinner" />
      <p>{text}</p>
    </div>
  );
}

export function EmptyState({ title, text, action }) {
  return (
    <div className="state empty">
      <div className="empty-icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 10h18M9 4v16" />
        </svg>
      </div>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export function ErrorBox({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="alert alert-error" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

const BADGE_LABELS = {
  success: "Answered",
  clarification: "Needs detail",
  blocked: "Blocked",
  error: "Error",
};

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{BADGE_LABELS[status] || status}</span>;
}

// Shown when a page needs a dataset but none has been uploaded yet.
export function NoDataset() {
  return (
    <EmptyState
      title="No dataset yet"
      text="Upload a CSV or Excel file first. Then you can ask questions about it."
      action={
        <Link className="btn btn-primary" to="/datasets">
          Go to Datasets
        </Link>
      }
    />
  );
}

// Drop-down to choose which dataset a page works on.
export function DatasetPicker() {
  const { datasets, datasetId, setDatasetId } = useApp();
  if (!datasets.length) return null;
  return (
    <label className="picker">
      <span>Dataset</span>
      <select value={datasetId || ""} onChange={(event) => setDatasetId(Number(event.target.value))}>
        {datasets.map((d) => (
          <option key={d.dataset_id} value={d.dataset_id}>
            {d.name}
          </option>
        ))}
      </select>
    </label>
  );
}
