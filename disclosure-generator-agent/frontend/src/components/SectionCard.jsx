export default function SectionCard({ step, title, description, children, actions }) {
  return (
    <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow p-6">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 mb-5">
        <div className="flex items-start gap-3 min-w-0">
          {step && (
            <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">
              {step}
            </span>
          )}
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-800 tracking-wide uppercase">
              {title}
            </h2>
            {description && (
              <p className="text-xs text-slate-500 mt-1">{description}</p>
            )}
          </div>
        </div>
        {actions && <div className="flex flex-wrap gap-2 shrink-0">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
