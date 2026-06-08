import "@testing-library/jest-dom/vitest";
// Eagerly initialize i18next before any component imports run. The
// next-intl compat shim at @/lib/next-compat/intl.tsx delegates to
// react-i18next + this config; without it, useTranslations() in a
// test would crash on the first call. en messages are statically
// imported so language lookups resolve synchronously.
import "../i18n/i18next";

import { cleanup } from "@testing-library/react";
import React from "react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import enMessages from "../../messages/en.json";
import { server } from "./mocks/server";

// `next-intl` is no longer a real dependency — the Vite alias
// (replicated in vitest.config.ts) redirects it to the production
// compat shim. This vi.mock provides a deterministic translation
// surface for tests that don't want to depend on react-i18next's
// internal subscription model. It mirrors the shim's `t` / `t.rich`
// / `t.raw` shape so test assertions don't drift.
function getNestedRaw(obj: unknown, path: string): unknown {
  if (!path) return obj;
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === "object" && part in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

// One factory used by both module-id paths. Inlined twice (not shared via
// vi.importMock) because vi.importMock from a setup-file mock factory
// deadlocks when both `next-intl` and the shim path are mocked — the second
// factory's awaited importMock waits for the first mock to resolve, but the
// first mock resolution is paused on whichever import the test made first,
// which leaves vitest's worker hung at module-load with no test ever running.
function makeIntlMock() {
  return {
    useTranslations: (namespace?: string) => {
      const ns = namespace ? getNestedRaw(enMessages, namespace) : enMessages;
      const lookup = (key: string): unknown => {
        const v = getNestedRaw(ns, key);
        return v === undefined ? (namespace ? `${namespace}.${key}` : key) : v;
      };
      const t = (key: string, params?: Record<string, unknown>) => {
        const raw = lookup(key);
        let rawStr = typeof raw === "string" ? raw : namespace ? `${namespace}.${key}` : key;
        if (!params) return rawStr;
        // Handle ICU plural: {name, plural, one {...} other {...}}
        rawStr = rawStr.replace(
          /\{(\w+),\s*plural,\s*((?:[^{}]|\{[^{}]*\})*)\}/g,
          (_full: string, name: string, branches: string) => {
            const value = Number(params[name]);
            const branchMap: Record<string, string> = {};
            const branchRe = /(\w+|=\d+)\s*\{([^{}]*)\}/g;
            let m: RegExpExecArray | null;
            while ((m = branchRe.exec(branches)) !== null) {
              branchMap[m[1]] = m[2];
            }
            let chosen = branchMap.other ?? "";
            if (`=${value}` in branchMap) chosen = branchMap[`=${value}`];
            else if (value === 1 && branchMap.one) chosen = branchMap.one;
            return chosen.replace(/#/g, String(value));
          },
        );
        return rawStr.replace(/\{(\w+)\}/g, (_: string, k: string) =>
          params[k] != null ? String(params[k]) : `{${k}}`,
        );
      };
      // Mock t.rich: render the message, replacing <tag>...</tag> and {placeholder} with React elements
      (
        t as unknown as {
          rich: (key: string, values?: Record<string, unknown>) => React.ReactNode;
        }
      ).rich = (key: string, values?: Record<string, unknown>) => {
        const rawVal = lookup(key);
        const raw = typeof rawVal === "string" ? rawVal : key;
        if (!values) return raw;
        const parts: React.ReactNode[] = [];
        const regex = /<(\w+)>(.*?)<\/\1>|\{(\w+)\}/g;
        let lastIndex = 0;
        let match: RegExpExecArray | null;
        let nodeKey = 0;
        while ((match = regex.exec(raw)) !== null) {
          if (match.index > lastIndex) {
            parts.push(raw.slice(lastIndex, match.index));
          }
          if (match[1]) {
            const fn = values[match[1]];
            if (typeof fn === "function") {
              parts.push(
                React.createElement(
                  React.Fragment,
                  { key: nodeKey++ },
                  (fn as (chunks: string) => React.ReactNode)(match[2]),
                ),
              );
            } else {
              parts.push(match[2]);
            }
          } else if (match[3]) {
            const v = values[match[3]];
            if (typeof v === "function") {
              parts.push(React.createElement(React.Fragment, { key: nodeKey++ }, (v as () => React.ReactNode)()));
            } else if (v != null) {
              parts.push(String(v));
            }
          }
          lastIndex = regex.lastIndex;
        }
        if (lastIndex < raw.length) parts.push(raw.slice(lastIndex));
        return React.createElement(React.Fragment, null, ...parts);
      };
      // Mock t.raw: returns the raw value (object/array/string) at the given key
      (t as unknown as { raw: (key: string) => unknown }).raw = (key: string) => {
        const v = getNestedRaw(ns, key);
        return v === undefined ? key : v;
      };
      return t;
    },
    useLocale: () => "en",
    NextIntlClientProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
  };
}

vi.mock("@/lib/next-compat/intl", () => makeIntlMock());
vi.mock("next-intl", () => makeIntlMock());

/**
 * The next-compat navigation shim (`@/lib/next-compat/navigation`) calls
 * `useNavigate` / `useLocation` / `useSearchParams` / `useParams` from
 * `react-router`. Those hooks throw when there's no `<Router>` ancestor —
 * which is exactly the situation in unit tests that render a component
 * in isolation. Mock the react-router hooks here so any `next/navigation`
 * import (which Vite redirects to the shim) Just Works in tests without
 * forcing every test file to wrap its render in `<MemoryRouter>`.
 */
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  // `<Link>` / `<NavLink>` from react-router crash with
  // "Cannot destructure property 'basename' of React.useContext(...)" when
  // rendered without a router ancestor. Substitute plain anchor renderers
  // so individual component tests don't need to wrap in `<MemoryRouter>`.
  const LinkStub = React.forwardRef<
    HTMLAnchorElement,
    Record<string, unknown> & { to?: unknown; children?: React.ReactNode }
  >(function LinkStub({ to, children, replace: _replace, prefetch: _prefetch, viewTransition: _vt, ...rest }, ref) {
    const href = typeof to === "string" ? to : "#";
    return React.createElement("a", { ref, href, ...rest }, children);
  });
  const NavLinkStub = React.forwardRef<
    HTMLAnchorElement,
    Record<string, unknown> & {
      to?: unknown;
      children?: React.ReactNode | ((p: { isActive: boolean }) => React.ReactNode);
    }
  >(function NavLinkStub({ to, children, className, style, ...rest }, ref) {
    const href = typeof to === "string" ? to : "#";
    const isActive = href === "/";
    const renderedChildren =
      typeof children === "function"
        ? (children as (p: { isActive: boolean }) => React.ReactNode)({
            isActive,
          })
        : children;
    const resolvedClass =
      typeof className === "function" ? (className as (p: { isActive: boolean }) => string)({ isActive }) : className;
    const resolvedStyle =
      typeof style === "function"
        ? (style as (p: { isActive: boolean }) => React.CSSProperties)({
            isActive,
          })
        : style;
    return React.createElement(
      "a",
      { ref, href, className: resolvedClass, style: resolvedStyle, ...rest },
      renderedChildren,
    );
  });
  return {
    ...actual,
    Link: LinkStub,
    NavLink: NavLinkStub,
    useNavigate: () => vi.fn(),
    useLocation: () => ({
      pathname: "/",
      search: "",
      hash: "",
      state: null,
      key: "default",
    }),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
    useParams: () => ({}),
  };
});

// Filter out jsdom localStorage file warnings
// These are internal to jsdom and don't affect our tests
const originalEmitWarning = process.emitWarning;
process.emitWarning = (warning: string | Error, ...args: unknown[]) => {
  const warningString = typeof warning === "string" ? warning : warning.message;
  if (warningString.includes("--localstorage-file")) {
    return; // Suppress this specific warning
  }
  return originalEmitWarning.call(process, warning, ...(args as [never, never]));
};

// Mock localStorage to avoid jsdom warnings
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (index: number) => {
      const keys = Object.keys(store);
      return keys[index] || null;
    },
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
});

// Mock matchMedia for the `useTheme` hook at `@/hooks/use-theme`
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// `next/dynamic` is no longer used directly — the compat shim at
// `src/lib/next-compat/dynamic.tsx` wraps `React.lazy` + `<Suspense>`,
// which works natively in jsdom. No vitest mock needed.

// Mock DOM APIs needed by ProseMirror/TipTap
if (typeof document !== "undefined") {
  // Mock elementFromPoint for ProseMirror position calculations
  document.elementFromPoint = vi.fn(() => null);
  document.elementsFromPoint = vi.fn(() => []);

  // Mock caretPositionFromPoint (alternative to caretRangeFromPoint)
  (document as any).caretPositionFromPoint = vi.fn(() => null);

  // Mock caretRangeFromPoint for position calculations
  if (!document.caretRangeFromPoint) {
    (document as any).caretRangeFromPoint = vi.fn(() => null);
  }
}

// Mock getClientRects and getBoundingClientRect for all elements
const mockRect = {
  x: 0,
  y: 0,
  width: 100,
  height: 20,
  top: 0,
  right: 100,
  bottom: 20,
  left: 0,
  toJSON: () => ({}),
};

const mockDOMRect = () => mockRect;

if (typeof Element !== "undefined") {
  Element.prototype.getClientRects = vi.fn(() => [mockRect] as any);
  Element.prototype.getBoundingClientRect = vi.fn(mockDOMRect);
}

if (typeof Range !== "undefined") {
  Range.prototype.getClientRects = vi.fn(() => [mockRect] as any);
  Range.prototype.getBoundingClientRect = vi.fn(mockDOMRect);
}

// Mock scrollIntoView and pointer capture (needed by Radix UI)
if (typeof Element !== "undefined") {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => false);
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
}

// Mock ResizeObserver for components that use it (e.g., ScrollArea)
global.ResizeObserver = class ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  constructor(_callback: ResizeObserverCallback) {}
} as any;

// Setup MSW
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
