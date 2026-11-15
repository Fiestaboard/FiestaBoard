"use client";

import {
  Box,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@fiestaboard/ui";
import { Copy, FileText, LayoutGrid, MoreHorizontal, Pause, PencilLine, Play, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import Link from "@/components/smart-link";
import { useTranslations } from "@/i18n/translations";

export interface BoardActions {
  /** The display's name: the menu's label and the Pause item. */
  boardName: string;
  onChangePage: () => void;
  onCompose: () => void;
  /** The editor for the page on the board; null when there is none (a composed message, a gap). */
  editHref: string | null;
  /** Null when the board's text is unknown. */
  onCopyText: (() => void) | null;
  onRefresh: () => void;
  paused: boolean;
  onTogglePause: (() => void) | null;
  busy?: boolean;
}

/**
 * 07a `302:2333` items: Change Page… (P) · Compose a message… (C) · Edit page
 * (E) · Copy as text · Refresh board │ Pause <display> (neutral, not
 * destructive: it is reversible from the Paused banner).
 */
function BoardMenuItems({ actions }: { actions: BoardActions }) {
  const t = useTranslations("home.contextMenu");
  return (
    <>
      <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{actions.boardName}</DropdownMenuLabel>
      <DropdownMenuItem onClick={actions.onChangePage}>
        <LayoutGrid aria-hidden="true" />
        {t("changePage")}
        <DropdownMenuShortcut>P</DropdownMenuShortcut>
      </DropdownMenuItem>
      <DropdownMenuItem onClick={actions.onCompose}>
        <PencilLine aria-hidden="true" />
        {t("compose")}
        <DropdownMenuShortcut>C</DropdownMenuShortcut>
      </DropdownMenuItem>
      {actions.editHref && (
        <DropdownMenuItem render={<Link href={actions.editHref} />}>
          <FileText aria-hidden="true" />
          {t("editPage")}
          <DropdownMenuShortcut>E</DropdownMenuShortcut>
        </DropdownMenuItem>
      )}
      {actions.onCopyText && (
        <DropdownMenuItem onClick={actions.onCopyText}>
          <Copy aria-hidden="true" />
          {t("copyText")}
        </DropdownMenuItem>
      )}
      <DropdownMenuItem onClick={actions.onRefresh} disabled={actions.busy}>
        <RefreshCw aria-hidden="true" />
        {t("refresh")}
      </DropdownMenuItem>
      {actions.onTogglePause && (
        <>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={actions.onTogglePause} disabled={actions.busy}>
            {actions.paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
            {actions.paused ? t("resume", { board: actions.boardName }) : t("pause", { board: actions.boardName })}
          </DropdownMenuItem>
        </>
      )}
    </>
  );
}

/**
 * The board context menu (07a §6, WEB-18): right-click, Shift+F10 / the Menu
 * key and a 500 ms long-press open it on the board itself, through FiestaUI's
 * `DropdownMenu trigger="context"` (1.8a). A ⋯ button that appears on board
 * hover or focus (always on touch) opens the same items, so the menu is never
 * the only way in. Everywhere else the browser keeps its own menu.
 */
export function BoardContextMenu({ actions, children }: { actions: BoardActions; children: ReactNode }) {
  const t = useTranslations("home.contextMenu");
  return (
    <Box className="group/board relative">
      <DropdownMenu trigger="context">
        <DropdownMenuTrigger
          render={
            <Box
              tabIndex={0}
              role="group"
              aria-label={actions.boardName}
              aria-keyshortcuts="Shift+F10"
              data-testid="home-board"
              className="rounded-xl outline-none [-webkit-touch-callout:none] focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
          }
        >
          {children}
        </DropdownMenuTrigger>
        <DropdownMenuContent className="min-w-56">
          <BoardMenuItems actions={actions} />
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="secondary"
            size="icon"
            aria-label={t("moreActions", { board: actions.boardName })}
            className="absolute end-3 top-3 size-9 opacity-0 shadow-sm transition-opacity group-hover/board:opacity-100 group-focus-within/board:opacity-100 focus-visible:opacity-100 data-[popup-open]:opacity-100 pointer-coarse:opacity-100"
          >
            <MoreHorizontal className="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          <BoardMenuItems actions={actions} />
        </DropdownMenuContent>
      </DropdownMenu>
    </Box>
  );
}
