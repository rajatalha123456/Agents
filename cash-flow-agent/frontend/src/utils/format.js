export function formatCurrency(value) {
  const num = Number(value ?? 0);
  return num.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function formatAmount(value, currency = "USD") {
  const num = Number(value ?? 0);
  try {
    return num.toLocaleString(undefined, { style: "currency", currency, maximumFractionDigits: 0 });
  } catch {
    return `${currency} ${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
}
