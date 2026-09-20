import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearRememberedToolDetails } from "@/hooks/use-target-caches";

import { AiApprovalCard } from "@/components/ai-approval-card";
import type { ToolCall } from "@/lib/ai-chat-types";

// The card names its target from the app's query caches (#2024), so it
// renders inside a client. `seed` is what the drawer has already fetched
// when the approval card appears; an empty seed is the cold-cache case.
function render(ui: React.ReactElement, seed: Array<[readonly unknown[], unknown]> = []) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) queryClient.setQueryData(key, data);
  return rtlRender(ui, {
    wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
  });
}

const SCHEDULE_ID = "289204ec-4306-41f0-b37b-4341cfe68783";

const DELETE_SCHEDULE: ToolCall = {
  id: "c3",
  name: "delete_schedule",
  args: { schedule_id: SCHEDULE_ID },
  title: "Delete schedule",
  read_only: false,
  destructive: true,
  requires_approval: true,
  source: "mcp",
  system_gated: false,
  auto_approved: false,
};

const SEEDED_CACHES: Array<[readonly unknown[], unknown]> = [
  [["pages"], { pages: [{ id: "p-night", name: "Goodnight" }] }],
  [
    ["schedules"],
    {
      schedules: [
        {
          id: SCHEDULE_ID,
          page_id: "p-night",
          start_time: "21:00",
          end_time: "23:00",
          day_pattern: "all",
          enabled: true,
        },
      ],
    },
  ],
];

const DELETE_PAGE: ToolCall = {
  id: "c1",
  name: "delete_page",
  args: { page_id: "p1" },
  title: "Delete page",
  read_only: false,
  destructive: true,
  requires_approval: true,
  source: "mcp",
  system_gated: false,
  auto_approved: false,
};

const RESTART_SYSTEM: ToolCall = {
  ...DELETE_PAGE,
  id: "c2",
  name: "restart_system",
  args: {},
  title: "Restart system",
  system_gated: true,
};

const APPROVE_ALL = /approve and don.t ask again in this chat/i;

describe("AiApprovalCard", () => {
  beforeEach(() => {
    // Resolved names are remembered per tool-call id for the session, so a
    // test that wants the cold-cache reading must not inherit one.
    clearRememberedToolDetails();
  });

  it("names the call and puts focus on Deny, the safe answer", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getByRole("group", { name: /needs your approval/i })).toBeInTheDocument();
    expect(screen.getByText(/Delete page/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("Approve and Deny call their handlers", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onDeny = vi.fn();
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={onApprove} onDeny={onDeny} />);

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Deny" }));

    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onDeny).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while the decision is in flight", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /working/i })).toBeDisabled();
  });

  it("falls back to a generic description for a tool it does not know", () => {
    render(
      <AiApprovalCard
        call={{ ...DELETE_PAGE, name: "obliterate_everything", title: "Obliterate everything" }}
        onApprove={vi.fn()}
        onDeny={vi.fn()}
      />,
    );
    expect(screen.getByText("Obliterate everything")).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone by another tool/i)).toBeInTheDocument();
  });

  // -- naming the target (#2024) --

  it("names the schedule it is about to delete, not its uuid", () => {
    render(<AiApprovalCard call={DELETE_SCHEDULE} onApprove={vi.fn()} onDeny={vi.fn()} />, SEEDED_CACHES);
    // The name appears twice on purpose — beside the title and inside the
    // sentence — and the uuid appears nowhere.
    expect(screen.getAllByText(/Goodnight · 21:00–23:00 · every day/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(new RegExp(SCHEDULE_ID))).toHaveLength(0);
  });

  it("says the same name in the sentence that explains what will be lost", () => {
    render(<AiApprovalCard call={DELETE_SCHEDULE} onApprove={vi.fn()} onDeny={vi.fn()} />, SEEDED_CACHES);
    expect(screen.getByText(/Permanently removes schedule "Goodnight · 21:00–23:00 · every day"/)).toBeInTheDocument();
  });

  it("falls back to the id when the caches cannot name the target", () => {
    // A call this session has never resolved: its own id, as a real second
    // call would have.
    const unseen = { ...DELETE_SCHEDULE, id: "c-unseen" };
    render(<AiApprovalCard call={unseen} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getAllByText(new RegExp(SCHEDULE_ID)).length).toBeGreaterThan(0);
  });

  // -- "Approve and don't ask again in this chat" (#2021) --

  it("offers 'don't ask again' for an ordinary destructive call and it approves through its own handler", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onApproveAll = vi.fn();
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={onApprove} onDeny={vi.fn()} onApproveAll={onApproveAll} />);

    await user.click(screen.getByRole("button", { name: APPROVE_ALL }));

    expect(onApproveAll).toHaveBeenCalledTimes(1);
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("does not offer 'don't ask again' for a system-gated call", () => {
    render(<AiApprovalCard call={RESTART_SYSTEM} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} />);
    expect(screen.queryByRole("button", { name: APPROVE_ALL })).not.toBeInTheDocument();
    // Approve / Deny are untouched for the system tier.
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("keeps Deny as the mount focus when 'don't ask again' is offered", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("disables 'don't ask again' while the decision is in flight", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: APPROVE_ALL })).toBeDisabled();
  });

  it("Tab order from the mount-focused Deny is Approve, then 'don't ask again' — never the other way", async () => {
    const user = userEvent.setup();
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Approve" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: APPROVE_ALL })).toHaveFocus();
    // Shift+Tab from Deny leaves the card: nothing approving sits before it.
    screen.getByRole("button", { name: "Deny" }).focus();
    await user.tab({ shift: true });
    expect(screen.queryByRole("button", { name: APPROVE_ALL })).not.toHaveFocus();
    expect(screen.getByRole("button", { name: "Approve" })).not.toHaveFocus();
  });
});
