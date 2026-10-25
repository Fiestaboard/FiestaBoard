"use client";

import { Alert, AlertDescription, AlertTitle, Box, Button, Flex, Text } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, History, Save, UploadCloud } from "lucide-react";
import { useState } from "react";

import Link from "@/components/smart-link";
import { queryKeys, useBoardCurrentMessage } from "@/hooks/use-board";
import { useRestoreBoard } from "@/hooks/use-restore-board";
import { useSaveBoardAsPage } from "@/hooks/use-save-board-as-page";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type BoardCurrentMessageResponse, type SilenceStatus } from "@/lib/api";
import type { BoardGeometry } from "@/lib/board-characters-to-template";
import { formatDetectedAt } from "@/lib/board-out-of-sync-time";

export interface BoardOutOfSyncBannerProps {
  /** The board to watch; omitted means the primary (single-board Home). */
  boardId?: string;
  /** The board's page geometry, so a saved page fits it. */
  geometry: BoardGeometry;
  /** The board is paused: nothing will be sent to it, so Restore is held. */
  paused: boolean;
  /** Render nothing (Live Mode is driving the board from the page editor). */
  suppressed?: boolean;
}

type Face = "out-of-sync" | "overwritten" | "kept";

type SavedPage = { id: string; name: string; gridKey: string };

/**
 * What another app put on the board, and what the user can do about it
 * (issue #1945). One banner, mounted on Home and on each display's own page.
 *
 * - **out-of-sync** (warning): the board shows something FiestaBoard did not
 *   send. [Restore] puts the page back; [Save as page] keeps what is there.
 *   A muted hold line says, before the tap, when Restore will not send
 *   (pause, silence) or that it resends every display (a secondary board).
 * - **overwritten** (warning, #2354): a display that cannot read back what it
 *   shows (a Divoom Pixoo) reported another app wrote it. There is no frame
 *   to compare or save, so only [Restore]. With auto-restore on, the backend
 *   takes the display back on its next pass, so this mostly shows with it off.
 * - **kept** (info): FiestaBoard has since repainted, but the backend still
 *   holds the last confirmed external frame. [Save as page] or [Dismiss].
 *
 * After a save the button becomes "Saved as “…”" + [Open page], so a second
 * tap cannot make a duplicate; it returns when the board shows a new grid.
 *
 * It owns its data like SilenceImminentBanner: the board-state query the
 * preview already observes (deduped by React Query) and the silence status.
 */
export function BoardOutOfSyncBanner({ boardId, geometry, paused, suppressed = false }: BoardOutOfSyncBannerProps) {
  const t = useTranslations("boardOutOfSync");
  const locale = useLocale();
  const queryClient = useQueryClient();

  const { data: boardState } = useBoardCurrentMessage(boardId, { poll: !paused });
  const { data: silenceStatus } = useQuery<SilenceStatus>({
    queryKey: queryKeys.silenceStatus(boardId),
    queryFn: () => api.getSilenceStatus(boardId),
  });

  const { save, isPending: isSaving } = useSaveBoardAsPage();
  const { restore, isPending: isRestoring } = useRestoreBoard({ boardId, paused });
  const [savedPage, setSavedPage] = useState<SavedPage | null>(null);
  const [isDismissing, setIsDismissing] = useState(false);

  // During silence FiestaBoard leaves the board alone on purpose and Restore
  // cannot send, so there is nothing to offer until the window ends (#1943).
  if (suppressed || !boardState || silenceStatus?.active) return null;

  const characters = boardState.characters ?? null;
  const expected = boardState.expected_characters ?? null;
  const expectedKey = JSON.stringify(expected);
  const isOutOfSync = characters !== null && expected !== null && JSON.stringify(characters) !== expectedKey;
  const externalFrame = boardState.external_characters ?? null;
  const hasKeptFrame = externalFrame !== null && JSON.stringify(externalFrame) !== expectedKey;
  // Set only from a no-read-back display's own overwrite report, and cleared
  // server-side on every FiestaBoard write. Such a display still serves
  // `characters` (the last frame sent, equal to `expected_characters`), so it
  // cannot be told apart by them.
  const isOverwritten = Boolean(boardState.overwritten_at);

  // The live faces win: what is on the board now is what the user sees.
  const face: Face | null = isOutOfSync ? "out-of-sync" : isOverwritten ? "overwritten" : hasKeptFrame ? "kept" : null;
  if (face === null) return null;

  // The frame Save keeps: what the board shows, or the held external frame.
  // The overwritten face has none (nothing was read back), so no Save.
  const grid: number[][] | null = face === "out-of-sync" ? characters : face === "kept" ? externalFrame : null;
  const gridKey = grid === null ? null : JSON.stringify(grid);
  const saved = savedPage !== null && savedPage.gridKey === gridKey ? savedPage : null;

  const handleSave = async () => {
    if (grid === null || gridKey === null) return;
    try {
      const page = await save(grid, geometry);
      setSavedPage({ id: page.id, name: page.name, gridKey });
    } catch {
      // Toasted by the hook; the button stays so the user can try again.
    }
  };

  const handleDismiss = async () => {
    setIsDismissing(true);
    // Gone on the tap: drop the held frame from the cache first.
    queryClient.setQueryData(queryKeys.boardCurrentMessage(boardId), (old: BoardCurrentMessageResponse | undefined) => {
      if (!old) return old;
      const { external_characters: _held, external_detected_at: _heldAt, ...rest } = old;
      return rest;
    });
    try {
      await api.dismissExternalFrame(boardId);
    } catch {
      // The refetch below brings the notice back if the frame is still held.
    } finally {
      setIsDismissing(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.boardCurrentMessage(boardId) });
    }
  };

  // A live face: the board shows something else now, and Restore is offered.
  const live = face !== "kept";
  // Only a face with a frame can save it.
  const canSave = grid !== null;

  // The one hold line: a paused display holds Restore (live faces only).
  const hold: string | null = live && paused ? t("holdPaused") : null;

  const Icon = live ? AlertTriangle : History;

  return (
    <Alert
      variant={live ? "warning" : "info"}
      // A state the board is in, not a failure that just happened.
      politeness="polite"
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3"
      data-testid="board-out-of-sync"
      data-face={face}
      data-saved={saved ? "true" : undefined}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <Box className="flex-1 min-w-0">
        <AlertTitle>
          {live ? t("title") : t("keptTitle", { time: formatDetectedAt(boardState.external_detected_at, locale) })}
        </AlertTitle>
        <AlertDescription>
          {face === "out-of-sync"
            ? t("detail")
            : face === "overwritten"
              ? t("overwrittenDetail", { time: formatDetectedAt(boardState.overwritten_at, locale) })
              : t("keptDetail")}
        </AlertDescription>
        {hold && (
          <Text size="xs" className="text-muted-foreground mt-1" data-testid="board-out-of-sync-hold">
            {hold}
          </Text>
        )}
      </Box>
      <Flex align="center" gap="2" wrap className="sm:self-center shrink-0">
        {live && (
          <Button size="sm" variant="outline" onClick={restore} disabled={isRestoring} className="gap-1.5">
            {isRestoring ? (
              <Spinner label={null} className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <UploadCloud className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {t("restore")}
          </Button>
        )}
        {!canSave ? null : saved ? (
          <Flex align="center" gap="1.5" wrap>
            <Text as="span" size="sm" className="inline-flex min-w-0 items-center gap-1.5">
              <Check className="h-3.5 w-3.5 text-success shrink-0" aria-hidden="true" />
              <Text as="span" size="sm" className="truncate max-w-[32ch]">
                {t("savedAs", { pageName: saved.name })}
              </Text>
            </Text>
            <Button asChild size="sm" variant="link" className="h-auto px-0 whitespace-nowrap">
              <Link href={`/pages/edit/${saved.id}`}>{t("openPage")}</Link>
            </Button>
          </Flex>
        ) : (
          <Button size="sm" variant="outline" onClick={handleSave} disabled={isSaving} className="gap-1.5">
            {isSaving ? (
              <Spinner label={null} className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Save className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {t("saveAsPage")}
          </Button>
        )}
        {!live && (
          <Button size="sm" variant="ghost" onClick={handleDismiss} disabled={isDismissing}>
            {t("dismiss")}
          </Button>
        )}
      </Flex>
    </Alert>
  );
}
