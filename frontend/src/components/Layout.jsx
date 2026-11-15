// Layout.jsx
// The frame around every page: sidebar on the left, page content, footer.

import { NavLink } from "react-router-dom";
import { useApp } from "../AppContext.jsx";
import { CREDIT_LINE } from "../api.js";

// Simple line icons, drawn as SVG so no icon library is needed.
const ICONS = {
  datasets: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  overview: "M4 20V10m6 10V4m6 16v-8m4 8H2",
  ask: "M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.6A8 8 0 1 1 21 12z",
  history: "M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4",
  forecast: "M3 17l6-6 4 4 8-8m0 0h-5m5 0v5",
  reports: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  admin: "M12 3l8 3v6c0 4.5-3.2 8.3-8 9-4.8-.7-8-4.5-8-9V6z",
};

function Icon({ name }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

export function Logo() {
  return (
    <div className="logo">
      <span className="logo-mark" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 18 18">
          <rect x="2" y="9" width="3" height="7" rx="1" fill="white" />
          <rect x="7.5" y="5" width="3" height="11" rx="1" fill="white" />
          <rect x="13" y="2" width="3" height="14" rx="1" fill="white" />
        </svg>
      </span>
      <span>
        <strong>BI Agent</strong>
        <small>AI-Powered Business Intelligence</small>
      </span>
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout, datasetId, health } = useApp();
  const links = [
    { to: "/datasets", label: "Datasets", icon: "datasets", end: true },
    { to: datasetId ? `/datasets/${datasetId}` : "/datasets", label: "Overview", icon: "overview", disabled: !datasetId },
    { to: "/ask", label: "Ask", icon: "ask" },
    { to: "/history", label: "History", icon: "history" },
    { to: "/forecast", label: "Forecast", icon: "forecast" },
    { to: "/reports", label: "Reports", icon: "reports" },
  ];
  if (user.role === "admin") links.push({ to: "/admin", label: "Admin", icon: "admin" });

  return (
    <div className="shell">
      <aside className="sidebar">
        <Logo />
        <nav>
          {links.map((link) =>
            link.disabled ? (
              <span key={link.label} className="nav-link disabled" title="Upload a dataset first">
                <Icon name={link.icon} />
                {link.label}
              </span>
            ) : (
              <NavLink key={link.label} to={link.to} end={link.end}
                       className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
                <Icon name={link.icon} />
                {link.label}
              </NavLink>
            )
          )}
        </nav>

        <div className="sidebar-bottom">
          {health && (
            <div className={`mode-chip mode-${health.llm_mode}`}
                 title={health.llm_mode === "mock"
                   ? "Mock mode: fixed demo questions, no API calls"
                   : `Live mode: ${health.llm_model}`}>
              <span className="dot" />
              AI mode: {health.llm_mode}
            </div>
          )}
          <div className="user-box">
            <div className="avatar">{user.name.slice(0, 1).toUpperCase()}</div>
            <div className="user-text">
              <strong>{user.name}</strong>
              <small>{user.role === "admin" ? "Admin" : "User"} · {user.email}</small>
            </div>
          </div>
          <button className="btn btn-ghost btn-block" onClick={logout}>
            Log out
          </button>
        </div>
      </aside>

      <div className="main">
        <main className="content">{children}</main>
        <footer className="footer">{CREDIT_LINE}</footer>
      </div>
    </div>
  );
}
