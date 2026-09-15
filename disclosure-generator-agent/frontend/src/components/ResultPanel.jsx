import VerificationBadges from "./VerificationBadges.jsx";
import DisclosureText from "./DisclosureText.jsx";

function StatusPill({ status }) {
  const styles = {
    success: "bg-emerald-100 text-emerald-800",
    refused: "bg-amber-100 text-amber-800",
    error: "bg-rose-100 text-rose-800",
    loading: "bg-slate-100 text-slate-600",
  };
  const labels = {
    success: "Success",
    refused: "Refused",
    error: "Error",
    loading: "Generating…",
  };
  return (
    <span className={"text-xs font-semibold px-3 py-1 rounded-full " + styles[status]}>
      {labels[status]}
    </span>
  );
}

export default function ResultPanel({ state }) {
  const { status, result, language, error } = state;

  if (status === "idle") {
    return (
      <p className="text-sm text-slate-400">
        Sign a payload and click "Generate disclosure" to see the result here.
      </p>
    );
  }

  if (status === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <StatusPill status="loading" />
        Waiting for the LLM backend — this can take a while on CPU-only Ollama.
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="space-y-2">
        <StatusPill status="error" />
        <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
          {error}
        </p>
      </div>
    );
  }

  const isSuccess = result?.status === "success";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <StatusPill status={isSuccess ? "success" : "refused"} />
        <VerificationBadges verification={result?.verification} />
      </div>

      {isSuccess ? (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
          <DisclosureText text={result.disclosure} language={language} />
        </div>
      ) : (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          {result?.reason || "Generation was refused."}
        </p>
      )}

      <details className="text-xs text-slate-500">
        <summary className="cursor-pointer select-none">Raw response JSON</summary>
        <pre className="mt-2 bg-slate-900 text-slate-100 rounded-md p-3 overflow-x-auto">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}
