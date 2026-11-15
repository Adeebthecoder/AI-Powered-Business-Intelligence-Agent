// DatasetsPage.jsx
// Upload a CSV or Excel file, see what the cleaning step fixed, and list
// the datasets uploaded so far.

import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../AppContext.jsx";
import { api } from "../api.js";
import { EmptyState, ErrorBox } from "../components/States.jsx";
import { formatDateTime, formatNumber } from "../format.js";

// Table of the cleaning steps. Also used on the Overview page.
export function CleaningSummary({ summary }) {
  return (
    <div>
      <p className="muted">
        {formatNumber(summary.rows_before)} rows in the file, {formatNumber(summary.rows_after)} rows
        after cleaning.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Step</th>
              <th>What was done</th>
              <th className="num">Rows affected</th>
            </tr>
          </thead>
          <tbody>
            {summary.steps.map((step) => (
              <tr key={step.step}>
                <td className="nowrap"><strong>{step.step}</strong></td>
                <td>{step.detail}</td>
                <td className="num">{formatNumber(step.rows_affected)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DatasetsPage() {
  const { datasets, refreshDatasets, setDatasetId } = useApp();
  const navigate = useNavigate();
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [justUploaded, setJustUploaded] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  function chooseFile(chosen) {
    setError("");
    setJustUploaded(null);
    if (!chosen) return;
    if (!/\.(csv|xlsx)$/i.test(chosen.name)) {
      setError("Please choose a CSV (.csv) or Excel (.xlsx) file.");
      return;
    }
    setFile(chosen);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name);
      const dataset = await api("/api/datasets", { method: "POST", body: form });
      await refreshDatasets();
      setDatasetId(dataset.dataset_id);
      setJustUploaded(dataset);
      setFile(null);
      setName("");
      if (fileInput.current) fileInput.current.value = "";
    } catch (problem) {
      setError(problem.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(dataset) {
    const sure = window.confirm(
      `Delete "${dataset.name}"? Its history, forecasts and reports will be deleted too.`
    );
    if (!sure) return;
    try {
      await api(`/api/datasets/${dataset.dataset_id}`, { method: "DELETE" });
      if (justUploaded?.dataset_id === dataset.dataset_id) setJustUploaded(null);
      await refreshDatasets();
    } catch (problem) {
      setError(problem.message);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Datasets</h1>
          <p>Upload business data as CSV or Excel. It is cleaned and loaded into PostgreSQL for you.</p>
        </div>
      </header>

      <section className="card">
        <h2>Upload a file</h2>
        <div
          className={`dropzone${dragOver ? " over" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragOver(false);
            chooseFile(event.dataTransfer.files[0]);
          }}
          onClick={() => fileInput.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => event.key === "Enter" && fileInput.current?.click()}
        >
          <input ref={fileInput} type="file" accept=".csv,.xlsx" hidden
                 onChange={(event) => chooseFile(event.target.files[0])} />
          {file ? (
            <p><strong>{file.name}</strong> ({(file.size / 1024 / 1024).toFixed(2)} MB)</p>
          ) : (
            <>
              <p><strong>Click to choose a file</strong> or drag it here</p>
              <p className="muted small">CSV or Excel (.xlsx), up to 20 MB. Try data/indian_retail_sales.csv from the project folder.</p>
            </>
          )}
        </div>

        {file && (
          <div className="upload-row">
            <label className="field grow">
              <span>Dataset name (optional)</span>
              <input value={name} onChange={(e) => setName(e.target.value)}
                     placeholder="For example: Retail Sales 2023 to 2025" />
            </label>
            <button className="btn btn-primary" onClick={handleUpload} disabled={uploading}>
              {uploading ? "Cleaning and loading..." : "Upload and clean"}
            </button>
          </div>
        )}
        {uploading && <p className="muted small">This takes a few seconds for 10,000 rows.</p>}
        <ErrorBox message={error} />
      </section>

      {justUploaded && (
        <section className="card card-success">
          <div className="card-title-row">
            <h2>"{justUploaded.name}" is ready</h2>
            <div className="button-row">
              <button className="btn btn-primary" onClick={() => navigate(`/datasets/${justUploaded.dataset_id}`)}>
                View overview
              </button>
              <button className="btn" onClick={() => navigate("/ask")}>Ask a question</button>
            </div>
          </div>
          <h3>Cleaning summary</h3>
          <CleaningSummary summary={justUploaded.cleaning_summary} />
        </section>
      )}

      <section className="card">
        <h2>Your datasets</h2>
        {datasets.length === 0 ? (
          <EmptyState title="No datasets yet"
                      text="Upload your first file above. The sample file is in the data folder of the project." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>File</th>
                  <th className="num">Rows</th>
                  <th className="num">Columns</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr key={dataset.dataset_id}>
                    <td>
                      <Link to={`/datasets/${dataset.dataset_id}`} onClick={() => setDatasetId(dataset.dataset_id)}>
                        <strong>{dataset.name}</strong>
                      </Link>
                    </td>
                    <td className="muted">{dataset.source}</td>
                    <td className="num">{formatNumber(dataset.row_count)}</td>
                    <td className="num">{dataset.column_count}</td>
                    <td className="nowrap">{formatDateTime(dataset.upload_date)}</td>
                    <td className="actions">
                      <button className="btn btn-small"
                              onClick={() => { setDatasetId(dataset.dataset_id); navigate("/ask"); }}>
                        Ask
                      </button>
                      <button className="btn btn-small btn-danger" onClick={() => handleDelete(dataset)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
