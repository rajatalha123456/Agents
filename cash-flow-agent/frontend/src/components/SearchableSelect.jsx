import { ChevronDown, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export default function SearchableSelect({ options, value, onChange, placeholder = "Select..." }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = options.find(([v]) => v === value);
  const q = query.trim().toLowerCase();
  const filtered = q
    ? options.filter(([v, l]) => v.toLowerCase().includes(q) || l.toLowerCase().includes(q))
    : options;

  function select(v) {
    onChange(v);
    setOpen(false);
    setQuery("");
  }

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="input flex items-center justify-between gap-2"
      >
        <span className="truncate" style={!selected ? { color: "var(--ink-400)" } : undefined}>
          {selected ? `${selected[0]} — ${selected[1]}` : placeholder}
        </span>
        <ChevronDown size={16} className="shrink-0" style={{ color: "var(--ink-400)" }} />
      </button>

      {open && (
        <div
          className="absolute z-20 mt-1 w-full card overflow-hidden flex flex-col"
          style={{ maxHeight: "16rem" }}
        >
          <div className="p-2" style={{ borderBottom: "1px solid var(--border)" }}>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--ink-400)" }} />
              <input
                autoFocus
                className="input !pl-8 !py-1.5 text-sm"
                placeholder="Type to search..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setOpen(false);
                  if (e.key === "Enter" && filtered.length > 0) select(filtered[0][0]);
                }}
              />
            </div>
          </div>
          <div className="overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-sm" style={{ color: "var(--ink-400)" }}>No matches</div>
            )}
            {filtered.map(([v, l]) => (
              <button
                key={v}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(v)}
                className={`combobox-option ${v === value ? "selected" : ""}`}
              >
                <span className="font-medium">{v}</span> — {l}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
