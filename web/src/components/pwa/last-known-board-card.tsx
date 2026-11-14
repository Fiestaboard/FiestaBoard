"use client";

import { Badge, type BoardCellGrid, Card, CardContent, CardHeader, CardTitle, Flex } from "@fiestaboard/ui";

import { DevicePreview } from "@/components/device-preview";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { resolveCode62Glyph } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, Code62Glyph } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";
import type { LastKnownBoard } from "@/lib/pwa/last-known-board";

/** "2:14 PM" today; "Nov 12, 2:14 PM" on another day. */
export function formatLastConnected(at: number, now: number = Date.now(), locale?: string): string {
  const then = new Date(at);
  const sameDay = new Date(now).toDateString() === then.toDateString();
  return new Intl.DateTimeFormat(
    locale,
    sameDay
      ? { hour: "numeric", minute: "2-digit" }
      : { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" },
  ).format(then);
}

/**
 * The last frame this device saw on a board, drawn as that board, labelled
 * as possibly out of date (07 `59:69165`: "Last known · Lobby wall", "Last
 * connected 2:14 PM · may be out of date"). Static: nothing animates, and
 * nothing on it can be acted on, because the hub isn't answering.
 */
export function LastKnownBoardCard({ record }: { record: LastKnownBoard }) {
  const t = useTranslations("offline");
  const board = record.board;
  const name = board?.name ?? null;
  const deviceType = (board?.device_type ?? undefined) as BoardInstance["device_type"] | undefined;
  return (
    <Card data-testid="last-known-board" className="w-full text-left">
      <CardHeader>
        <Flex align="center" gap="2" wrap>
          <CardTitle className="text-sm">{name ? t("lastKnownTitle", { board: name }) : t("lastKnown")}</CardTitle>
          <Badge variant="outline">{t("lastKnownAt", { time: formatLastConnected(record.savedAt) })}</Badge>
        </Flex>
      </CardHeader>
      <CardContent>
        <DevicePreview
          model={resolveBoardModel(board as Parameters<typeof resolveBoardModel>[0])}
          ledLayout={board?.led_layout as BoardInstance["led_layout"]}
          message={record.message}
          cells={record.cells as BoardCellGrid | undefined}
          size="sm"
        >
          <ScaledBoardDisplay
            isStatic
            message={record.message}
            size="sm"
            boardType={(board?.board_color ?? undefined) as BoardInstance["board_color"] | undefined}
            deviceType={deviceType}
            notesWide={board?.notes_wide ?? undefined}
            notesTall={board?.notes_tall ?? undefined}
            gridRows={board?.grid_rows ?? record.rows}
            gridCols={board?.grid_cols ?? record.cols}
            code62Glyph={resolveCode62Glyph(deviceType, (board?.code62_glyph ?? undefined) as Code62Glyph | undefined)}
          />
        </DevicePreview>
      </CardContent>
    </Card>
  );
}
