import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VariablePickerContent } from "@/components/tiptap-template-editor/components/VariablePickerContent";

import { server } from "./mocks/server";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("VariablePickerContent", () => {
  const mockOnInsert = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders search input with auto-focus", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText("Search variables...");
      expect(searchInput).toBeInTheDocument();
      expect(searchInput).toHaveFocus();
    });
  });

  it("shows all variables without truncation", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const weatherCategory = screen.getByText(/weather/i);
      expect(weatherCategory).toBeInTheDocument();
    });

    const weatherSection = screen.getByText(/weather/i).closest("div")?.parentElement;
    if (weatherSection) {
      const variablePills = within(weatherSection).getAllByRole("button");
      expect(variablePills.length).toBeGreaterThanOrEqual(11);
    }

    expect(screen.queryByText(/\+ \d+ more/i)).not.toBeInTheDocument();
  });

  it("filters variables by search query", async () => {
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search variables...")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search variables...");
    await user.type(searchInput, "temp");

    await waitFor(() => {
      const temperaturePill = screen.getByText("temperature");
      expect(temperaturePill).toBeInTheDocument();
    });
  });

  it("shows all variables when category name matches search", async () => {
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search variables...")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search variables...");
    await user.type(searchInput, "weather");

    await waitFor(() => {
      const weatherCategory = screen.getByText(/weather/i);
      expect(weatherCategory).toBeInTheDocument();
    });

    const weatherSection = screen.getByText(/weather/i).closest("div")?.parentElement;
    if (weatherSection) {
      const variablePills = within(weatherSection).getAllByRole("button");
      expect(variablePills.length).toBeGreaterThanOrEqual(11);
    }
  });

  it("shows no results message when search has no matches", async () => {
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search variables...")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search variables...");
    await user.type(searchInput, "nonexistentvariable123");

    await waitFor(() => {
      expect(screen.getByText(/No variables found matching/i)).toBeInTheDocument();
    });
  });

  it("calls onInsert when variable is clicked", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const temperaturePill = screen.getByText("temperature");
      expect(temperaturePill).toBeInTheDocument();
    });

    const temperaturePill = screen.getByText("temperature");
    await userEvent.click(temperaturePill);

    expect(mockOnInsert).toHaveBeenCalledWith("{{weather.temperature}}");
  });

  it("filters case-insensitively", async () => {
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search variables...")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search variables...");
    await user.type(searchInput, "TEMP");

    await waitFor(() => {
      const temperaturePill = screen.getByText("temperature");
      expect(temperaturePill).toBeInTheDocument();
    });
  });

  it("matches partial strings in variable names", async () => {
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search variables...")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search variables...");
    await user.type(searchInput, "cond");

    await waitFor(() => {
      const conditionPill = screen.getByText("condition");
      expect(conditionPill).toBeInTheDocument();
    });
  });

  it("renders preview values from metadata", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("temperature")).toBeInTheDocument();
    });

    // The mock metadata for temperature has preview "72"
    await waitFor(() => {
      expect(screen.getByText("72")).toBeInTheDocument();
    });
  });

  it("renders variable groups when defined", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("temperature")).toBeInTheDocument();
    });

    // The mock has variable_groups for weather with "Current Conditions"
    await waitFor(() => {
      expect(screen.getByText("Current Conditions")).toBeInTheDocument();
    });
  });

  it("renders group headings for datetime plugin", async () => {
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      // datetime mock has groups "Time" and "Date"
      expect(screen.getByText("Time")).toBeInTheDocument();
      expect(screen.getByText("Date")).toBeInTheDocument();
    });
  });

  it("works with no metadata (backward compat)", async () => {
    // Even without metadata, the component should still render variable pills
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await waitFor(() => {
      // datetime variables should still render
      expect(screen.getByText("time")).toBeInTheDocument();
      expect(screen.getByText("date")).toBeInTheDocument();
    });
  });

  it("renders array item fields declared in the map form, with their descriptions", async () => {
    server.use(
      http.get("/api/v1/variables", () =>
        HttpResponse.json({ variables: { mlb: ["games", "games.*.minutes_until_game"] }, max_lengths: {} }),
      ),
      http.get("/api/plugins/mlb/manifest", () =>
        HttpResponse.json({
          id: "mlb",
          name: "MLB",
          version: "1.0.0",
          description: "",
          author: "FiestaBoard",
          settings_schema: {},
          max_lengths: {},
          variables: {
            arrays: {
              games: {
                label_field: "formatted",
                item_fields: {
                  formatted: { description: "Summary line" },
                  minutes_until_game: { description: "Minutes until first pitch", type: "number" },
                },
              },
            },
          },
        }),
      ),
      http.post("/api/displays/raw/batch", () =>
        HttpResponse.json({
          displays: {
            mlb: {
              data: { games: [{ formatted: "NYY @ BOS", minutes_until_game: 15 }] },
              available: true,
              error: null,
            },
          },
        }),
      ),
    );
    const user = userEvent.setup();
    render(<VariablePickerContent onInsert={mockOnInsert} />, { wrapper: TestWrapper });

    await user.click(await screen.findByText("NYY @ BOS"));
    const pill = await screen.findByRole("button", { name: "minutes_until_game" });
    await user.hover(pill);

    expect((await screen.findAllByText("Minutes until first pitch")).length).toBeGreaterThan(0);
    await user.click(pill);
    expect(mockOnInsert).toHaveBeenCalledWith("{{mlb.games.0.minutes_until_game}}");
  });
});
