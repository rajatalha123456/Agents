import Field, { TextInput, NumberInput, DateInput } from "./Field.jsx";

export default function PayloadForm({ payload, onChange }) {
  const set = (key) => (e) => onChange({ ...payload, [key]: e.target.value });
  const setNumber = (key) => (e) =>
    onChange({ ...payload, [key]: e.target.value === "" ? "" : Number(e.target.value) });

  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Account ID">
        <TextInput value={payload.account_id} onChange={set("account_id")} />
      </Field>
      <Field label="Account name">
        <TextInput value={payload.account_name} onChange={set("account_name")} />
      </Field>

      <Field label="Currency">
        <TextInput value={payload.currency} onChange={set("currency")} />
      </Field>
      <Field label="Return %">
        <NumberInput value={payload.return_percent} onChange={setNumber("return_percent")} />
      </Field>

      <Field label="Period start">
        <DateInput value={payload.period_start} onChange={set("period_start")} />
      </Field>
      <Field label="Period end">
        <DateInput value={payload.period_end} onChange={set("period_end")} />
      </Field>

      <Field label="NAV">
        <NumberInput value={payload.nav} onChange={setNumber("nav")} />
      </Field>
      <Field label="Opening balance">
        <NumberInput value={payload.opening_balance} onChange={setNumber("opening_balance")} />
      </Field>
      <Field label="Closing balance">
        <NumberInput value={payload.closing_balance} onChange={setNumber("closing_balance")} />
      </Field>
    </div>
  );
}
