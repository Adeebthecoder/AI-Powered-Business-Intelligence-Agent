// AdminPage.jsx
// Only visible to an admin: all users and all datasets in the system.

import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ErrorBox, Loading } from "../components/States.jsx";
import { formatDateTime, formatNumber } from "../format.js";

export default function AdminPage() {
  const [users, setUsers] = useState(null);
  const [datasets, setDatasets] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/api/admin/users"), api("/api/admin/datasets")])
      .then(([userList, datasetList]) => {
        setUsers(userList);
        setDatasets(datasetList);
      })
      .catch((problem) => setError(problem.message));
  }, []);

  if (error) return <div className="page"><ErrorBox message={error} /></div>;
  if (!users || !datasets) return <div className="page"><Loading text="Loading admin data..." /></div>;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Admin</h1>
          <p>All users and all datasets. Only accounts with the admin role can open this page.</p>
        </div>
      </header>

      <section className="card">
        <h2>Users ({users.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Role</th><th className="num">Datasets</th><th>Joined</th></tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td><strong>{user.name}</strong></td>
                  <td>{user.email}</td>
                  <td><span className={`badge ${user.role === "admin" ? "badge-success" : "badge-neutral"}`}>{user.role}</span></td>
                  <td className="num">{user.dataset_count}</td>
                  <td className="nowrap">{formatDateTime(user.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Datasets ({datasets.length})</h2>
        {datasets.length === 0 ? (
          <p className="muted">No datasets have been uploaded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Owner</th><th>File</th><th className="num">Rows</th><th>Uploaded</th></tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr key={dataset.dataset_id}>
                    <td><strong>{dataset.name}</strong></td>
                    <td>{dataset.owner_name} <span className="muted">({dataset.owner_email})</span></td>
                    <td className="muted">{dataset.source}</td>
                    <td className="num">{formatNumber(dataset.row_count)}</td>
                    <td className="nowrap">{formatDateTime(dataset.upload_date)}</td>
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
