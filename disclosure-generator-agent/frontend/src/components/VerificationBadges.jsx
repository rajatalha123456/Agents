function Badge({ label, ok }) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border " +
        (ok
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : "bg-rose-50 text-rose-700 border-rose-200")
      }
    >
      {ok ? "✓" : "✗"} {label}
    </span>
  );
}

export default function VerificationBadges({ verification }) {
  if (!verification) return null;
  return (
    <div className="flex flex-wrap gap-2">
      <Badge label="Signature" ok={verification.signature_valid} />
      <Badge label="Freshness" ok={verification.freshness_valid} />
      <Badge label="Sanity" ok={verification.sanity_valid} />
    </div>
  );
}
