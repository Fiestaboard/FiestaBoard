import { fireEvent, render, screen } from "@testing-library/react";
import { useLayoutEffect, useState } from "react";
import { describe, expect, it } from "vitest";

import { useDepsChanged } from "@/hooks/use-deps-changed";

/**
 * `useDepsChanged` is the render-phase replacement for the
 * "mirror an external value into local state" effect that
 * `react-hooks/set-state-in-effect` flags (issue #1568). It has to fire on
 * exactly the renders `useEffect(fn, deps)` would have fired on — the first
 * one, plus every dep-identity change — or the components ported onto it
 * silently stop syncing.
 */
describe("useDepsChanged", () => {
  /** Renders `value`, mirrored into state via useDepsChanged. */
  function Mirror({ value }: { value: string }) {
    const [mirrored, setMirrored] = useState("unsynced");
    const changed = useDepsChanged([value]);
    if (changed) setMirrored(value);
    return <output data-testid="mirror">{mirrored}</output>;
  }

  it("fires on the first render, so mount-time syncing still happens", () => {
    render(<Mirror value="from-server" />);
    expect(screen.getByTestId("mirror").textContent).toBe("from-server");
  });

  it("fires again when a dep changes identity", () => {
    const { rerender } = render(<Mirror value="from-server" />);
    rerender(<Mirror value="refetched" />);
    expect(screen.getByTestId("mirror").textContent).toBe("refetched");
  });

  it("does not fire when the deps are unchanged, so local edits survive re-renders", () => {
    function EditableMirror({ value }: { value: string }) {
      const [mirrored, setMirrored] = useState("unsynced");
      const changed = useDepsChanged([value]);
      if (changed) setMirrored(value);
      return (
        <>
          <output data-testid="mirror">{mirrored}</output>
          <button data-testid="edit" onClick={() => setMirrored("typed-by-user")} />
        </>
      );
    }

    const { rerender } = render(<EditableMirror value="from-server" />);
    fireEvent.click(screen.getByTestId("edit"));
    expect(screen.getByTestId("mirror").textContent).toBe("typed-by-user");

    // Same dep identity — a parent re-render must not clobber the local edit.
    rerender(<EditableMirror value="from-server" />);
    expect(screen.getByTestId("mirror").textContent).toBe("typed-by-user");
  });

  it("compares deps by identity, not by value, so equal-looking objects still re-sync", () => {
    function ObjectMirror({ obj }: { obj: { n: number } }) {
      const [seen, setSeen] = useState(0);
      const changed = useDepsChanged([obj]);
      if (changed) setSeen((s) => s + 1);
      return <output data-testid="seen">{seen}</output>;
    }

    const { rerender } = render(<ObjectMirror obj={{ n: 1 }} />);
    expect(screen.getByTestId("seen")).toHaveTextContent("1");
    rerender(<ObjectMirror obj={{ n: 1 }} />);
    expect(screen.getByTestId("seen")).toHaveTextContent("2");
  });

  it("treats a dep list of a different length as changed", () => {
    function VariadicMirror({ deps }: { deps: unknown[] }) {
      const [count, setCount] = useState(0);
      const changed = useDepsChanged(deps);
      if (changed) setCount((c) => c + 1);
      return <output data-testid="count">{count}</output>;
    }

    const { rerender } = render(<VariadicMirror deps={["a"]} />);
    expect(screen.getByTestId("count")).toHaveTextContent("1");
    rerender(<VariadicMirror deps={["a", "b"]} />);
    expect(screen.getByTestId("count")).toHaveTextContent("2");
  });

  it("mirrors the value before the first commit, not after it", () => {
    // This is the point of the refactor. The effect version committed
    // "unsynced", then re-rendered with "a" — so a layout effect (which runs
    // synchronously with each commit) would observe both. The render-phase
    // version restarts the render before committing, so the only value that
    // ever reaches the DOM is "a".
    const commits: string[] = [];

    function Recording({ value }: { value: string }) {
      const [mirrored, setMirrored] = useState("unsynced");
      const changed = useDepsChanged([value]);
      if (changed) setMirrored(value);
      useLayoutEffect(() => {
        commits.push(mirrored);
      });
      return <output>{mirrored}</output>;
    }

    render(<Recording value="a" />);
    expect(commits).toEqual(["a"]);
  });
});
