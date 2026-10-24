import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { StepChooseOutput } from "@/components/wizard/step-choose-output";
import type { AvailableOutput } from "@/lib/api";

import { server } from "./mocks/server";

const outputs: AvailableOutput[] = Array.from({ length: 31 }, (_, i) => ({
  id: `sign_${i}`,
  name: `Sign ${i}`,
  description: "A display plugin.",
  icon: null,
  source: "registry",
  installed: false,
  builtin: false,
  beta_gated: false,
  available: true,
  needs_network: true,
  output_api: 1,
  display: {
    category: i === 30 ? "Ambient sculptures" : "LED signs",
    manufacturer: i === 30 ? "Orbit" : "Acme",
    models: [`Model ${i}`],
    keywords: [],
  },
}));

function Chooser() {
  const [value, setValue] = useState<string | null>(null);
  const [valid, setValid] = useState(false);
  return (
    <>
      <StepChooseOutput value={value} onChange={(o) => setValue(o.id)} onValidChange={setValid} />
      <button disabled={!valid}>Continue</button>
    </>
  );
}
function setup(status = "available") {
  server.use(http.get("/api/outputs/catalog", () => HttpResponse.json({ outputs, registry_status: status })));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Chooser />
    </QueryClientProvider>,
  );
}

describe("display catalog", () => {
  it("finds a product by manufacturer and model beyond the first page", async () => {
    setup();
    const search = await screen.findByRole("searchbox", { name: "Search displays" });
    expect(screen.getAllByRole("radio")).toHaveLength(12);
    await userEvent.type(search, "orbit model 30");
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /Sign 30/ })).toBeInTheDocument();
  });
  it("offers a category supplied by a new plugin without core-specific UI", async () => {
    setup();
    await userEvent.click(await screen.findByLabelText("Display category"));
    await userEvent.click(await screen.findByRole("option", { name: "Ambient sculptures" }));
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /Sign 30/ })).toBeInTheDocument();
  });
  it("keeps selection visible and valid when changing pages and filtering to no matches", async () => {
    setup();
    await userEvent.click(await screen.findByRole("radio", { name: /Sign 0/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next results" }));
    expect(screen.getByRole("radio", { name: /Sign 12/ })).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "missing display");
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.getByText("Selected: Sign 0")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("radio")).toHaveLength(12);
  });
  it("discloses an incomplete catalog, retains choices and retries", async () => {
    setup("unavailable");
    const alert = await screen.findByTestId("catalog-unavailable");
    expect(alert).toHaveTextContent("Marketplace unavailable");
    expect(screen.getAllByRole("radio")).toHaveLength(12);
    server.use(http.get("/api/outputs/catalog", () => HttpResponse.json({ outputs, registry_status: "available" })));
    await userEvent.click(within(alert).getByRole("button", { name: "Retry marketplace" }));
    expect(await screen.findByRole("searchbox")).toBeInTheDocument();
    await screen.findByText("All displays");
  });
});
