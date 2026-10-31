import "../../app/globals.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";

import { FlexiblePageEditor } from "@/components/flexible-page-editor";
import i18n from "@/i18n/i18next";
import { api, type Page } from "@/lib/api";

const document: Page = {
  id: "fixture",
  name: "Morning",
  type: "flexible",
  revision: "fixture-one",
  created_at: "2026-01-01T00:00:00Z",
  duration_seconds: 30,
  blocks: [{ id: "heading", kind: "text", text: "Hello", future: true }],
};
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function Fixture() {
  const [saved, setSaved] = useState("");
  // This browser fixture has no backend and never addresses a live display.
  api.updatePage = async (_id, fields) => {
    setSaved(JSON.stringify(fields));
    return { page: { ...document, ...fields, revision: "fixture-two" }, incompatible_references: [] };
  };
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <main>
          <h1>Flexible editor acceptance</h1>
          <FlexiblePageEditor initialPage={document} boards={[]} onSave={() => {}} onClose={() => {}} />
          <output aria-label="Saved document" style={{ overflowWrap: "anywhere" }}>
            {saved}
          </output>
        </main>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

createRoot(window.document.getElementById("root")!).render(<Fixture />);
