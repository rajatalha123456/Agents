import { useEffect, useState } from "react";
import Header from "./components/Header.jsx";
import SectionCard from "./components/SectionCard.jsx";
import PayloadForm from "./components/PayloadForm.jsx";
import AllocationEditor from "./components/AllocationEditor.jsx";
import FeesEditor from "./components/FeesEditor.jsx";
import LanguageSelector from "./components/LanguageSelector.jsx";
import PresetPicker from "./components/PresetPicker.jsx";
import SignedRunPanel from "./components/SignedRunPanel.jsx";
import ResultPanel from "./components/ResultPanel.jsx";
import Button from "./components/Button.jsx";
import { checkHealth, signPayload, generateDisclosure, ApiError } from "./api.js";
import { PRESETS } from "./presets.js";

export default function App() {
  const [health, setHealth] = useState("checking");
  const [payload, setPayload] = useState(PRESETS.valid.payload);
  const [runId, setRunId] = useState("RUN-0001");
  const [language, setLanguage] = useState("en");

  const [signing, setSigning] = useState(false);
  const [signError, setSignError] = useState(null);
  const [signedRunText, setSignedRunText] = useState("");

  const [genState, setGenState] = useState({ status: "idle", result: null, language: "en", error: null });

  useEffect(() => {
    checkHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("down"));
  }, []);

  const handleSign = async () => {
    setSigning(true);
    setSignError(null);
    try {
      const { body } = await signPayload({ runId, payload });
      setSignedRunText(JSON.stringify(body, null, 2));
    } catch (err) {
      setSignError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSigning(false);
    }
  };

  const handleGenerate = async () => {
    let signedRun;
    try {
      signedRun = JSON.parse(signedRunText);
    } catch {
      setGenState({ status: "error", result: null, language, error: "Signed run JSON is not valid JSON." });
      return;
    }

    setGenState({ status: "loading", result: null, language, error: null });
    try {
      const { body } = await generateDisclosure({ signedRun, language });
      setGenState({ status: body.status, result: body, language, error: null });
    } catch (err) {
      setGenState({
        status: "error",
        result: null,
        language,
        error: err instanceof ApiError ? err.message : String(err),
      });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 px-4 py-4 sm:py-8">
      <div className="mx-auto max-w-6xl">
        <Header health={health} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <SectionCard
              step={1}
              title="Calculation payload"
              description="This is the data your calc engine would already produce."
              actions={<PresetPicker onPick={setPayload} />}
            >
              <PayloadForm payload={payload} onChange={setPayload} />
            </SectionCard>

            <SectionCard title="Allocation">
              <AllocationEditor
                allocation={payload.allocation}
                onChange={(allocation) => setPayload({ ...payload, allocation })}
              />
            </SectionCard>

            <SectionCard title="Fees">
              <FeesEditor
                fees={payload.fees}
                onChange={(fees) => setPayload({ ...payload, fees })}
              />
            </SectionCard>
          </div>

          <div className="space-y-6">
            <SectionCard
              step={2}
              title="Sign & tamper"
              description="Signs locally with the dev private key (never do this outside local dev)."
            >
              <SignedRunPanel
                runId={runId}
                onRunIdChange={setRunId}
                onSign={handleSign}
                signing={signing}
                signError={signError}
                signedRunText={signedRunText}
                onSignedRunTextChange={setSignedRunText}
              />
            </SectionCard>

            <SectionCard
              step={3}
              title="Generate disclosure"
              actions={<LanguageSelector value={language} onChange={setLanguage} />}
            >
              <Button
                variant="primary"
                onClick={handleGenerate}
                disabled={!signedRunText.trim() || genState.status === "loading"}
                className="mb-4 w-full justify-center sm:w-auto"
              >
                {genState.status === "loading" ? "Generating…" : "Generate disclosure"}
              </Button>
              <ResultPanel state={genState} />
            </SectionCard>
          </div>
        </div>

        <footer className="mt-8 pb-4 text-center text-xs text-slate-400">
          Internal test console — not for production disclosure generation.
        </footer>
      </div>
    </div>
  );
}
