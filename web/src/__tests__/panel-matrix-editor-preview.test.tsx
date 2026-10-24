import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { PanelMatrixEditorPreview } from "@/components/panel/panel-matrix-editor-preview";

import { FIESTAPANEL_LED_MATRIX } from "./mocks/fiestapanel-models";
import { server } from "./mocks/server";

const geometry = {
  rows: 13,
  cols: 32,
  geometry_key: "screen-large",
  device_model_spec: {
    ...FIESTAPANEL_LED_MATRIX,
    geometry: { kind: "pixels" as const, width: 192, height: 108 },
  },
};
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}

describe("draft LED preview", () => {
  it.each([null, "fill_tv"] as const)("preserves a matching frame and canvas for sizing %s", async (sizing) => {
    server.use(
      http.get("/api/panel/p1/frame", () =>
        HttpResponse.json({
          rows: 13,
          cols: 32,
          geometry_key: "screen-large",
          message: "MATCH",
          characters: null,
          layers: [{ x: 0, y: 0, width: 1, height: 1, rgba: "/wAA/w==" }],
        }),
      ),
    );
    render(
      <PanelMatrixEditorPreview
        panelId="p1"
        diagonal={55}
        aspectW={16}
        aspectH={9}
        sizing={sizing}
        spacing={6}
        calibration={1}
        geometry={geometry}
      />,
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("data-layers", "1"));
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("MATCH");
    expect(screen.queryByText(/Content preview will update after saving/)).not.toBeInTheDocument();
  });

  it.each(["old-grid", undefined])(
    "uses the resolved surface and drops incompatible or unidentified frame %s",
    async (key) => {
      let fetched = false;
      server.use(
        http.get("/api/panel/p1/frame", () => {
          fetched = true;
          return HttpResponse.json({
            rows: 13,
            cols: 32,
            geometry_key: key,
            message: "STALE",
            characters: null,
            cells: [[{ type: "char", value: "X" }]],
            layers: [{ x: 0, y: 0, width: 1, height: 1, rgba: "/wAA/w==" }],
          });
        }),
      );
      const { container } = render(
        <PanelMatrixEditorPreview
          panelId="p1"
          diagonal={85}
          aspectW={16}
          aspectH={9}
          sizing="fill_tv"
          spacing={6}
          calibration={1}
          geometry={geometry}
        />,
        { wrapper: Wrapper },
      );
      await waitFor(() => expect(fetched).toBe(true));
      const matrix = container.querySelector('[data-slot="led-matrix-display"]');
      expect(matrix).toHaveAttribute("data-matrix-width", "192");
      expect(matrix).toHaveAttribute("data-matrix-height", "108");
      expect(matrix).not.toHaveAttribute("data-layers", "1");
      expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("STALE");
      expect(screen.getByText(/Content preview will update after saving/)).toBeInTheDocument();
    },
  );
});
