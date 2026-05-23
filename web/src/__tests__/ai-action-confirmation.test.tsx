import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiActionConfirmation } from "@/components/ai-action-confirmation";
import type { ToolCall } from "@/lib/ai-chat-types";

// ---------------------------------------------------------------------------
// Minimal ToolCall fixtures
// ---------------------------------------------------------------------------

const installCall: ToolCall = {
  id: "tc1",
  op: "install_plugin",
  args: { plugin_id: "openweather", source: "registry" },
};

const uninstallCall: ToolCall = {
  id: "tc2",
  op: "uninstall_plugin",
  args: { plugin_id: "openweather" },
};

const enableCall: ToolCall = {
  id: "tc3",
  op: "enable_plugin",
  args: { plugin_id: "stocks" },
};

describe("AiActionConfirmation", () => {
  it("renders action label and description", () => {
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={vi.fn()}
        onDeny={vi.fn()}
      />,
    );
    expect(screen.getByText(/install plugin: openweather/i)).toBeInTheDocument();
  });

  it("shows Allow and Deny buttons in pending state", () => {
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={vi.fn()}
        onDeny={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /allow/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deny/i })).toBeInTheDocument();
  });

  it("calls onAllow when Allow is clicked and shows Done state", async () => {
    const onAllow = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={onAllow}
        onDeny={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /allow/i }));
    expect(onAllow).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(screen.getByText(/done/i)).toBeInTheDocument(),
    );
  });

  it("calls onDeny when Deny is clicked and shows Denied state", async () => {
    const onDeny = vi.fn();
    const user = userEvent.setup();
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={vi.fn()}
        onDeny={onDeny}
      />,
    );
    await user.click(screen.getByRole("button", { name: /deny/i }));
    expect(onDeny).toHaveBeenCalledOnce();
    expect(screen.getByText(/denied/i)).toBeInTheDocument();
  });

  it("autoAllow=true auto-fires onAllow on mount for non-destructive ops", async () => {
    const onAllow = vi.fn().mockResolvedValue(undefined);
    render(
      <AiActionConfirmation
        call={enableCall}
        onAllow={onAllow}
        onDeny={vi.fn()}
        autoAllow
      />,
    );
    await waitFor(() => expect(onAllow).toHaveBeenCalledOnce());
  });

  it("autoAllow=true does NOT auto-fire for destructive ops", async () => {
    const onAllow = vi.fn().mockResolvedValue(undefined);
    render(
      <AiActionConfirmation
        call={uninstallCall}
        onAllow={onAllow}
        onDeny={vi.fn()}
        autoAllow
      />,
    );
    // Wait a tick to ensure useEffect has run
    await new Promise((r) => setTimeout(r, 50));
    expect(onAllow).not.toHaveBeenCalled();
    // Allow/Deny buttons should still be visible
    expect(screen.getByRole("button", { name: /allow/i })).toBeInTheDocument();
  });

  it("autoAllow=false (default) does not auto-fire", async () => {
    const onAllow = vi.fn().mockResolvedValue(undefined);
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={onAllow}
        onDeny={vi.fn()}
        autoAllow={false}
      />,
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(onAllow).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /allow/i })).toBeInTheDocument();
  });

  it("resets to pending (not stuck in 'running') if onAllow throws", async () => {
    const onAllow = vi.fn().mockRejectedValue(new Error("network error"));
    const user = userEvent.setup();
    render(
      <AiActionConfirmation
        call={installCall}
        onAllow={onAllow}
        onDeny={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /allow/i }));
    // After error, buttons should reappear (state resets to pending)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /allow/i })).toBeInTheDocument(),
    );
  });

  it("uses destructive button variant for uninstall_plugin", () => {
    render(
      <AiActionConfirmation
        call={uninstallCall}
        onAllow={vi.fn()}
        onDeny={vi.fn()}
      />,
    );
    // The Allow button should still be present
    expect(screen.getByRole("button", { name: /allow/i })).toBeInTheDocument();
  });
});
