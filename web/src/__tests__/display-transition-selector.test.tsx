import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DisplayTransition } from "@/components/displays/display-transition";
import type { BoardInstance } from "@/lib/api";

import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

const base = {
  id: "demo",
  name: "Demo",
  output: "vestaboard",
  device_type: "flagship",
  transition: "row",
} as BoardInstance;
function setup(board = base) {
  server.use(
    http.get("/api/outputs", () => HttpResponse.json(mockOutputs)),
    http.get("/api/settings/plugins", () => HttpResponse.json({ transition_plugins_enabled: false })),
  );
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplayTransition board={board} onChange={onChange} />
    </QueryClientProvider>,
  );
  return onChange;
}

afterEach(() => document.documentElement.classList.remove("reduce-motion"));

describe("compact display transition", () => {
  it("demonstrates a native selection once without needing Replay", async () => {
    setup();
    const preview = await screen.findByTestId("transition-preview");
    await waitFor(() => expect(preview.querySelector("[data-native-strategy='row'] span")).toHaveStyle({animation:"display-order-reveal 180ms both"}));
  });

  it("honors reduced motion with a settled preview and disabled replay", async () => {
    document.documentElement.classList.add("reduce-motion");
    setup();
    const replay = await screen.findByRole("button", { name: "Replay preview" });
    await waitFor(() => expect(replay).toBeDisabled());
    expect(screen.getByText("Reduced motion is on. The preview shows the settled message.")).toBeInTheDocument();
  });

  it("explains an LED transition's adjusted cadence beside the single preview", async () => {
    setup({ ...base, output: "pixoo", device_model: "divoom_pixoo64", transition: "flip" });
    const preview = await screen.findByTestId("transition-preview");
    expect(screen.getByText(/Runs as:/)).toHaveTextContent(/200/);
    expect(preview.querySelector("[data-transition='flip']")).toBeInTheDocument();
  });

  it("uses a selector and one local replay preview without saving or sending", async () => {
    const writes: string[] = [];
    server.use(
      http.post(/\/api\/.*/, ({ request }) => {
        writes.push(request.url);
        return HttpResponse.json({});
      }),
    );
    const onChange = setup();
    expect(await screen.findByRole("combobox", { name: "Transition" })).toBeInTheDocument();
    const replay = await screen.findByRole("button", { name: "Replay preview" });
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.getAllByTestId("transition-preview")).toHaveLength(1);
    await userEvent.click(replay);
    expect(onChange).not.toHaveBeenCalled();
    expect(writes).toEqual([]);
  });

  it("keeps an unsupported saved native strategy visible without silently saving a fallback", async () => {
    const onChange = setup({ ...base, transition: "legacy-strategy" });
    const selector = await screen.findByRole("combobox", { name: "Transition" });
    expect(selector).toHaveTextContent("legacy-strategy");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows plugin preview unavailable instead of a fabricated animation", async () => {
    setup({ ...base, transition: "plugin:retired" });
    expect(await screen.findByText("Preview unavailable for this transition plugin.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replay preview" })).not.toBeInTheDocument();
  });

  it("selects a native strategy through the keyboard accessible menu", async () => {
    const onChange = setup();
    await userEvent.click(await screen.findByRole("combobox", { name: "Transition" }));
    await screen.findByRole("option", { name: "Diagonal" });
    await userEvent.keyboard("{End}{ArrowUp}{Enter}");
    expect(onChange).toHaveBeenCalledWith({ transition: "diagonal" });
  });

  it("keeps LED device default distinct from an explicit None and offers adjusted device entries", async () => {
    const onChange = setup({ ...base, output: "pixoo", device_model: "divoom_pixoo64", transition: undefined });
    const selector = await screen.findByRole("combobox", { name: "Transition" });
    expect(selector).toHaveTextContent("Device default");
    await userEvent.click(selector);
    expect(await screen.findByRole("option", { name: "Flip" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: /^None/ }));
    expect(onChange).toHaveBeenCalledWith({ transition: "none" });
  });
});
