import "../../app/globals.css";

import { MainContent } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, RouterProvider } from "react-router";

import { FlexiblePageEditor } from "@/components/flexible-page-editor";
import { PageEditorShell } from "@/components/page-editor-shell";
import i18n from "@/i18n/i18next";
import { api, type BoardInstance, type Page } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";

import { PagesSection } from "../../app/routes/pages";

const document: Page = {
  id: "fixture",
  name: "Morning",
  type: "flexible",
  revision: "fixture-one",
  created_at: "2026-01-01T00:00:00Z",
  duration_seconds: 30,
  blocks: [{ id: "heading", kind: "text", text: "Hello", future: true }],
};
const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });

const query = new URLSearchParams(window.location.search);
if (query.has("shell")) {
  document.blocks = Array.from({ length: 6 }, (_, i) => ({ id: `text_${i}`, kind: "text", text: `Line ${i + 1}` }));
}
if (query.has("canvas"))
  document.blocks = [
    { id: "first", kind: "text", text: "Morning" },
    { id: "second", kind: "text", text: "Weather" },
    { id: "art", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } },
  ];
const width = Number(query.get("width") || 52);
const height = Number(query.get("height") || 16);
const base = resolveBoardModel({ device_model: "divoom_pixoo64" })!;
const boards = query.has("physical")
  ? ([
      {
        id: "physical",
        name: "Physical fixture",
        device_type: "panel",
        grid_rows: 3,
        grid_cols: 13,
        device_model_spec: { ...base, geometry: { kind: "pixels", width, height: height + 1 } },
        physical_surface: { version: 1, width, height, modes: ["ordinary"] },
      },
    ] as BoardInstance[])
  : [];
api.previewFlexiblePage = async () => ({
  page_id: "fixture",
  available: true,
  display_type: "page:flexible",
  message: "HELLO",
  lines: ["HELLO"],
  raw: { text_representation: "cell_projection", surface: { kind: "pixels", width, height } },
  layers: [
    { x: 0, y: 0, width, height, physical_frame_version: 1, rgba: btoa("\xff\x00\x00\xff".repeat(width * height)) },
  ],
});

client.setQueryData(["page", "fixture"], document);
client.setQueryData(["pages"], { pages: [document] });
client.setQueryData(["boardSettings"], { boards });
const shellRouter = createMemoryRouter(
  [
    {
      path: "/pages/:id",
      element: (
        <MainContent collapsed={false} transitioning={false} aiPanelOpen={false}>
          <PagesSection>
            <PageEditorShell pageId="fixture" onClose={() => {}} onSave={() => {}} />
          </PagesSection>
        </MainContent>
      ),
    },
  ],
  { initialEntries: ["/pages/fixture"] },
);

function Fixture() {
  const [saved, setSaved] = useState("");
  // This browser fixture has no backend and never addresses a live display.
  useEffect(() => {
    const previous = api.updatePage;
    api.updatePage = async (_id, fields) => {
      if (query.has("saveError")) throw new Error("Could not save. Try again.");
      setSaved(JSON.stringify(fields));
      return { page: { ...document, ...fields, revision: "fixture-two" }, incompatible_references: [] };
    };
    return () => {
      api.updatePage = previous;
    };
  }, []);
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        {query.has("shell") ? (
          <RouterProvider router={shellRouter} />
        ) : (
          <main>
            <h1>Flexible editor acceptance</h1>
            <FlexiblePageEditor initialPage={document} boards={boards} onSave={() => {}} onClose={() => {}} />
            <output aria-label="Saved document" style={{ overflowWrap: "anywhere" }}>
              {saved}
            </output>
          </main>
        )}
      </QueryClientProvider>
    </I18nextProvider>
  );
}

createRoot(window.document.getElementById("root")!).render(<Fixture />);
