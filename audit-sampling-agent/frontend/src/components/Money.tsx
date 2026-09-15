import { formatMoney } from "../lib/money";

export function Money({ value }: { value: string | null | undefined }) {
  const formatted = formatMoney(value);
  return <span className={formatted === "not run" ? "text-slate-400 italic" : ""}>{formatted}</span>;
}
