"use client";

import { CharacterGlyph, Flex } from "@fiestaboard/ui";

import { useHomeColorStrip } from "@/hooks/use-home-color-strip";

/** The board's six colour tiles, in the hardware's own order. */
const STRIP_TILES = ["red", "orange", "yellow", "green", "blue", "violet"] as const;

/**
 * Home's colour strip (07e Appearance › Boards, "Show the color strip on
 * Home"): a row of the board's six colour tiles under the Now showing board,
 * the rainbow 07a draws along the hero board's foot. It is decoration, drawn
 * outside the board so the board itself still shows exactly what is on the
 * wall, and hidden from assistive tech. This browser can turn it off.
 */
export function HomeColorStrip({ size = "md" }: { size?: "sm" | "md" }) {
  const [show] = useHomeColorStrip();
  if (!show) return null;
  return (
    <Flex justify="center" gap="1" aria-hidden="true" data-testid="home-color-strip">
      {STRIP_TILES.map((color) => (
        <CharacterGlyph key={color} token={color} size={size} decorative />
      ))}
    </Flex>
  );
}
