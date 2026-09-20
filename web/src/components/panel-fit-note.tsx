import { Text } from "@fiestaboard/ui";

import { usePanelTargets } from "@/hooks/use-panel-targets";
import { useTranslations } from "@/i18n/translations";
import { panelsFittingGrid } from "@/lib/panel-page-fit";

interface PanelFitNoteProps {
  /** "flagship" | "note" | "note_array" */
  deviceType: string;
  notesWide?: number;
  notesTall?: number;
  className?: string;
}

/**
 * A quiet line naming the FiestaPanel a page's grid fits.
 *
 * Panels are the one board shape whose dimensions nobody chose — they are
 * auto-fit from a TV's diagonal — so "3 × 30" tells a user nothing about
 * whether a page will land on the wall correctly, and "Fits Kitchen TV" tells
 * them everything. Renders nothing when no panel has that grid, so an install
 * without panels never sees it.
 */
export function PanelFitNote({ deviceType, notesWide = 1, notesTall = 1, className }: PanelFitNoteProps) {
  const t = useTranslations("fiestaPanels");
  const targets = usePanelTargets();
  const matches = panelsFittingGrid(targets, deviceType, notesWide, notesTall);
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
