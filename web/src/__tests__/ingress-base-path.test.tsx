/**
 * Reproduces Fiestaboard/FiestaBoard-Home-Assistant-App#48: under HA
 * Ingress the SPA is served from /api/hassio_ingress/<token>/ and the
 * add-on's nginx sub_filter rewrites the inlined React Router
 * hydration literal so `window.__reactRouterContext.basename` carries
 * the ingress prefix at runtime. API calls built from a hard-coded
 * "/api" constant escape that rewrite (the sub_filter only matches
 * `"/api/` with a trailing slash), land on the HA origin root, and
 * 404 against HA Core.
 *
 * These tests simulate the post-rewrite ingress page by setting the
 * hydration global, then assert that every API entry point targets
 * the prefixed URL. They also pin the direct-deployment contract
 * (no global -> plain /api/...) so the fix can't regress port access.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(async () => undefined),
}));

// Stable router mock — see login-page.test.tsx for why the object
// identity must not change between renders.
const stableRouter = {
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
};
const stableSearchParams = new URLSearchParams("");
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => stableRouter,
  useSearchParams: () => stableSearchParams,
  usePathname: () => "/login",
}));

import { fetchEventSource } from "@microsoft/fetch-event-source";

import { BootGate } from "@/components/boot-gate";
import type { ChatRequestBody } from "@/lib/ai-chat-types";
import { api } from "@/lib/api";
import { streamChat } from "@/lib/api-stream";

import LoginPage from "../../app/routes/login";

const INGRESS_PREFIX = "/api/hassio_ingress/test-token";

type IngressWindow = Window & {
  __reactRouterContext?: { basename?: string };
};
const win = window as IngressWindow;

let requestedUrls: string[];

/** Replace global fetch with a recorder that answers every endpoint. */
function stubFetch() {
  requestedUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      requestedUrls.push(url);
      // /auth/status needs a real shape so LoginPage renders a form
      // instead of redirecting away; everything else tolerates `{}`.
      const body = url.includes("/auth/status")
        ? {
            enabled: true,
            setup_required: false,
            authenticated: false,
            username: null,
            mode: "enabled",
            first_run: false,
          }
        : {};
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function enterIngressMode() {
  win.__reactRouterContext = { basename: `${INGRESS_PREFIX}/` };
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete win.__reactRouterContext;
  vi.clearAllMocks();
});

describe("API URLs under HA Ingress (issue #48)", () => {
  beforeEach(() => {
    enterIngressMode();
    stubFetch();
  });

  it("fetchApi-based calls carry the ingress prefix", async () => {
    await api.getConfig();
    expect(requestedUrls).toContain(`${INGRESS_PREFIX}/api/config`);
  });

  it("exportBackupUrl carries the ingress prefix", () => {
    expect(api.exportBackupUrl()).toBe(`${INGRESS_PREFIX}/api/backup/export`);
  });

  it("generateAiPage's bespoke fetch carries the ingress prefix", async () => {
    await api.generateAiPage({ prompt: "p", device_type: "flagship" } as Parameters<typeof api.generateAiPage>[0]);
    expect(requestedUrls).toContain(`${INGRESS_PREFIX}/api/pages/ai/generate`);
  });

  it("bespoke auth fetches carry the ingress prefix", async () => {
    await api.changePassword("old", "new");
    await api.changeUsername("old", "admin2");
    await api.setAuthPreference(true);
    await api.disableAuth("old");
    expect(requestedUrls).toEqual(
      expect.arrayContaining([
        `${INGRESS_PREFIX}/api/auth/change-password`,
        `${INGRESS_PREFIX}/api/auth/change-username`,
        `${INGRESS_PREFIX}/api/auth/preference`,
        `${INGRESS_PREFIX}/api/auth/disable`,
      ]),
    );
  });

  it("AI chat SSE stream carries the ingress prefix", async () => {
    await streamChat({ messages: [] } as unknown as ChatRequestBody, {});
    const url = vi.mocked(fetchEventSource).mock.calls[0]?.[0];
    expect(url).toBe(`${INGRESS_PREFIX}/api/pages/ai/chat`);
  });

  it("BootGate's health probe carries the ingress prefix", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <BootGate>
          <div>app</div>
        </BootGate>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(requestedUrls).toContain(`${INGRESS_PREFIX}/api/health`));
  });

  it("login page auth calls carry the ingress prefix", async () => {
    render(<LoginPage />);
    await waitFor(() => expect(requestedUrls).toContain(`${INGRESS_PREFIX}/api/auth/status`));

    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Username/i), "admin");
    await user.type(screen.getByLabelText(/Password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /Sign in/i }));
    await waitFor(() => expect(requestedUrls).toContain(`${INGRESS_PREFIX}/api/auth/login`));
  });

  it("401 login redirect navigates under the ingress prefix", async () => {
    vi.stubGlobal("location", {
      ...window.location,
      pathname: `${INGRESS_PREFIX}/settings`,
      search: "",
      assign: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );
    await expect(api.getConfig()).rejects.toThrow();
    // The redirect target is app-relative (the router re-applies the
    // basename after login), while the /login document URL itself
    // must carry the ingress prefix to reach the SPA at all.
    expect(window.location.assign).toHaveBeenCalledWith(`${INGRESS_PREFIX}/login?redirect=%2Fsettings`);
  });

  it("does not redirect-loop on the login page under ingress", async () => {
    vi.stubGlobal("location", {
      ...window.location,
      pathname: `${INGRESS_PREFIX}/login`,
      search: "",
      assign: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );
    await expect(api.getConfig()).rejects.toThrow();
    expect(window.location.assign).not.toHaveBeenCalled();
  });

  it("never double-prefixes the ingress path", async () => {
    await api.getConfig();
    for (const url of requestedUrls) {
      expect(url.match(/\/api\/hassio_ingress\//g)?.length ?? 0).toBeLessThanOrEqual(1);
    }
  });
});

describe("API URLs for direct deployments (no ingress)", () => {
  it("uses plain /api paths when the hydration global is absent", async () => {
    stubFetch();
    await api.getConfig();
    expect(requestedUrls).toContain("/api/config");
    expect(api.exportBackupUrl()).toBe("/api/backup/export");
  });

  it('uses plain /api paths for the default basename "/"', async () => {
    win.__reactRouterContext = { basename: "/" };
    stubFetch();
    await api.getConfig();
    expect(requestedUrls).toContain("/api/config");
  });

  it("401 login redirect stays un-prefixed", async () => {
    vi.stubGlobal("location", {
      ...window.location,
      pathname: "/settings",
      search: "",
      assign: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );
    await expect(api.getConfig()).rejects.toThrow();
    expect(window.location.assign).toHaveBeenCalledWith("/login?redirect=%2Fsettings");
  });
});
