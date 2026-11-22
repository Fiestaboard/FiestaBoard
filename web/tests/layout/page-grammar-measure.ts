import type { Page } from "@playwright/test";

/** What the flat page grammar spaces: where the title sits and how far below it the page starts. */
export interface PageSpacing {
  /** The header row's first ink, from the top chrome's bottom (the phone header; the viewport top beside the rail). */
  top: number;
  /** The first ink of the header row (back link, icon or title), from the rail's right edge (the viewport's left on a phone). */
  left: number;
  /** The right-most ink of the page, from the viewport's right edge. */
  right: number;
  /** From the header's last ink to the first ink of the content below it. */
  headerGap: number;
  /** Whether the route is drawn in a rounded page-structure card. */
  card: boolean;
  /** What the content below the header starts with (for a failure message). */
  next: string;
}

/**
 * Measures from the DOM, the way Figma's metadata reads: text boxes, and
 * boxes that paint (a fill or a border). Hidden and zero-sized nodes do not
 * count, nor do the rail, the phone header or the tab bar.
 */
export async function measurePage(page: Page): Promise<PageSpacing> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime))
        .map((a) => a.finished.catch(() => undefined)),
    );
    await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
  });
  return page.evaluate(() => {
    const main = document.querySelector<HTMLElement>("#main-content") ?? document.querySelector("main")!;
    const h1 = main.querySelector<HTMLElement>("h1")!;
    const header = h1.closest<HTMLElement>("[data-slot=page-header]") ?? h1.parentElement!;
    const paints = (el: Element) => {
      const s = getComputedStyle(el);
      const bg = s.backgroundColor !== "rgba(0, 0, 0, 0)" && s.backgroundColor !== "transparent";
      const border =
        parseFloat(s.borderTopWidth) > 0 &&
        s.borderTopStyle !== "none" &&
        !/(, 0\)|\/ 0\)|transparent)$/.test(s.borderTopColor);
      return bg || border;
    };
    const ownText = (el: Element) =>
      Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && n.textContent!.trim() !== "");
    const ink = (root: Element) =>
      Array.from(root.querySelectorAll("*"))
        .filter((el) => {
          if (!(el instanceof HTMLElement || el instanceof SVGSVGElement)) return false;
          // The page's own grounds and wrappers (they hold the title) are not content.
          if (el.contains(h1) && el !== h1) return false;
          if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
          const r = el.getBoundingClientRect();
          // Zero-sized, and the 1 px hidden inputs behind a Select or a radio group.
          if (r.width < 2 || r.height < 2) return false;
          // A collapsed Reveal clips its content to 0 px.
          let clip = el.parentElement;
          while (clip && clip !== root) {
            const cr = clip.getBoundingClientRect();
            if (getComputedStyle(clip).overflow !== "visible" && (cr.height < 1 || cr.width < 1)) return false;
            clip = clip.parentElement;
          }
          return el instanceof SVGSVGElement || ownText(el) || paints(el) || /^(IMG|CANVAS|INPUT)$/.test(el.tagName);
        })
        // Text runs across its line box, as a Figma text node does, but only
        // as wide as its glyphs, not the padded box around it (a ghost link).
        .map((el) => {
          let r = el.getBoundingClientRect();
          if (ownText(el) && !paints(el)) {
            const range = document.createRange();
            range.selectNodeContents(el);
            const glyphs = range.getBoundingClientRect();
            r = new DOMRect(glyphs.left, r.top, glyphs.width, r.height);
          }
          return Object.assign(r, { el });
        });
    // An open item's crumb and name belong to the header block above the content.
    const subheader = main.querySelector('[data-slot="page-subheader"][data-state="open"]');
    const headerInk = ink(header)
      .concat(subheader ? ink(subheader) : [])
      .concat([Object.assign(h1.getBoundingClientRect(), { el: h1 as Element })]);
    const headerBottom = Math.max(...headerInk.map((r) => r.bottom));
    const below = ink(main).filter((r) => r.top >= headerBottom - 0.5);
    const firstBelow = Math.min(...below.map((r) => r.top));
    const next = below.find((r) => r.top === firstBelow)?.el;
    // The rail: a visible <aside> narrower than half the window (the phone
    // header is an <aside> too, but spans the width).
    const rails = Array.from(document.querySelectorAll("aside"))
      .filter((a) => a.checkVisibility())
      .map((a) => a.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.width < window.innerWidth / 2 && r.left < 40);
    // The phone bar: a fixed <header> across the top.
    const phoneHeader = Array.from(document.querySelectorAll("header"))
      .filter((a) => a.checkVisibility() && getComputedStyle(a).position === "fixed")
      .map((a) => a.getBoundingClientRect())
      .find((r) => r.width >= window.innerWidth / 2 && r.top < 40);
    const chromeBottom = phoneHeader ? phoneHeader.bottom : 0;
    const railRight = rails.length ? Math.max(...rails.map((r) => r.right)) : 0;
    // Clipped scrollers (a board at actual size) can run past the edge.
    const width = document.documentElement.clientWidth;
    const all = ink(main).filter((r) => r.right <= width + 0.5);
    const round = (n: number) => Math.round(n * 10) / 10;
    return {
      top: round(Math.min(...headerInk.map((r) => r.top)) - chromeBottom),
      left: round(Math.min(...headerInk.map((r) => r.left)) - railRight),
      right: round(width - Math.max(...all.map((r) => r.right))),
      headerGap: round(firstBelow - headerBottom),
      card: !!main.querySelector("[data-slot=page-card][data-surface=card]"),
      next: next
        ? `${next.tagName.toLowerCase()}[${next.getAttribute("data-slot") ?? ""}] ${(next.textContent ?? "").trim().slice(0, 24)}`
        : "",
    };
  });
}
