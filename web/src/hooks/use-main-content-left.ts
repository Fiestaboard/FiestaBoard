"use client";

import { useEffect, useState } from "react";

/** Where the app's content column starts: right of the nav rail, 0 with no rail. */
function measure(): number {
  const main = document.getElementById("main-content");
  if (!main) return 0;
  const left = main.getBoundingClientRect().left + (parseFloat(getComputedStyle(main).paddingLeft) || 0);
  return Math.max(0, Math.round(left));
}

/**
 * The left edge a viewport-fixed bar of the content column starts at, so it
 * never covers the nav rail (a landscape phone or tablet, BB-B-17). Follows
 * the rail collapsing and the window resizing.
 */
export function useMainContentLeft(enabled = true): number {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const update = () => setLeft(measure());
    update();
    const main = document.getElementById("main-content");
    const resize = new ResizeObserver(update);
    if (main) resize.observe(main);
    const mutation = new MutationObserver(update);
    if (main) mutation.observe(main, { attributes: true, attributeFilter: ["class", "style"] });
    window.addEventListener("resize", update);
    // The rail's collapse animates the padding; settle on its final value.
    main?.addEventListener("transitionend", update);
    return () => {
      resize.disconnect();
      mutation.disconnect();
      window.removeEventListener("resize", update);
      main?.removeEventListener("transitionend", update);
    };
  }, [enabled]);
  return enabled ? left : 0;
}
