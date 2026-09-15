const CONFIDENCE_STYLES = {
  Low: 'bg-red-100 text-red-700',
  Medium: 'bg-amber-100 text-amber-700',
  High: 'bg-emerald-100 text-emerald-700',
}

const SEVERITY_STYLES = {
  Low: 'bg-slate-100 text-slate-700',
  Medium: 'bg-amber-100 text-amber-700',
  High: 'bg-red-100 text-red-700',
}

function Badge({ children, className = '' }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}

function Section({ title, children, count }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="flex items-center gap-2 text-base font-semibold text-slate-900">
        {title}
        {typeof count === 'number' && (
          <span className="text-sm font-normal text-slate-400">({count})</span>
        )}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function Empty({ label }) {
  return <p className="text-sm text-slate-400">{label}</p>
}

export default function ResultsView({ filename, result }) {
  const {
    contract_type,
    contract_type_confidence,
    psr,
    fees = [],
    loss_clauses = [],
    dates = [],
    conflicts = [],
    needs_human_review,
    review_notes,
  } = result

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <p className="text-sm text-slate-400">{filename}</p>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold text-slate-900">{contract_type}</h2>
          <Badge className={CONFIDENCE_STYLES[contract_type_confidence] || 'bg-slate-100 text-slate-700'}>
            {contract_type_confidence} confidence
          </Badge>
          {needs_human_review && (
            <Badge className="bg-red-100 text-red-700">Needs human review</Badge>
          )}
        </div>
        {needs_human_review && review_notes && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{review_notes}</p>
        )}
      </div>

      <Section title="Payment Services Regulations (PSR)">
        <div className="flex items-center gap-2">
          <Badge className={psr.applicable ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-700'}>
            {psr.applicable ? 'Applicable' : 'Not applicable'}
          </Badge>
        </div>
        {psr.applicable && (
          <div className="mt-3 space-y-2 text-sm text-slate-600">
            {psr.parties?.length > 0 && (
              <p>
                <span className="font-medium text-slate-800">Parties: </span>
                {psr.parties.join(', ')}
              </p>
            )}
            {psr.scope && (
              <p>
                <span className="font-medium text-slate-800">Scope: </span>
                {psr.scope}
              </p>
            )}
            {psr.regulatory_notes && (
              <p>
                <span className="font-medium text-slate-800">Regulatory notes: </span>
                {psr.regulatory_notes}
              </p>
            )}
          </div>
        )}
      </Section>

      <Section title="Fees & charges" count={fees.length}>
        {fees.length === 0 ? (
          <Empty label="No fees found." />
        ) : (
          <ul className="space-y-3">
            {fees.map((fee, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-3 text-sm">
                <p className="font-medium text-slate-800">{fee.description}</p>
                <div className="mt-1 flex flex-wrap gap-x-4 text-slate-500">
                  {fee.amount && <span>Amount: {fee.amount}</span>}
                  {fee.trigger && <span>Trigger: {fee.trigger}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Loss & liability clauses" count={loss_clauses.length}>
        {loss_clauses.length === 0 ? (
          <Empty label="No loss/liability clauses found." />
        ) : (
          <ul className="space-y-3">
            {loss_clauses.map((clause, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-800">{clause.clause_type}</span>
                  {clause.source_reference && (
                    <span className="text-xs text-slate-400">({clause.source_reference})</span>
                  )}
                </div>
                <p className="mt-1 text-slate-600">{clause.summary}</p>
                {clause.cap_or_limit && (
                  <p className="mt-1 text-slate-500">Cap/limit: {clause.cap_or_limit}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Key dates" count={dates.length}>
        {dates.length === 0 ? (
          <Empty label="No dates found." />
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {dates.map((date, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-3 text-sm">
                <span className="font-medium text-slate-800">{date.label}</span>
                <span className="ml-2 text-slate-500">{date.value || '—'}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Conflicts" count={conflicts.length}>
        {conflicts.length === 0 ? (
          <Empty label="No conflicting clauses found." />
        ) : (
          <ul className="space-y-3">
            {conflicts.map((conflict, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-3 text-sm">
                <Badge className={SEVERITY_STYLES[conflict.severity] || 'bg-slate-100 text-slate-700'}>
                  {conflict.severity} severity
                </Badge>
                <p className="mt-2 text-slate-600">{conflict.explanation}</p>
                <div className="mt-2 space-y-1 text-slate-500">
                  <p>A: {conflict.clause_a}</p>
                  <p>B: {conflict.clause_b}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
