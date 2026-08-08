/**
 * Swizzled `@theme/PaginatorNavLink` — the prev/next tiles at the foot of every
 * doc page, rebuilt on FiestaUI's `Card` instead of Infima's `.pagination-nav__link`
 * plus the hand-written border/radius/hover rules that used to live in `custom.css`.
 *
 * The Infima placement classes stay: `.pagination-nav` is a two-column grid and
 * `--prev` / `--next` are what put each tile in its column and align its text.
 * Only the box treatment moves to the design system, which `custom.css` now
 * neutralises on the anchor so the `Card` inside owns the border and padding.
 */

import Link from "@docusaurus/Link";
import { Card, CardDescription, cn, Text } from "@fiestaboard/ui";
import type { Props } from "@theme/PaginatorNavLink";
import type { ReactNode } from "react";

export default function PaginatorNavLink({ permalink, title, subLabel, isNext }: Props): ReactNode {
  return (
    <Link
      className={cn(
        "pagination-nav__link no-underline",
        isNext ? "pagination-nav__link--next" : "pagination-nav__link--prev",
      )}
      to={permalink}
    >
      {/* `Card`'s own `gap-6`/`py-6` are tuned for full content cards; a paginator
          tile is a two-line label, so it tightens to `gap-1`/`p-4`. */}
      <Card className="h-full gap-1 p-4 py-4 hover:border-ring">
        {subLabel && <CardDescription className="text-xs">{subLabel}</CardDescription>}
        {/* `Text`, not `CardTitle`: `CardTitle` only renders h1-h6, and upstream
            deliberately uses a plain element here — a prev/next tile is a
            navigation label, and promoting it would put two extra headings at
            the foot of every page for anyone navigating by heading. */}
        <Text as="span" size="base" weight="semibold" className="block">
          {title}
        </Text>
      </Card>
    </Link>
  );
}
