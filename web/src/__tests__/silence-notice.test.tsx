// The shared "this board is silenced" notice and the one place its time comes
// from (#1943). Every surface (Home, Change Page, Force Set, Compose, Live
// Output) renders SilenceNotice with a time from silenceEndsAtLabel, so the
// wording and the time cannot disagree between them.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SilenceNotice } from "@/components/silence-notice";
import type { SilenceStatus } from "@/lib/api";
import { silenceEndsAt, silenceEndsAtLabel } from "@/lib/silence-until";

const BASE: SilenceStatus = {
  enabled: true,
  active: true,
  start_time_utc: "22:00+00:00",
  end_time_utc: "07:00+00:00",
  current_time_utc: "02:00+00:00",
  next_change_utc: "07:00+00:00",
};

const label = (d: Date) => d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

describe("silenceEndsAtLabel", () => {
  it("formats ends_at_utc in the viewer's locale and zone", () => {
    const status = { ...BASE, ends_at_utc: "2026-10-18T07:00:00+00:00" };
    expect(silenceEndsAtLabel(status)).toBe(label(new Date("2026-10-18T07:00:00+00:00")));
  });

  it("falls back to seconds_until_next_change for an older API", () => {
    const now = Date.parse("2026-10-18T02:00:00Z");
    const status = { ...BASE, seconds_until_next_change: 5 * 3600 };
    expect(silenceEndsAt(status, now)?.toISOString()).toBe("2026-10-18T07:00:00.000Z");
    expect(silenceEndsAtLabel(status, now)).toBe(label(new Date("2026-10-18T07:00:00Z")));
  });

  it("is null when the board is not silenced, or nothing says when it ends", () => {
    expect(silenceEndsAtLabel({ ...BASE, active: false, ends_at_utc: "2026-10-18T07:00:00+00:00" })).toBeNull();
    expect(silenceEndsAtLabel(BASE)).toBeNull();
    expect(silenceEndsAtLabel(undefined)).toBeNull();
  });

  it("ignores an unparseable ends_at_utc and uses the countdown", () => {
    const now = Date.parse("2026-10-18T02:00:00Z");
    const status = { ...BASE, ends_at_utc: "not a date", seconds_until_next_change: 60 };
    expect(silenceEndsAt(status, now)?.toISOString()).toBe("2026-10-18T02:01:00.000Z");
  });
});

describe("SilenceNotice", () => {
  it("renders nothing when the board is not silenced", () => {
    const { container } = render(<SilenceNotice active={false} until="7:00 AM" description="x" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("titles itself with the end time and carries the surface's sentence", () => {
    render(<SilenceNotice until="7:00 AM" description="The board stays quiet until then." data-testid="n" />);
    const notice = screen.getByTestId("n");
    expect(notice).toHaveTextContent("Silenced until 7:00 AM");
    expect(notice).toHaveTextContent("The board stays quiet until then.");
    expect(notice).toHaveAttribute("role", "status");
  });

  it("says the board is silenced when the end time is unknown", () => {
    render(<SilenceNotice until={null} description="x" data-testid="n" />);
    expect(screen.getByTestId("n")).toHaveTextContent("The board is silenced");
  });

  it("renders the action row", () => {
    render(
      <SilenceNotice until="7:00 AM" description="x">
        <button type="button">Show now</button>
        <button type="button">Discard message</button>
      </SilenceNotice>,
    );
    expect(screen.getByRole("button", { name: "Show now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard message" })).toBeInTheDocument();
  });

  it("marks the warning variant", () => {
    render(<SilenceNotice variant="warning" until="7:00 AM" description="x" data-testid="n" />);
    const notice = screen.getByTestId("n");
    expect(notice).toHaveAttribute("data-variant", "warning");
    expect(notice.className).toContain("border-warning");
  });

  it("compact puts title and sentence on one line", () => {
    render(<SilenceNotice compact until="7:00 AM" description="Live Output is previewing only." data-testid="n" />);
    expect(screen.getByTestId("n")).toHaveTextContent("Silenced until 7:00 AM — Live Output is previewing only.");
  });
});
