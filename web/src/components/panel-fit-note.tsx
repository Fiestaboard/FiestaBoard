import { Text } from "@fiestaboard/ui";

import { useDisplayTargets } from "@/hooks/use-panel-targets";
import { useTranslations } from "@/i18n/translations";
import { panelsFittingGrid } from "@/lib/panel-page-fit";

interface PanelFitNoteProps {
  /** "flagship" | "note" | "note_array" | "panel" */
  deviceType: string;
  notesWide?: number;
  notesTall?: number;
  /** Panel pages only: the page's character grid. */
  gridRows?: number | null;
  gridCols?: number | null;
  className?: string;
}

/**
 * A quiet line naming the display (a FiestaPanel, or any other board with a
 * custom grid, such as an LED matrix) a page's grid fits.
 *
 * Panels are the one board shape whose dimensions nobody chose — they are
 * auto-fit from a TV's diagonal — so "3 × 30" tells a user nothing about
 * whether a page will land on the wall correctly, and "Fits Kitchen TV" tells
 * them everything. Renders nothing when no panel has that grid, so an install
 * without panels never sees it.
 */
export function PanelFitNote({
  deviceType,
  notesWide = 1,
  notesTall = 1,
  gridRows,
  gridCols,
  className,
}: PanelFitNoteProps) {
  const t = useTranslations("fiestaPanels");
  const targets = useDisplayTargets();
  const matches = panelsFittingGrid(targets, deviceType, notesWide, notesTall, gridRows, gridCols);
  if (matches.length === 0) return null;
  const [first, ...rest] = matches;
  return (
    <Text as="span" size="xs" tone="muted" className={className}>
      {rest.length === 0
        ? t("fitsPanel", { name: first.name })
        : t("fitsPanelAndMore", { name: first.name, count: rest.length })}
    </Text>
  );
}
