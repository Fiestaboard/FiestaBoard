import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type Theme = "light" | "dark" | "system";
type Resolved = "light" | "dark";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (next: Theme) => void;
  resolvedTheme: Resolved;
};

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPrefers(): Resolved {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "light";
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function applyClass(resolved: Resolved): void {
  if (typeof document === "undefined") return;
  const cl = document.documentElement.classList;
  if (resolved === "dark") cl.add("dark");
  else cl.remove("dark");
}

type ThemeProviderProps = {
  children: React.ReactNode;
  // Accepted-and-ignored props for source compatibility with prior
  // `next-themes` call sites. The hook always uses the `dark` class on
  // <html> and exposes `system` / `light` / `dark` choices.
  attribute?: string;
  defaultTheme?: Theme;
  enableSystem?: boolean;
  disableTransitionOnChange?: boolean;
  storageKey?: string;
};

export function ThemeProvider({ children, defaultTheme }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return defaultTheme ?? "system";
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
    return defaultTheme ?? "system";
  });
  const [systemResolved, setSystemResolved] = useState<Resolved>(systemPrefers);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = () => setSystemResolved(mql.matches ? "dark" : "light");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const resolvedTheme: Resolved = theme === "system" ? systemResolved : theme;

  useEffect(() => {
    applyClass(resolvedTheme);
  }, [resolvedTheme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, resolvedTheme }),
    [theme, setTheme, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx) return ctx;
  // Fallback so isolated components and tests that don't wrap in a
  // provider still get a sane shape — matches next-themes' permissive
  // behavior of returning a usable object outside the provider.
  return {
    theme: "system",
    setTheme: () => {},
    resolvedTheme: systemPrefers(),
  };
}
