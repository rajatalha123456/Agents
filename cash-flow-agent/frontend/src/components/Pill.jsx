const TONE_STYLES = {
  success: { bg: "var(--success-50)", fg: "var(--success-600)" },
  warning: { bg: "var(--warning-50)", fg: "var(--warning-600)" },
  danger: { bg: "var(--danger-50)", fg: "var(--danger-600)" },
  brand: { bg: "var(--brand-50)", fg: "var(--brand-600)" },
  high: { bg: "var(--success-50)", fg: "var(--success-600)" },
  medium: { bg: "var(--warning-50)", fg: "var(--warning-600)" },
  low: { bg: "var(--danger-50)", fg: "var(--danger-600)" },
};

export default function Pill({ tone = "brand", children }) {
  const s = TONE_STYLES[tone] || TONE_STYLES.brand;
  return (
    <span className="pill" style={{ background: s.bg, color: s.fg }}>
      {children}
    </span>
  );
}
