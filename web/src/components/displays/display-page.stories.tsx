import { PageCard } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";

import firstPartyOutputs from "@/__tests__/mocks/first-party-outputs.json";
import { OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import type { BoardInstance, BoardSettings, SilenceStatus } from "@/lib/api";

import DisplayPage from "../../../app/routes/displays.$boardId";

/**
 * One display's own page (/displays/:boardId) with the out-of-sync banner
 * (issue #1945) directly under its "Now showing" preview, then its settings.
 */

const ROWS = 6;
const COLS = 22;

function rows(...lines: string[]): number[][] {
  return Array.from({ length: ROWS }, (_, r) =>
    Array.from({ length: COLS }, (_, c) => {
      const ch = (lines[r] ?? "")[c];
      const code = ch ? ch.charCodeAt(0) - 64 : 0;
      return code >= 1 && code <= 26 ? code : 0;
    }),
  );
}

function message(grid: number[][]): string {
  return grid.map((row) => row.map((c) => (c === 0 ? " " : String.fromCharCode(c + 64))).join("")).join("\n");
}

const OWN_PAGE = rows("WEATHER", "SUNNY");
const OTHER_APP = rows("HAPPY BIRTHDAY", "FROM THE APP");

const LIVING_ROOM: BoardInstance = {
  id: "living",
  name: "Living Room",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "192.168.1.100",
  local_api_key: "***",
  cloud_key: "",
  output: "vestaboard",
  output_config: { api_mode: "local", host: "192.168.1.100", port: 7000, local_api_key: "***" },
};

const SILENCE_OFF: SilenceStatus = {
  enabled: false,
  active: false,
  start_time_utc: "22:00+00:00",
  end_time_utc: "07:00+00:00",
  current_time_utc: "12:00+00:00",
  next_change_utc: "22:00+00:00",
};

function onDisplayPage(board: BoardInstance, boardState: Record<string, unknown>) {
  return function Decorator(Story: () => ReactNode) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    const settings: BoardSettings = { board_type: "black", boards: [board], devices: [board.device_type] };
    client.setQueryData(["boardSettings"], settings);
    client.setQueryData(OUTPUTS_QUERY_KEY, firstPartyOutputs);
    client.setQueryData(["board-current-message", board.id], {
      rows: ROWS,
      cols: COLS,
      cached_at: new Date().toISOString(),
      api_mode: "local",
      board_id: board.id,
      ...boardState,
    });
    client.setQueryData(["silenceStatus", board.id], SILENCE_OFF);
    client.setQueryData(["pages"], { pages: [] });
    return (
      <QueryClientProvider client={client}>
        <div className="max-w-3xl">
          <PageCard>
            <Routes>
              <Route path="/displays/:boardId" element={<Story />} />
              <Route path="*" element={<Navigate to={`/displays/${board.id}`} replace />} />
            </Routes>
          </PageCard>
        </div>
      </QueryClientProvider>
    );
  };
}

const meta = {
  title: "Displays/DisplayPage",
  component: DisplayPage,
  parameters: { layout: "padded" },
} satisfies Meta<typeof DisplayPage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OutOfSync: Story = {
  decorators: [
    onDisplayPage(LIVING_ROOM, {
      characters: OTHER_APP,
      message: message(OTHER_APP),
      expected_characters: OWN_PAGE,
    }),
  ],
};

export const PausedOutOfSync: Story = {
  decorators: [
    onDisplayPage(
      { ...LIVING_ROOM, paused: true },
      { characters: OTHER_APP, message: message(OTHER_APP), expected_characters: OWN_PAGE },
    ),
  ],
};

export const Kept: Story = {
  decorators: [
    onDisplayPage(LIVING_ROOM, {
      characters: OWN_PAGE,
      message: message(OWN_PAGE),
      expected_characters: OWN_PAGE,
      external_characters: OTHER_APP,
      external_detected_at: new Date().toISOString(),
    }),
  ],
};
