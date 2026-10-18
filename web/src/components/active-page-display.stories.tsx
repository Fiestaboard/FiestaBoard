import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import { expect, userEvent, waitFor, within } from "storybook/test";

import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n/i18next";
import type { Collection, CollectionsResponse, Page, PagesResponse, SilenceStatus } from "@/lib/api";

import { ActivePageDisplay } from "./active-page-display";

const meta = {
  title: "Layout/ActivePageDisplay",
  component: ActivePageDisplay,
  parameters: {
    layout: "padded",
    nextjs: {
      appDirectory: true,
      navigation: {
        pathname: "/",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ActivePageDisplay>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Weather Dashboard",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Transit Times",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-02T00:00:00Z",
  },
];

const mockPreviewMessage = "{63}WEATHER{/63}\n{64}72°F SUNNY{/64}\n \nHIGH: 75°F\nLOW: 65°F\nHUMIDITY: 60%";

const mockCollections: Collection[] = [
  {
    id: "collection:abc-123",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    random: null,
    created_at: "2024-02-01T00:00:00Z",
  },
];

const createQueryClient = (
  activePageId: string | null,
  scheduleEnabled: boolean = false,
  silenceActive: boolean = false,
  collections?: Collection[],
  silence: Partial<SilenceStatus> = {},
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });

  client.setQueryData(["pages"], { pages: mockPages } as PagesResponse);
  client.setQueryData(["activePage"], { page_id: activePageId });
  client.setQueryData(["schedules", "default"], {
    enabled: scheduleEnabled,
    schedules: [],
  });

  if (scheduleEnabled && activePageId) {
    client.setQueryData(["schedules", "active"], {
      page_id: activePageId,
      schedule_id: "sched-1",
    });
  }

  if (activePageId) {
    client.setQueryData(["pagePreview", activePageId], {
      page_id: activePageId,
      message: mockPreviewMessage,
      lines: mockPreviewMessage.split("\n"),
      display_type: "template",
      raw: {},
    });
  }

  // Seed preview data for all pages so collection rotation has something to show
  for (const page of mockPages) {
    if (!client.getQueryData(["pagePreview", page.id])) {
      client.setQueryData(["pagePreview", page.id], {
        page_id: page.id,
        message: mockPreviewMessage,
        lines: mockPreviewMessage.split("\n"),
        display_type: "template",
        raw: {},
      });
    }
  }

  client.setQueryData(["silenceStatus"], {
    enabled: true,
    active: silenceActive,
    start_time_utc: "2024-01-01T00:00:00Z",
    end_time_utc: "2024-01-01T08:00:00Z",
    current_time_utc: "2024-01-01T04:00:00Z",
    next_change_utc: "2024-01-01T08:00:00Z",
    ...silence,
  } as SilenceStatus);

  client.setQueryData(["boardSettings"], {
    board_type: "black",
    boards: [],
    devices: ["flagship"],
  });

  client.setQueryData(["collections"], {
    collections: collections ?? [],
    total: collections?.length ?? 0,
  } as CollectionsResponse);

  return client;
};

export const ManualMode: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", false)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const ScheduleMode: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", true)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const SilenceModeActive: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", false, true)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

// A paused board: the badge plus the Resume toggle beside Change Page (issue #2051).
export const BoardPaused: Story = {
  decorators: [
    (Story) => {
      const client = createQueryClient("page-1", true);
      client.setQueryData(["boardSettings"], {
        board_type: "black",
        boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black", paused: true }],
        devices: ["flagship"],
      });
      return (
        <QueryClientProvider client={client}>
          <div className="max-w-4xl">
            <Story />
          </div>
        </QueryClientProvider>
      );
    },
  ],
};

export const ScheduleGap: Story = {
  decorators: [
    (Story) => {
      const client = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            staleTime: Infinity,
          },
        },
      });

      client.setQueryData(["pages"], { pages: mockPages } as PagesResponse);
      client.setQueryData(["schedules", "default"], {
        enabled: true,
        schedules: [],
        default_page_id: null,
      });
      client.setQueryData(["schedules", "active"], null);
      client.setQueryData(["activePage"], { page_id: null });
      client.setQueryData(["boardSettings"], {
        board_type: "black",
        boards: [],
        devices: ["flagship"],
      });

      return (
        <QueryClientProvider client={client}>
          <div className="max-w-4xl">
            <Story />
          </div>
        </QueryClientProvider>
      );
    },
  ],
};

export const Loading: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const InDashboard = () => (
  <QueryClientProvider client={createQueryClient("page-1", true)}>
    <div className="min-h-screen bg-background p-6">
      <div className="container mx-auto max-w-6xl">
        <h1 className="text-3xl font-bold mb-6">Dashboard</h1>
        <ActivePageDisplay />
      </div>
    </div>
  </QueryClientProvider>
);

export const CollectionActive: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("collection:abc-123", false, false, mockCollections)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const CollectionActiveScheduled: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("collection:abc-123", true, false, mockCollections)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

// ---------------------------------------------------------------------------
// Silence (#1943, #1944): hold by default, one explicit "Show now"
// ---------------------------------------------------------------------------

/** When silence ends, as the stories quote it: seven hours after the story loads. */
const ENDS_AT = new Date(Date.now() + 7 * 3600 * 1000).toISOString();
const SILENCED: Partial<SilenceStatus> = {
  active: true,
  mode: "freeze",
  ends_at_utc: ENDS_AT,
  seconds_until_next_change: 7 * 3600,
  holds_blocked_sends: false,
  held: null,
};
const HELD: Partial<SilenceStatus> = {
  ...SILENCED,
  holds_blocked_sends: true,
  held: { kind: "text", preview: "GOOD MORNING EVERYONE HAVE A…", queued_at: new Date().toISOString() },
};
const endsAtLabel = () => new Date(ENDS_AT).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const PHONE = { viewport: { value: "phone375", isRotated: false } };

function silenced(client: QueryClient, opts: { schedule?: boolean } = {}) {
  if (opts.schedule) {
    client.setQueryData(["schedules", "active"], {
      page_id: "page-1",
      source: "schedule",
      schedule_enabled: true,
      temporary_override: null,
    });
  }
  return (Story: () => React.ReactElement) => (
    <QueryClientProvider client={client}>
      <div className="max-w-4xl">
        <Story />
      </div>
    </QueryClientProvider>
  );
}

/** Manual mode, "Weather Dashboard" active, nothing held: the alert and Show now. */
export const SilencedManual: Story = {
  decorators: [silenced(createQueryClient("page-1", false, true, undefined, SILENCED))],
};

export const SilencedManualPhone: Story = {
  ...SilencedManual,
  globals: PHONE,
};

/** A message is held: it shows first, and can be discarded. */
export const SilencedManualHeld: Story = {
  decorators: [silenced(createQueryClient("page-1", false, true, undefined, HELD))],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => expect(canvas.getByTestId("silence-show-now")).toBeVisible());
    await waitFor(() => expect(canvas.getByTestId("silence-discard-held")).toBeVisible());
    await expect(canvas.getByTestId("silence-held")).toHaveTextContent("GOOD MORNING EVERYONE HAVE A…");
  },
};

export const SilencedManualHeldPhone: Story = {
  ...SilencedManualHeld,
  globals: PHONE,
};

/** Schedule mode: the schedule resumes when silence ends; no Show now. */
export const SilencedSchedule: Story = {
  decorators: [silenced(createQueryClient("page-1", true, true, undefined, SILENCED), { schedule: true })],
};

/**
 * Silence "page" mode: the header names the silence page on the board
 * (#1637); the alert still names the page that shows when silence ends.
 */
export const SilencedPageMode: Story = {
  decorators: [
    silenced(createQueryClient("page-1", false, true, undefined, { ...SILENCED, mode: "page", page_id: "page-2" })),
  ],
};

/** A collection is active: the alert names it, with no Show now. */
export const SilencedCollection: Story = {
  decorators: [silenced(createQueryClient("collection:abc-123", false, true, mockCollections, SILENCED))],
};

/** The Change Page sheet during silence: the note under its description. */
export const SilencedSheetOpen: Story = {
  decorators: [silenced(createQueryClient("page-1", false, true, undefined, SILENCED))],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const [changePage] = await canvas.findAllByRole("button", { name: /change page/i });
    await userEvent.click(changePage);
    await expect(await within(document.body).findByTestId("select-page-silence")).toBeVisible();
  },
};

export const SilencedSheetOpenPhone: Story = {
  ...SilencedSheetOpen,
  globals: PHONE,
};

/** Shows a toast exactly as the Home page raises it, over the silenced Home. */
function withToast(raise: () => void) {
  return (Story: () => React.ReactElement) => {
    function Raise() {
      useEffect(() => {
        const id = setTimeout(raise, 50);
        return () => clearTimeout(id);
      }, []);
      return null;
    }
    return (
      <>
        <Story />
        <Toaster />
        <Raise />
      </>
    );
  };
}

/** A page picked during silence: saved, with Show now in the toast. */
export const HeldPageToast: Story = {
  decorators: [
    withToast(() =>
      toast.info(i18n.t("activeDisplay.toastSwitchHeld", { pageName: "Transit Times", time: endsAtLabel() }), {
        duration: Infinity,
        action: { label: i18n.t("activeDisplay.showNow"), onClick: () => {} },
      }),
    ),
    silenced(createQueryClient("page-2", false, true, undefined, SILENCED)),
  ],
};

/** Show now landed. */
export const ShownNowToast: Story = {
  decorators: [
    withToast(() =>
      toast.success(i18n.t("activeDisplay.toastShownNow", { pageName: "Transit Times" }), { duration: Infinity }),
    ),
    silenced(createQueryClient("page-2", false, true, undefined, SILENCED)),
  ],
};

/** A pick on a paused board. */
export const PausedToast: Story = {
  decorators: [
    withToast(() =>
      toast.info(i18n.t("activeDisplay.toastSwitchPaused", { pageName: "Transit Times" }), { duration: Infinity }),
    ),
    silenced(createQueryClient("page-2", false, true, undefined, SILENCED)),
  ],
};

/** Regression: not silenced — no alert, no sheet note, dialogs unchanged. */
export const SilenceInactiveDefault: Story = {
  decorators: [silenced(createQueryClient("page-1", false, false, undefined, { active: false }))],
};
