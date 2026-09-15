export default function DisclaimerFooter() {
  return (
    <footer
      className="text-center text-xs py-3 px-4"
      style={{ borderTop: "1px solid var(--border)", color: "var(--ink-400)" }}
    >
      Forecasts are based on the data you provide and general assumptions. They are estimates only
      and do not guarantee future financial outcomes.
    </footer>
  );
}
