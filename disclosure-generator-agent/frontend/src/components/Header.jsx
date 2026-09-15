import { API_BASE_URL } from "../api.js";

const HEALTH_STYLES = {
  checking: "bg-slate-100 text-slate-600",
  ok: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200",
  down: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200",
};

const HEALTH_DOT = {
  checking: "bg-slate-400 animate-pulse",
  ok: "bg-emerald-500",
  down: "bg-rose-500",
};

const HEALTH_LABELS = {
  checking: "Checking backend…",
  ok: "Backend online",
  down: "Backend unreachable",
};

export default function Header({ health }) {
  return (
    <header className="sticky top-0 z-10 -mx-4 mb-8 border-b border-slate-200/80 bg-slate-50/80 px-4 py-4 backdrop-blur-sm sm:mx-0 sm:rounded-2xl sm:border sm:px-6 sm:shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white shadow-sm">
            DG
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold tracking-tight text-slate-900">
              Disclosure Generator
              <span className="ml-2 font-medium text-slate-400">Test Console</span>
            </h1>
            <p className="truncate text-xs text-slate-500">{API_BASE_URL}</p>
          </div>
        </div>
        <span
          className={
            "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium " +
            HEALTH_STYLES[health]
          }
        >
          <span className={"h-1.5 w-1.5 rounded-full " + HEALTH_DOT[health]} />
          {HEALTH_LABELS[health]}
        </span>
      </div>
    </header>
  );
}
