import { X } from "lucide-react";

export default function FormCard({ title, onClose, onSubmit, children, footer }) {
  return (
    <form onSubmit={onSubmit} className="card p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm font-semibold" style={{ color: "var(--ink-900)" }}>{title}</div>
        <button type="button" onClick={onClose} className="btn-ghost !px-1.5 !py-1.5">
          <X size={16} />
        </button>
      </div>
      {children}
      {footer}
    </form>
  );
}
