import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--page-plane)" }}>
      <div className="text-center">
        <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4" style={{ background: "#e8f1fc" }}>
          <Compass size={26} color="var(--series-blue)" />
        </div>
        <div className="text-5xl font-bold mb-2" style={{ color: "var(--ink-primary)" }}>404</div>
        <p className="text-sm mb-5" style={{ color: "var(--ink-secondary)" }}>This page doesn't exist, or you don't have access to it.</p>
        <Link to="/" className="btn btn-primary">Back to dashboard</Link>
      </div>
    </div>
  );
}
