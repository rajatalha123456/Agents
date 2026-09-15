import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
const STORAGE_KEY = "audit_sampling_agent.theme";

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

function loadStored(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    // ignore
  }
  return "system";
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const initial = loadStored();
if (typeof document !== "undefined") applyTheme(initial);

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initial,
  setTheme: (theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore
    }
    applyTheme(theme);
    set({ theme });
  },
}));
