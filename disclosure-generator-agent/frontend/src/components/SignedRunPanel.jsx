import Button from "./Button.jsx";
import Field, { TextInput } from "./Field.jsx";

function corruptSignature(signedRunText) {
  try {
    const obj = JSON.parse(signedRunText);
    obj.signature = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";
    return JSON.stringify(obj, null, 2);
  } catch {
    return signedRunText;
  }
}

function backdateSignedAt(signedRunText, hoursAgo) {
  try {
    const obj = JSON.parse(signedRunText);
    const backdated = new Date(Date.now() - hoursAgo * 3600 * 1000);
    obj.signed_at = backdated.toISOString();
    return JSON.stringify(obj, null, 2);
  } catch {
    return signedRunText;
  }
}

export default function SignedRunPanel({
  runId,
  onRunIdChange,
  onSign,
  signing,
  signError,
  signedRunText,
  onSignedRunTextChange,
}) {
  const hasSignedRun = signedRunText.trim().length > 0;

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <Field label="Run ID">
          <TextInput value={runId} onChange={(e) => onRunIdChange(e.target.value)} />
        </Field>
        <Button variant="primary" onClick={onSign} disabled={signing}>
          {signing ? "Signing…" : "Sign payload (dev key)"}
        </Button>
      </div>

      {signError && (
        <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
          {signError}
        </p>
      )}

      {hasSignedRun && (
        <>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-600">
              Signed run (editable — hand-edit to test tampering)
            </span>
            <div className="flex gap-2">
              <Button
                variant="danger"
                onClick={() => onSignedRunTextChange(corruptSignature(signedRunText))}
                title="Replace the signature with garbage, to test signature verification"
              >
                Corrupt signature
              </Button>
              <Button
                variant="danger"
                onClick={() => onSignedRunTextChange(backdateSignedAt(signedRunText, 48))}
                title="Set signed_at 48h in the past, to test freshness rejection"
              >
                Backdate 48h
              </Button>
            </div>
          </div>
          <textarea
            className="w-full h-56 font-mono text-xs rounded-md border border-slate-300 p-3 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            spellCheck={false}
            value={signedRunText}
            onChange={(e) => onSignedRunTextChange(e.target.value)}
          />
        </>
      )}
    </div>
  );
}
