/**
 * useSaveBoardAsPage (issue #1945): the one Save-as-page path both banner
 * faces call. The page is named in the APP's locale (useLocale + Intl), never
 * the browser's toLocaleString — a German user gets "Vom Board gespeichert
 * 17.10.2026, 23:42" — and the success toast carries an Open action.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

const { localeHolder } = vi.hoisted(() => ({ localeHolder: { current: "en" } }));

// The global setup stubs translations English-only. Swap in a stub that reads
// the active locale's bundle so the name and toasts are the real strings.
vi.mock("@/i18n/translations", async () => {
  const en = (await import("../../messages/en.json")).default as unknown as Record<string, Record<string, string>>;
  const de = (await import("../../messages/de.json")).default as unknown as Record<string, Record<string, string>>;
  const bundles: Record<string, Record<string, Record<string, string>>> = { en, de };
  return {
    useLocale: () => localeHolder.current,
    useTranslations: (namespace: string) => (key: string, params?: Record<string, unknown>) => {
      const raw = bundles[localeHolder.current][namespace][key];
      return raw.replace(/\{(\w+)\}/g, (_: string, k: string) => String(params?.[k] ?? `{${k}}`));
    },
  };
});

const push = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

import { useSaveBoardAsPage } from "@/hooks/use-save-board-as-page";

const GRID = [
  [8, 9, 63],
  [0, 0, 0],
];
const FLAGSHIP = { deviceType: "flagship", notesWide: 1, notesTall: 1 } as const;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function recordCreatePage(status = 201) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.post("/api/v1/pages", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      if (status >= 400) return HttpResponse.json({ detail: "nope" }, { status });
      return HttpResponse.json({ id: "p-42", ...body }, { status: 201 });
    }),
  );
  return bodies;
}

describe("useSaveBoardAsPage", () => {
  beforeEach(() => {
    localeHolder.current = "en";
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("names the page in the app's locale with a medium date and short time", async () => {
    localeHolder.current = "de";
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 17, 23, 42));
    const created = recordCreatePage();
    const { result } = renderHook(() => useSaveBoardAsPage(), { wrapper });

    await act(() => result.current.save(GRID, FLAGSHIP));

    expect(created[0].name).toBe("Vom Board 17.10.2026, 23:42");
  });

  it("names the page in English for an English app", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 17, 23, 42));
    const created = recordCreatePage();
    const { result } = renderHook(() => useSaveBoardAsPage(), { wrapper });

    await act(() => result.current.save(GRID, FLAGSHIP));

    // Intl writes a narrow no-break space before "PM" on current ICU.
    expect(String(created[0].name).replace(/\s/g, " ")).toBe("From board Oct 17, 2026, 11:42 PM");
  });

  it("posts the board's grid as a template page and returns the page", async () => {
    const created = recordCreatePage();
    const { result } = renderHook(() => useSaveBoardAsPage(), { wrapper });

    let page: { id: string } | undefined;
    await act(async () => {
      page = await result.current.save(GRID, FLAGSHIP);
    });

    expect(page?.id).toBe("p-42");
    expect(created[0]).toMatchObject({ type: "template", device_type: "flagship", template: ["HI{{red}}", ""] });
  });

  it("toasts success with an Open action that opens the new page in the editor", async () => {
    const success = vi.spyOn(toast, "success");
    recordCreatePage();
    const { result } = renderHook(() => useSaveBoardAsPage(), { wrapper });

    await act(() => result.current.save(GRID, FLAGSHIP));

    expect(success).toHaveBeenCalledTimes(1);
    const [message, options] = success.mock.calls[0] as [string, { action: { label: string; onClick: () => void } }];
    expect(message).toMatch(/^Saved “From board .*” as a page$/);
    expect(options.action.label).toBe("Open");
    options.action.onClick();
    expect(push).toHaveBeenCalledWith("/pages/edit/p-42");
  });

  it("toasts the failure and rethrows so the caller keeps its button", async () => {
    const error = vi.spyOn(toast, "error");
    recordCreatePage(500);
    const { result } = renderHook(() => useSaveBoardAsPage(), { wrapper });

    await act(async () => {
      await expect(result.current.save(GRID, FLAGSHIP)).rejects.toThrow();
    });

    expect(error).toHaveBeenCalledWith("Failed to save board as a page");
  });
});
