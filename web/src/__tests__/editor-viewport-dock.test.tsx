import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useEditorViewportDock } from "@/hooks/use-editor-viewport-dock";

let viewport: EventTarget & { height: number; offsetTop: number; scale: number };
const scrollIntoView = vi.fn();

function Editor({ enabled = true }: { enabled?: boolean }) {
  const content = useRef<HTMLDivElement>(null);
  const preview = useRef<HTMLElement>(null);
  const bottom = useEditorViewportDock(enabled, content, preview);
  return (
    <div ref={content} style={{ paddingBottom: bottom }} data-testid="editor">
      <input aria-label="Page name" />
      <section ref={preview} aria-label="Preview" />
      <textarea aria-label="Template" />
    </div>
  );
}

function resize(height: number) {
  act(() => {
    viewport.height = height;
    viewport.dispatchEvent(new Event("resize"));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  viewport = Object.assign(new EventTarget(), { height: 900, offsetTop: 0, scale: 1 });
  vi.stubGlobal("visualViewport", viewport);
  vi.stubGlobal("innerHeight", 900);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => setTimeout(() => callback(0), 16));
  vi.stubGlobal("cancelAnimationFrame", clearTimeout);
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("reserves scroll space, waits for layout, and keeps template focus while revealing the dock", () => {
  render(<Editor />);
  const input = screen.getByRole("textbox", { name: "Template" });
  input.focus();
  fireEvent.change(input, { target: { value: "Open today" } });
  resize(520);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "380px" });
  expect(scrollIntoView).not.toHaveBeenCalled();
  act(() => vi.advanceTimersByTime(32));
  expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: "start", behavior: "instant" });
  expect(input).toHaveFocus();
  expect(input).toHaveValue("Open today");
  resize(900);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "0px" });
  act(() => vi.advanceTimersByTime(32));
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
});

it("does not move the dock for name editing, viewport pan, or pinch zoom", () => {
  render(<Editor />);
  screen.getByRole("textbox", { name: "Page name" }).focus();
  resize(520);
  act(() => vi.advanceTimersByTime(32));
  expect(scrollIntoView).not.toHaveBeenCalled();
  screen.getByRole("textbox", { name: "Template" }).focus();
  act(() => {
    viewport.offsetTop = 80;
    viewport.dispatchEvent(new Event("scroll"));
  });
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "300px" });
  viewport.scale = 2;
  resize(450);
  act(() => vi.advanceTimersByTime(32));
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "0px" });
  expect(scrollIntoView).not.toHaveBeenCalled();
});

it("cancels pending scrolling when focus leaves or the editor unmounts", () => {
  const { unmount } = render(<Editor />);
  const remove = vi.spyOn(viewport, "removeEventListener");
  screen.getByRole("textbox", { name: "Template" }).focus();
  resize(520);
  screen.getByRole("textbox", { name: "Page name" }).focus();
  act(() => vi.advanceTimersByTime(32));
  expect(scrollIntoView).not.toHaveBeenCalled();
  screen.getByRole("textbox", { name: "Template" }).focus();
  resize(450);
  act(() => vi.advanceTimersByTime(16));
  unmount();
  act(() => vi.advanceTimersByTime(32));
  expect(scrollIntoView).not.toHaveBeenCalled();
  expect(remove.mock.calls.map(([event]) => event)).toEqual(["resize", "scroll"]);
});

it("clears reserved space when zoom changes even if the numeric bottom inset stays equal", () => {
  render(<Editor />);
  resize(520);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "380px" });
  viewport.scale = 2;
  viewport.offsetTop = 70;
  resize(450);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "0px" });
  viewport.scale = 1;
  viewport.offsetTop = 0;
  resize(520);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "380px" });
  expect(scrollIntoView).not.toHaveBeenCalled();
});

it("leaves a desktop pane unchanged and tolerates a missing VisualViewport", () => {
  const { unmount } = render(<Editor enabled={false} />);
  screen.getByRole("textbox", { name: "Template" }).focus();
  resize(520);
  act(() => vi.advanceTimersByTime(32));
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "0px" });
  expect(scrollIntoView).not.toHaveBeenCalled();
  unmount();
  vi.stubGlobal("visualViewport", undefined);
  render(<Editor />);
  expect(screen.getByTestId("editor")).toHaveStyle({ paddingBottom: "0px" });
});
