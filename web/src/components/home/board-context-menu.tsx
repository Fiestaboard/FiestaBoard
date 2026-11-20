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
  ListItem,
  ListRow,
  ListRowGroup,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@fiestaboard/ui";
import { Copy, FileText, LayoutGrid, MoreHorizontal, Pause, PencilLine, Play, RefreshCw } from "lucide-react";
import { type ReactNode, useState } from "react";

import Link from "@/components/smart-link";
import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { useTranslations } from "@/i18n/translations";

export interface BoardActions {
  /** The display's name: the menu's label and the Pause item. */
  boardName: string;
  /** "<page> · <mode>", the touch sheet's second line (07a `310:33402`). */
  summary?: string;
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
  sendsDisabled?: boolean;
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
      <DropdownMenuItem onClick={actions.onChangePage} disabled={actions.sendsDisabled}>
        <LayoutGrid aria-hidden="true" />
        {t("changePage")}
        <DropdownMenuShortcut>P</DropdownMenuShortcut>
      </DropdownMenuItem>
      <DropdownMenuItem onClick={actions.onCompose} disabled={actions.sendsDisabled}>
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
 * The same items as a bottom sheet, for a coarse pointer (07a `310:33402`,
 * BB-A-5): the display over "<page> · <mode>", then 48 px rows. No shortcut
 * letters — a phone has no keyboard to press them on. Each row closes the
 * sheet before it acts.
 */
function BoardActionsSheet({
  actions,
  open,
  onOpenChange,
}: {
  actions: BoardActions;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("home.contextMenu");
  const run = (action: () => void) => () => {
    onOpenChange(false);
    action();
  };
  const row = (key: string, icon: ReactNode, title: string, onClick: () => void, disabled?: boolean) => (
    <ListItem key={key}>
      <ListRow
        leading={icon}
        title={title}
        render={<button type="button" onClick={run(onClick)} disabled={disabled} />}
      />
    </ListItem>
  );
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" grabber>
        <SheetHeader className="pe-12 text-start">
          <SheetTitle>{actions.boardName}</SheetTitle>
          {actions.summary ? <SheetDescription>{actions.summary}</SheetDescription> : null}
        </SheetHeader>
        <ListRowGroup variant="plain" className="pb-2">
          {!actions.sendsDisabled &&
            row("change", <LayoutGrid aria-hidden="true" />, t("changePage"), actions.onChangePage)}
          {!actions.sendsDisabled && row("compose", <PencilLine aria-hidden="true" />, t("compose"), actions.onCompose)}
          {actions.editHref && (
            <ListItem key="edit">
              <ListRow
                leading={<FileText aria-hidden="true" />}
                title={t("editPage")}
                render={<Link href={actions.editHref} onClick={() => onOpenChange(false)} />}
              />
            </ListItem>
          )}
          {actions.onCopyText && row("copy", <Copy aria-hidden="true" />, t("copyText"), actions.onCopyText)}
          {row("refresh", <RefreshCw aria-hidden="true" />, t("refresh"), actions.onRefresh, actions.busy)}
          {actions.onTogglePause &&
            row(
              "pause",
              actions.paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />,
              actions.paused ? t("resume", { board: actions.boardName }) : t("pause", { board: actions.boardName }),
              actions.onTogglePause,
              actions.busy,
            )}
        </ListRowGroup>
      </SheetContent>
    </Sheet>
  );
}

/**
 * The board context menu (07a §6, WEB-18): right-click, Shift+F10 / the Menu
 * key and a 500 ms long-press open it on the board itself, through FiestaUI's
 * `DropdownMenu trigger="context"` (1.8a). A ⋯ button in the card header
 * appears on card hover or focus (always on touch) and opens the same items,
 * so the menu is never the only way in. Everywhere else the browser keeps
 * its own menu.
 */
export function BoardContextMenu({ actions, children }: { actions: BoardActions; children: ReactNode }) {
  // On a coarse pointer the long-press opens the bottom sheet instead of a
  // menu anchored to the finger (BB-A-5).
  const coarse = useCoarsePointer();
  const [sheetOpen, setSheetOpen] = useState(false);
  return (
    <Box>
      <DropdownMenu
        trigger="context"
        {...(coarse
          ? {
              open: false,
              onOpenChange: (next: boolean) => {
                if (next) setSheetOpen(true);
              },
            }
          : {})}
      >
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
      {coarse && <BoardActionsSheet actions={actions} open={sheetOpen} onOpenChange={setSheetOpen} />}
    </Box>
  );
}

/** The same actions in the card header, clear of BoardViewport's controls. */
export function BoardActionsMenu({ actions }: { actions: BoardActions }) {
  const t = useTranslations("home.contextMenu");
  const coarse = useCoarsePointer();
  const [sheetOpen, setSheetOpen] = useState(false);
  const button = (
    <Button
      variant="secondary"
      size="icon"
      aria-label={t("moreActions", { board: actions.boardName })}
      className="size-9 shrink-0 opacity-0 shadow-sm transition-opacity group-hover/home-card:opacity-100 group-focus-within/home-card:opacity-100 focus-visible:opacity-100 data-[popup-open]:opacity-100 pointer-coarse:opacity-100"
      {...(coarse ? { onClick: () => setSheetOpen(true), "aria-haspopup": "dialog" as const } : {})}
    >
      <MoreHorizontal className="size-4" aria-hidden="true" />
    </Button>
  );
  if (coarse) {
    return (
      <>
        {button}
        <BoardActionsSheet actions={actions} open={sheetOpen} onOpenChange={setSheetOpen} />
      </>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{button}</DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <BoardMenuItems actions={actions} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
