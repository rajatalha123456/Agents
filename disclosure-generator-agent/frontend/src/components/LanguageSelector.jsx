const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "ur", label: "اردو (Urdu)" },
  { value: "ar", label: "العربية (Arabic)" },
];

export default function LanguageSelector({ value, onChange }) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.value}
          type="button"
          onClick={() => onChange(lang.value)}
          className={
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors " +
            (value === lang.value
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-slate-500 hover:text-slate-800")
          }
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
