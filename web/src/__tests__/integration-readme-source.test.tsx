import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { IntegrationReadme } from "@/components/integrations/integration-readme";

vi.mock("@/lib/github", () => ({
  fetchPluginReadme: vi.fn(async (repository: string) => ({
    markdown: `README from ${repository.split("/").at(-1)}`,
    resolvedBranch: "main",
  })),
  rewriteMarkdownImageUrls: (value: string) => value,
  rewriteMarkdownRepoLinks: (value: string) => value,
}));

it("nests README sections below the integration heading and clamps deeper sections at heading six", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <IntegrationReadme
        pluginId="weather"
        documentation={
          "# Guide\n\nBody copy.\n\n## Setup\n\n### Details\n\n#### Advanced\n\n##### Notes\n\n###### Appendix"
        }
      />
    </QueryClientProvider>,
  );
  for (const [name, level] of [
    ["Guide", 3],
    ["Setup", 4],
    ["Details", 5],
    ["Advanced", 6],
    ["Notes", 6],
    ["Appendix", 6],
  ] as const) {
    expect(screen.getByRole("heading", { name, level })).toBeInTheDocument();
  }
});

it("refreshes README when an installed plugin changes repository while keeping its ID and branch", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <IntegrationReadme pluginId="weather" repository="https://github.com/example/original" branch="main" />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("README from original")).toBeInTheDocument();
  view.rerender(
    <QueryClientProvider client={client}>
      <IntegrationReadme pluginId="weather" repository="https://github.com/example/fork" branch="main" />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("README from fork")).toBeInTheDocument();
  expect(screen.queryByText("README from original")).not.toBeInTheDocument();
});
