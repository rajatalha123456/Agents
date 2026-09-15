import { Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(form);
      navigate("/");
    } catch (err) {
      const data = err.response?.data;
      setError(data ? Object.values(data).flat().join(" ") : "Registration failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center text-white mb-3"
            style={{ background: "linear-gradient(135deg, var(--brand-500), var(--brand-700))" }}
          >
            <Wallet size={20} />
          </div>
          <div className="text-lg font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink-900)" }}>
            Cash-flow &amp; Liquidity Forecast
          </div>
        </div>

        <form onSubmit={handleSubmit} className="card p-6">
          <h1 className="text-base font-semibold mb-4" style={{ color: "var(--ink-900)" }}>Create an account</h1>
          {error && <div className="text-sm mb-3" style={{ color: "var(--danger-600)" }}>{error}</div>}
          <label className="block mb-3">
            <span className="field-label">Username</span>
            <input
              className="input"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
              autoFocus
            />
          </label>
          <label className="block mb-3">
            <span className="field-label">Email</span>
            <input
              type="email"
              className="input"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </label>
          <label className="block mb-5">
            <span className="field-label">Password</span>
            <input
              type="password"
              className="input"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? "Creating account..." : "Register"}
          </button>
          <div className="text-sm mt-4 text-center" style={{ color: "var(--ink-500)" }}>
            Already have an account?{" "}
            <Link to="/login" className="font-medium" style={{ color: "var(--brand-600)" }}>Log in</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
