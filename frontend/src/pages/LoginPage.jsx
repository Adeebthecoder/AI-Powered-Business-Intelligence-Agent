// LoginPage.jsx
// Log in and sign up on one screen, with a tab to switch between them.

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../AppContext.jsx";
import { api, CREDIT_LINE } from "../api.js";
import { Logo } from "../components/Layout.jsx";

export default function LoginPage() {
  const { login } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login"); // "login" or "signup"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    if (mode === "signup" && password.length < 8) {
      setError("The password must have at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      let reply;
      if (mode === "login") {
        // The backend login uses the standard form format (username + password).
        reply = await api("/api/auth/login", {
          method: "POST",
          body: new URLSearchParams({ username: email, password }),
        });
      } else {
        reply = await api("/api/auth/signup", { method: "POST", body: { name, email, password } });
      }
      await login(reply);
      navigate("/datasets");
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-hero">
        <Logo />
        <h1>Ask your business data a question. Get an answer you can check.</h1>
        <ul>
          <li>Upload a CSV or Excel file and see it cleaned and summarised.</li>
          <li>Ask in plain English. The system writes safe, read-only SQL.</li>
          <li>Every number comes from your data, with a chart and the SQL to prove it.</li>
        </ul>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={handleSubmit}>
          <div className="tabs">
            <button type="button" className={mode === "login" ? "tab active" : "tab"}
                    onClick={() => { setMode("login"); setError(""); }}>
              Log in
            </button>
            <button type="button" className={mode === "signup" ? "tab active" : "tab"}
                    onClick={() => { setMode("signup"); setError(""); }}>
              Sign up
            </button>
          </div>

          {mode === "signup" && (
            <label className="field">
              <span>Full name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2}
                     autoComplete="name" />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                   autoComplete="email" />
          </label>
          <label className="field">
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   required autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "signup" && <small>At least 8 characters.</small>}
          </label>

          {error && <div className="alert alert-error" role="alert">{error}</div>}

          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
          </button>
          <p className="muted small center">
            For the demo account, see the README file.
          </p>
        </form>
        <p className="login-credit">{CREDIT_LINE}</p>
      </section>
    </div>
  );
}
