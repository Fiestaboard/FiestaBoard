import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { useEditorToolbarPortal } from "@/hooks/use-editor-toolbar-portal";
import { useVisualViewportBottom } from "@/hooks/use-visual-viewport-bottom";

afterEach(() => vi.unstubAllGlobals());

it("keeps independent toolbar landmarks alive through a peer unmount and updates their names", () => {
  const first = renderHook(({ enabled, label }) => useEditorToolbarPortal(enabled, label), {
    initialProps: { enabled: true, label: "First editor tools" },
  });
  const second = renderHook(() => useEditorToolbarPortal(true, "Second editor tools"));
  const firstHost = first.result.current!;
  const secondHost = second.result.current!;
  expect(firstHost).toHaveAccessibleName("First editor tools");
  expect(secondHost.parentElement).toBe(document.body);
  first.rerender({ enabled: true, label: "Outils du premier éditeur" });
  expect(first.result.current).toBe(firstHost);
  expect(firstHost).toHaveAccessibleName("Outils du premier éditeur");
  first.rerender({ enabled: false, label: "Outils du premier éditeur" });
  expect(firstHost).not.toBeInTheDocument();
  expect(secondHost).toBeInTheDocument();
  first.rerender({ enabled: true, label: "First editor tools" });
  expect(firstHost).toBeInTheDocument();
  first.unmount();
  expect(firstHost).not.toBeInTheDocument();
  expect(secondHost).toBeInTheDocument();
  second.unmount();
  expect(secondHost).not.toBeInTheDocument();
});

it("tracks visual viewport resize and pan and removes both subscriptions on unmount", () => {
  const viewport = Object.assign(new EventTarget(), { height: 900, offsetTop: 0 });
  const remove = vi.spyOn(viewport, "removeEventListener");
  vi.stubGlobal("visualViewport", viewport);
  vi.stubGlobal("innerHeight", 900);
  const { result, unmount } = renderHook(useVisualViewportBottom);
  expect(result.current).toBe(0);
  act(() => {
    viewport.height = 520;
    viewport.dispatchEvent(new Event("resize"));
  });
  expect(result.current).toBe(380);
  act(() => {
    viewport.offsetTop = 100;
    viewport.dispatchEvent(new Event("scroll"));
  });
  expect(result.current).toBe(280);
  act(() => {
    viewport.offsetTop = 400;
    viewport.dispatchEvent(new Event("scroll"));
  });
  expect(result.current).toBe(0);
  unmount();
  expect(remove.mock.calls.map(([event]) => event)).toEqual(["resize", "scroll"]);
});

it("keeps tools at the layout viewport edge when VisualViewport is unavailable", () => {
  vi.stubGlobal("visualViewport", undefined);
  const { result } = renderHook(useVisualViewportBottom);
  expect(result.current).toBe(0);
});
