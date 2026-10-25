/**
 * The MCP token reveal dialog shows the freshly minted token once; its Copy
 * buttons are the only way to take the token and the client config away.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { McpSettings } from "@/components/settings/mcp-settings";

import { server } from "./mocks/server";

const MINTED_TOKEN = "test_copied_mcp_token";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("McpSettings token reveal copy", () => {
  it("copies the minted token to the clipboard", async () => {
    let minted = false;
    server.use(
      http.get("/api/auth/mcp-token", () =>
        HttpResponse.json(minted ? { configured: true, source: "stored" } : { configured: false, source: "none" }),
      ),
      http.post("/api/auth/mcp-token", () => {
        minted = true;
        return HttpResponse.json({ token: MINTED_TOKEN }, { status: 201 });
      }),
    );
    const user = userEvent.setup();

    render(<McpSettings />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: "Generate token" }));
    await user.click(await screen.findByRole("button", { name: "Generate" }));
    await screen.findByText(MINTED_TOKEN);

    // The token's Copy button comes first; the config snippet's follows it.
    await user.click(screen.getAllByRole("button", { name: "Copy" })[0]);

    await expect(navigator.clipboard.readText()).resolves.toBe(MINTED_TOKEN);
  });
});
