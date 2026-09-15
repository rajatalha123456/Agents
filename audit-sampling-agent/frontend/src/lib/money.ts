// Money never touches parseFloat. The API sends amounts as strings
// specifically so JavaScript floats never enter the picture; this module
// is the only place money is parsed or formatted anywhere in the app.
import Decimal from "decimal.js";

export function parseMoney(value: string | null | undefined): Decimal | null {
  if (value === null || value === undefined) return null;
  return new Decimal(value);
}

export function formatMoney(value: string | null | undefined, currency = "USD"): string {
  const d = parseMoney(value);
  if (d === null) return "not run";
  const sign = d.isNegative() ? "-" : "";
  const abs = d.abs().toFixed(2);
  const [whole, frac] = abs.split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const symbol = currency === "USD" ? "$" : currency + " ";
  return `${sign}${symbol}${withCommas}.${frac}`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "not run";
  return `${(value * 100).toFixed(digits)}%`;
}
