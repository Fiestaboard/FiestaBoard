import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createRef, type ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { PageBuilder, type PageBuilderHandle } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockTemplateVariables } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

const board = { id: "test-board", name: "Kitchen board", device_type: "flagship", enabled: true, board_color: "black" };

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function viewport(width: number) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query) =>
      ({
        matches:
          (width < 1024 && query === "(max-width: 1023px)") ||
          (width < 768 && query.includes("767px")) ||
          (width < 640 && query.includes("639px")),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

function baseline() {
  server.use(
    http.get("/api/v1/boards/test-board", () =>
      HttpResponse.json({ ...board, drawing: { source: "baseline", features: {} } }),
    ),
  );
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  viewport(1440);
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({ boards: [board], devices: ["flagship"], board_type: "black" }),
    ),
    http.get("/api/v1/boards/test-board", () =>
      HttpResponse.json({ ...board, drawing: { source: "profile", features: {} } }),
    ),
    http.get("/api/plugins/:pluginId/manifest", () => HttpResponse.json({ variables: {} })),
    http.get("/api/v1/variables", () => HttpResponse.json(mockTemplateVariables)),
    http.get("/api/v1/functions", () => HttpResponse.json({ functions: {} })),
    http.post("/api/templates/render", async ({ request }) => {
      const body = (await request.json()) as { template: string[] };
      const lines = body.template.map((line) => line.toUpperCase());
      return HttpResponse.json({ rendered: lines.join("\n"), lines, line_count: lines.length });
    }),
  );
});

// Losing the baseline toolbar prevents valid plain-template insertions and hides
// the reason display-dependent tools are unavailable.
it.each([390, 1440])("keeps supported H3 tools and explains disabled tools at %ipx", async (width) => {
  viewport(width);
  baseline();
  const { container } = render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await screen.findByText("Can’t tell what this display draws");
  expect(await screen.findByRole("button", { name: "Variables" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Formula" })).toBeEnabled();
  for (const name of ["Colors", "Formatting"]) {
    const tool = screen.getByRole("button", { name });
    expect(tool).toBeDisabled();
    expect(tool).toHaveAccessibleDescription(/display type unknown/i);
  }
  expect(container.querySelector('[data-slot="board-preview-mode-toggle"]')).not.toBeInTheDocument();
  if (width === 390) {
    expect(screen.getByRole("button", { name: "Variables" }).closest("section")).toHaveAccessibleName(/editor tools/i);
  }
});

// A disconnected warning leaves the preview looking like a supported hardware
// renderer. The warning and plain output must remain one accessible surface.
it("groups the H3 warning with its plain-text preview", async () => {
  baseline();
  const { container } = render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  const warning = await screen.findByText("Can’t tell what this display draws");
  fireEvent.change(screen.getByRole("textbox", { name: /template/i }), { target: { value: "Open today" } });
  const preview = container.querySelector('[data-slot="editor-preview"]')!;
  expect(preview).toContainElement(warning);
  expect(within(preview as HTMLElement).getByText("Plain text")).toBeInTheDocument();
  await waitFor(() => expect(warning.closest('[role="alert"]')).toHaveTextContent("OPEN TODAY"));
  expect(screen.getByText(/template · plain text only/i)).toBeInTheDocument();
});

// Insertion must replace the selected source range, preserving surrounding
// casing and template bytes instead of appending to the wrong line.
it("inserts an H3 variable at the textarea selection", async () => {
  baseline();
  const user = userEvent.setup();
  const ref = createRef<PageBuilderHandle>();
  render(<PageBuilder ref={ref} onClose={vi.fn()} />, { wrapper: Wrapper });
  await screen.findByText("Can’t tell what this display draws");
  const input = screen.getByRole("textbox", { name: /template/i }) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "Open HERE today" } });
  input.focus();
  input.setSelectionRange(5, 9);
  await user.click(await screen.findByRole("button", { name: "Variables" }));
  await user.click(await screen.findByRole("button", { name: /^temperature/i }));
  expect(input).toHaveValue("Open {{weather.temperature}} today");
  await waitFor(() => expect(input).toHaveFocus());
  expect(ref.current?.hasUnsavedChanges()).toBe(true);
});

it("inserts a validated H3 formula at the textarea selection", async () => {
  baseline();
  const user = userEvent.setup();
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await screen.findByText("Can’t tell what this display draws");
  const input = screen.getByRole("textbox", { name: /template/i }) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "Open HERE today" } });
  input.focus();
  input.setSelectionRange(5, 9);
  await user.click(await screen.findByRole("button", { name: "Formula" }));
  const dialog = await screen.findByRole("dialog", { name: "Formula" });
  const expression = await within(dialog).findByRole("textbox");
  await user.click(expression);
  await user.paste("1 + 1");
  const insert = within(dialog).getByRole("button", { name: /^Insert/ });
  await waitFor(() => expect(insert).toBeEnabled());
  await user.click(insert);
  expect(input).toHaveValue("Open {{= 1 + 1 }} today");
  await waitFor(() => expect(input).toHaveFocus());
  expect(input.selectionStart).toBe(17);
});

// The start actions are useful only before content exists; inserting through
// them must modify the same document and stop presenting the empty state.
it.each([390, 1440])("starts an empty new page with a prompt and working variable action at %ipx", async (width) => {
  viewport(width);
  const user = userEvent.setup();
  const ref = createRef<PageBuilderHandle>();
  render(<PageBuilder ref={ref} onClose={vi.fn()} />, { wrapper: Wrapper });
  const insert = await screen.findByRole("button", { name: "Insert a variable" });
  expect(await screen.findByText(/Type what the Kitchen board (?:should say|says)…/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Browse Staff Picks" })).toHaveAttribute("href", "/picks");
  expect(ref.current?.hasUnsavedChanges()).toBe(false);
  await user.click(insert);
  await user.click(await screen.findByRole("button", { name: /^temperature/i }));
  await waitFor(() => expect(ref.current?.getCurrentPage()?.template).toContain("{{weather.temperature}}"));
  expect(screen.queryByRole("button", { name: "Insert a variable" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Browse Staff Picks" })).not.toBeInTheDocument();
  expect(ref.current?.hasUnsavedChanges()).toBe(true);
});

it("does not show new-page starter actions for a saved page", async () => {
  render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: Wrapper });
  await screen.findByDisplayValue("Weather Page");
  expect(screen.queryByRole("button", { name: "Insert a variable" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Browse Staff Picks" })).not.toBeInTheDocument();
});

it("keeps leading whitespace when the new page receives its first plain-text edit", async () => {
  const user = userEvent.setup();
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await user.click(await screen.findByRole("button", { name: "Plain Text" }));
  const input = screen.getByRole("textbox", { name: /template/i });
  fireEvent.change(input, { target: { value: " " } });
  expect(input).toHaveValue(" ");
  expect(screen.queryByRole("button", { name: "Insert a variable" })).not.toBeInTheDocument();
});
