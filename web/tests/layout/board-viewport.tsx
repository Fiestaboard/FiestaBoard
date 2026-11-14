import "../../app/globals.css";

import { Stack, Text } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";

/**
 * Slice 2.4 (WEB-07) fixture: the app's board wrapper on real layout, so the
 * scroll, snap, keys and the Fit overview can be measured in Chromium without a
 * hub. `?theme=dark` renders the dark theme; `?only=<id>` renders one board.
 */
const params = new URLSearchParams(window.location.search);
if (params.get("theme") === "dark") document.documentElement.classList.add("dark");
const only = params.get("only");

const FLAGSHIP =
  "GOOD MORNING MAYA     \n72° SUNNY  HI 78  LO 61\nN JUDAH 4 MIN  7 MIN  \n\nCOFFEE AT 9           \nHAVE A GREAT DAY      ";
const NOTE_ARRAY =
  "  OPEN MIC     HOSTED BY     6 SPOTS LEFT \n TONIGHT 7 PM    DJ MAYA      SIGN UP AT  \n                             THE COUNTER  ";

const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });

function Slot({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  if (only && only !== id) return null;
  return (
    <section data-testid={id} className="min-w-0">
      <Stack gap="2">
        <Text size="xs" tone="muted">
          {label}
        </Text>
        {children}
      </Stack>
    </section>
  );
}

function Fixture() {
  return (
    <QueryClientProvider client={client}>
      <main className="mx-auto flex max-w-[1100px] flex-col gap-8 p-4">
        <Slot id="flagship" label="Flagship · 22×6">
          <ScaledBoardDisplay message={FLAGSHIP} deviceType="flagship" size="md" isStatic />
        </Slot>
        <Slot id="note-array" label="Note Array 3×1 · 45×3">
          <ScaledBoardDisplay message={NOTE_ARRAY} deviceType="note_array" notesWide={3} size="md" isStatic />
        </Slot>
        <Slot id="note-array-2x2" label="Note Array 2×2 · 30×6">
          <ScaledBoardDisplay message="" deviceType="note_array" notesWide={2} notesTall={2} size="md" isStatic />
        </Slot>
        <Slot id="thumbnail" label="Thumbnail (page card)">
          {/* Inside a <button>, as the page card draws it. */}
          <button type="button" aria-label="Open mic" className="block w-[300px] overflow-hidden text-left">
            <ScaledBoardDisplay
              thumbnail
              message={NOTE_ARRAY}
              deviceType="note_array"
              notesWide={3}
              size="sm"
              isStatic
            />
          </button>
        </Slot>
      </main>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
