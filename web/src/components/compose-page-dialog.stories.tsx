import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";

import { ComposePageDialog } from "./compose-page-dialog";

/**
 * Compose during silence (#1943, #1944). "Send now anyway" names what Send
 * does (it wakes the board); when the board holds messages, "Hold until
 * 7:00 AM" is the primary action and never wakes it.
 */
const meta = {
  title: "Silence/ComposePageDialog",
  component: ComposePageDialog,
  parameters: { layout: "centered" },
  args: {
    open: true,
    onOpenChange: fn(),
    deviceType: "flagship",
  },
} satisfies Meta<typeof ComposePageDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Not silenced: today's footer — Cancel, Save as Page, Send to board. */
export const Default: Story = {};

export const SilencedHoldsOn: Story = {
  args: { silence: { until: "7:00 AM", holds: true } },
  play: async () => {
    const body = within(document.body);
    const hold = await body.findByTestId("compose-hold");
    await expect(hold).toHaveTextContent("Hold until 7:00 AM");
    // The primary action is the last button in the footer (and in tab order).
    const buttons = Array.from(hold.parentElement?.querySelectorAll("button") ?? []);
    await expect(buttons[buttons.length - 1]).toBe(hold);
  },
};

export const SilencedHoldsOnPhone: Story = {
  ...SilencedHoldsOn,
  globals: { viewport: { value: "phone375", isRotated: false } },
};

export const SilencedHoldsOff: Story = {
  args: { silence: { until: "7:00 AM", holds: false } },
};

/** Hold pressed and still in flight: "Holding…". */
export const Holding: Story = {
  args: { silence: { until: "7:00 AM", holds: true } },
  beforeEach: () => {
    // Keep the hold request pending so the in-flight state stays on screen.
    const original = window.fetch;
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/message")) return new Promise<Response>(() => {});
      return original(input, init);
    }) as typeof window.fetch;
    return () => {
      window.fetch = original;
    };
  },
  play: async () => {
    const body = within(document.body);
    await userEvent.type(await body.findByRole("textbox", { name: /message/i }), "GOOD MORNING");
    await userEvent.click(body.getByTestId("compose-hold"));
    await expect(await body.findByText("Holding…")).toBeVisible();
  },
};
