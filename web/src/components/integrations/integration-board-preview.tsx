import {
  Box,
  Button,
  Flex,
  previewLabels,
  previewMessage,
  Skeleton,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
} from "@fiestaboard/ui";
import { useState } from "react";

import { BoardViewport } from "@/components/board-viewport";
import { useBoardSettings } from "@/hooks/use-board";
import { useEffectiveBoardColor } from "@/hooks/use-effective-board-color";
import { useEffectiveCode62Glyph } from "@/hooks/use-effective-code62-glyph";
import { useTranslations } from "@/i18n/translations";
import type { RegistryEntry } from "@/lib/api";

/** The catalog's literal example remains available after installation. The
 * effective color can load after the catalog; follow it until the user makes
 * a local preview choice, without changing the actual board's settings. */
export function IntegrationBoardPreview({
  entry,
  size,
  caption,
  controls = true,
}: {
  entry?: RegistryEntry;
  size?: "sm" | "md" | "lg";
  /** A line under the board, e.g. 07d's "Sample page using this integration". */
  caption?: string;
  /** The shape tabs and board colour pair; 07d's detail pane draws neither (BB-FC-9). */
  controls?: boolean;
}) {
  const t = useTranslations("pluginDetail");
  const { isLoading: isLoadingBoard } = useBoardSettings();
  const boardColor = useEffectiveBoardColor();
  const code62Glyph = useEffectiveCode62Glyph();
  const [previewColor, setPreviewColor] = useState<"black" | "white" | null>(null);
  if (!entry?.previews?.length) return null;
  if (isLoadingBoard) return <Skeleton className="h-32 w-full" />;
  const labels = previewLabels(entry.previews, {
    flagship: t("deviceFlagship"),
    note: t("deviceNote"),
    noteArray: t("deviceNoteArray"),
  });
  const effectiveColor = previewColor ?? boardColor;
  return (
    <Stack gap="4" className="min-w-0 items-center" data-slot="board-showcase">
      <Tabs defaultValue={0} className="w-full min-w-0">
        {controls && entry.previews.length > 1 && (
          <Flex justify="center">
            <TabsList aria-label={t("boardShapeLabel")} className="h-auto max-w-full flex-wrap">
              {labels.map((label, index) => (
                <TabsTrigger key={label} value={index}>
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Flex>
        )}
        {entry.previews.map((preview, index) => (
          <TabsContent key={labels[index]} value={index} className={controls ? "mt-4 min-w-0" : "min-w-0"}>
            {/* BoardShowcase's centered static board clips the first columns in
                a narrow slot. The house viewport retains readable Actual size,
                reachable edges and the user's optional Fit overview. */}
            <Box className={controls ? "min-w-0 rounded-xl bg-muted/40 p-4 shadow-card" : "min-w-0"}>
              <BoardViewport
                message={previewMessage(preview)}
                size={size}
                layout={size === "sm" ? "pane" : "phone-hero"}
                regionLabel={t("boardPreviewLabel", { name: entry.name })}
                boardType={effectiveColor}
                code62Glyph={code62Glyph}
                deviceType={preview.device_type ?? "flagship"}
                notesWide={preview.notes_wide ?? 1}
                notesTall={preview.notes_tall ?? 1}
                gridRows={preview.grid_rows}
                gridCols={preview.grid_cols}
                isStatic
              />
            </Box>
          </TabsContent>
        ))}
      </Tabs>
      {caption && (
        <Text size="xs" tone="muted" className="self-start">
          {caption}
        </Text>
      )}
      {controls && (
        <Flex role="group" aria-label={t("boardColorLabel")} justify="center" gap="1" wrap>
          {(["black", "white"] as const).map((color) => (
            <Button
              key={color}
              size="sm"
              variant={effectiveColor === color ? "default" : "outline"}
              aria-pressed={effectiveColor === color}
              onClick={() => setPreviewColor(color)}
            >
              {t(color === "black" ? "blackBoard" : "whiteBoard")}
            </Button>
          ))}
        </Flex>
      )}
    </Stack>
  );
}
