"use client";

import { useState } from "react";

/**
 * Render-phase equivalent of `useEffect(fn, deps)` for the specific job of
 * mirroring an external value (a query result, a prop) into local state.
 *
 * Returns `true` on the first render, and on any later render where one of
 * `deps` changed identity — i.e. exactly the renders after which
 * `useEffect(fn, deps)` would have fired. Callers do their `setState` calls
 * inside that branch, during render, instead of in an effect:
 *
 * ```tsx
 * const settingsChanged = useDepsChanged([data?.general]);
 * if (settingsChanged && data?.general) {
 *   setTimezone(data.general.timezone ?? DEFAULT_TZ);
 * }
 * ```
 *
 * Why this is better than the effect it replaces: React restarts the render
 * immediately when a component sets its own state during render, *before*
 * committing — so the mirrored value is on screen in the first commit. The
 * effect version commits the stale value, paints, then re-renders, which is
 * the cascading render that `react-hooks/set-state-in-effect` warns about
 * (and, per the React docs, a state update during render of the *same*
 * component is the supported way to adjust state when a prop changes:
 * https://react.dev/reference/react/useState#storing-information-from-previous-renders).
 *
 * Constraints, same as any render-phase update:
 * - Only call `setState` for THIS component inside the branch. Calling a
 *   parent's setter (or a router/toast side effect) during render is illegal;
 *   those must stay in an effect.
 * - The branch must be idempotent. It runs once per change because the deps
 *   snapshot is taken as soon as it fires.
 */
export function useDepsChanged(deps: readonly unknown[]): boolean {
  const [prev, setPrev] = useState<readonly unknown[] | null>(null);

  if (prev === null || prev.length !== deps.length || deps.some((dep, i) => !Object.is(dep, prev[i]))) {
    setPrev(deps);
    return true;
  }

  return false;
}
