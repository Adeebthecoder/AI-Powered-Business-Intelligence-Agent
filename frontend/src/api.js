// api.js
// One small helper for every call to the backend.
//  - adds the login token to each request
//  - turns backend error replies into a readable message
//  - logs the user out when the token has expired

const TOKEN_KEY = "bi_agent_token";

// Address of the backend. Empty on a laptop (the Vite dev server forwards /api to
// the backend). On a hosted site, set VITE_API_URL to the backend address, for
// example https://bi-agent.onrender.com (no slash at the end).
const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

export const CREDIT_LINE =
  "Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// Called by AuthContext so api.js can log the user out on a 401 reply.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// FastAPI sends errors as {"detail": "..."} or as a list of field problems.
function readError(body, status) {
  if (body && typeof body.detail === "string") return body.detail;
  if (body && Array.isArray(body.detail)) {
    return body.detail.map((item) => item.msg.replace("Value error, ", "")).join(" ");
  }
  if (status >= 500) return "The server had a problem. Please try again.";
  return "Something went wrong. Please try again.";
}

// The main helper. `options.body` may be a plain object (sent as JSON),
// a FormData (file upload) or URLSearchParams (the login form).
export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body = options.body;
  const isPlainObject =
    body && !(body instanceof FormData) && !(body instanceof URLSearchParams);
  if (isPlainObject) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, body });
  } catch {
    const onLaptop = ["localhost", "127.0.0.1"].includes(window.location.hostname);
    throw new Error(
      onLaptop
        ? "Cannot reach the backend. Check that it is running on http://localhost:8000."
        : "Cannot reach the server. Check your internet connection and try again."
    );
  }

  if (response.status === 401 && token) {
    onUnauthorized();
    throw new Error("Your session has expired. Please log in again.");
  }
  if (options.asBlob && response.ok) return response.blob();

  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(readError(data, response.status));
  return data;
}

// Create a PDF report for one analysis and download it in the browser.
export async function downloadReportForAnalysis(analysisId) {
  const report = await api(`/api/reports/${analysisId}`, { method: "POST" });
  await downloadReport(report.report_id);
  return report;
}

export async function downloadReport(reportId) {
  const blob = await api(`/api/reports/${reportId}/download`, { asBlob: true });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `bi_report_${reportId}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
