import { Box, Flex, Text } from "@fiestaboard/ui";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The template card before the rich editor exists (the lazy chunk's Suspense
 * fallback and TipTap's first, editor-less render). It is the loaded card's
 * box: the same header row (the host's title and an empty meta line) and the
 * same rows-area height, so nothing under the card moves when the editor
 * mounts (FABLE-2653 §3.2, Den TV load CLS). Kept out of the editor's module
 * so the host can draw it without loading the editor.
 */
export function TemplateCardPlaceholder({
  boardLines,
  cardTitle,
  roundedTop = false,
  className,
}: {
  boardLines: number;
  cardTitle?: ReactNode;
  /** The loaded card squares its top under a toolbar; the host's fallback has none above it. */
  roundedTop?: boolean;
  className?: string;
}) {
  return (
    <Box
      data-slot="template-editor"
      data-placeholder=""
      aria-busy="true"
      className={cn("relative flex h-full min-h-0 flex-col", className)}
    >
      <Box className="flex min-h-0 flex-1 flex-col">
        <Box
          data-slot="template-card-placeholder"
          className={cn(
            "border bg-background relative flex flex-1 flex-col rounded-md",
            !roundedTop && "rounded-t-none",
          )}
        >
          <Flex align="center" justify={cardTitle ? "between" : "end"} gap="3" className="min-h-8 px-3 pt-2">
            {cardTitle}
            {/* The count and caret's line, empty until the editor counts. */}
            <Text as="p" size="xs" aria-hidden="true" className="font-mono">
              {" "}
            </Text>
          </Flex>
          <Box
            className="relative flex-1"
            style={{ padding: "0.75rem", paddingTop: "0.5rem", minHeight: `${boardLines * 1.5 + 1.25}rem` }}
          >
            <Box style={{ minHeight: `${boardLines * 1.5}rem` }} />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
