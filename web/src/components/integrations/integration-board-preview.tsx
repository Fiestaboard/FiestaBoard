import { BoardShowcase, Skeleton } from "@fiestaboard/ui";
import { useState } from "react";

import { useBoardSettings } from "@/hooks/use-board";
import { useEffectiveBoardColor } from "@/hooks/use-effective-board-color";
import { useEffectiveCode62Glyph } from "@/hooks/use-effective-code62-glyph";
import { useTranslations } from "@/i18n/translations";
import type { RegistryEntry } from "@/lib/api";

/** The catalog's literal example remains available after installation. The
 * effective color can load after the catalog; follow it until the user makes
 * a local preview choice, without changing the actual board's settings. */
export function IntegrationBoardPreview({ entry, size }: { entry?: RegistryEntry; size?: "sm" | "md" | "lg" }) {
  const t = useTranslations("pluginDetail");
  const { isLoading: isLoadingBoard } = useBoardSettings();
  const boardColor = useEffectiveBoardColor();
  const code62Glyph = useEffectiveCode62Glyph();
  const [previewColor, setPreviewColor] = useState<"black" | "white" | null>(null);
  if (!entry?.previews?.length) return null;
  if (isLoadingBoard) return <Skeleton className="h-32 w-full" />;
  return (
    <BoardShowcase
      size={size}
      previews={entry.previews}
      previewLabel={t("boardPreviewLabel", { name: entry.name })}
      boardType={previewColor ?? boardColor}
      onBoardTypeChange={setPreviewColor}
      code62Glyph={code62Glyph}
      labels={{
        flagship: t("deviceFlagship"),
        note: t("deviceNote"),
        noteArray: t("deviceNoteArray"),
        boardShape: t("boardShapeLabel"),
        boardColor: t("boardColorLabel"),
        blackBoard: t("blackBoard"),
        whiteBoard: t("whiteBoard"),
      }}
    />
  );
}
