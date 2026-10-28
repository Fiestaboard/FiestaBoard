import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, userEvent, within } from "storybook/test";

import { CurrentBoardProvider } from "@/components/current-board-context";

import { SilenceSchedule } from "./silence-schedule";

const KITCHEN = { id: "board-1", name: "Kitchen", device_type: "flagship", board_color: "black" };
const DESK = { id: "board-2", name: "Desk", device_type: "note", board_color: "white" };

function client(silence: Record<string, unknown>, boards = [KITCHEN]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  queryClient.setQueryData(["all-settings"], {
    general: { timezone: "America/Los_Angeles" },
    silence_schedule: {
      config: {
        enabled: true,
        start_time: "06:00+00:00",
        end_time: "15:00+00:00",
        mode: "indicator",
        page_id: null,
        indicator_text: "SNOOZING",
        indicator_position: "center",
        show_queued_on_exit: false,
        ...silence,
      },
    },
  });
  queryClient.setQueryData(["boardSettings"], { board_type: "black", boards, devices: ["flagship"] });
  queryClient.setQueryData(["pages"], { pages: [], total: 0 });
  return queryClient;
}

/**
 * Settings → Scheduling → Silence Schedule with the "Show held messages when
 * silence ends" switch (#1944): the last block, for every mode.
 */
const meta = {
  title: "Silence/SilenceScheduleSettings",
  component: SilenceSchedule,
  parameters: { layout: "padded" },
} satisfies Meta<typeof SilenceSchedule>;

export default meta;
type Story = StoryObj<typeof meta>;

function withClient(queryClient: QueryClient, selectBoard?: string) {
  return (Story: () => React.ReactElement) => {
    try {
      if (selectBoard) localStorage.setItem("fiestaboard_current_board", selectBoard);
      else localStorage.removeItem("fiestaboard_current_board");
    } catch {
      // Storage unavailable — the provider falls back to the primary board.
    }
    return (
      <QueryClientProvider client={queryClient}>
        <CurrentBoardProvider>
          <div className="max-w-2xl">
            <Story />
          </div>
        </CurrentBoardProvider>
      </QueryClientProvider>
    );
  };
}

/** Indicator mode, switch off, hint under it. */
export const HeldOff: Story = {
  decorators: [withClient(client({}))],
};

export const HeldOn: Story = {
  decorators: [withClient(client({ show_queued_on_exit: true }))],
  play: async ({ canvasElement }) => {
    const toggle = await within(canvasElement).findByRole("switch", { name: "Show held messages when silence ends" });
    await expect(toggle).toHaveAttribute("aria-checked", "true");
  },
};

export const HeldOnPhone: Story = {
  ...HeldOn,
  globals: { viewport: { value: "phone375", isRotated: false } },
};

/** A secondary board selected: its own by_board entry seeds the switch. */
export const HeldPerBoardSeeded: Story = {
  decorators: [
    withClient(
      client({ show_queued_on_exit: false, by_board: { "board-2": { show_queued_on_exit: true } } }, [KITCHEN, DESK]),
      "board-2",
    ),
  ],
};

/** A second after the flip the form autosaves; the save is kept in flight here. */
export const Saving: Story = {
  decorators: [withClient(client({}))],
  beforeEach: () => {
    const original = window.fetch;
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/settings/silence-schedule")) return new Promise<Response>(() => {});
      return original(input, init);
    }) as typeof window.fetch;
    return () => {
      window.fetch = original;
    };
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("switch", { name: "Show held messages when silence ends" }));
    await expect(await canvas.findByText(/saving/i, undefined, { timeout: 3000 })).toBeVisible();
  },
};
