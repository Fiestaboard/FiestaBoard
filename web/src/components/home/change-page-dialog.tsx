"use client";

import {
  Badge,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  ListRow,
  SegmentedControl,
  SegmentedControlItem,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, FileText, GalleryHorizontalEnd } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { SilenceNotice } from "@/components/silence-notice";
import { useCollections, usePagePreview, usePages } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useLocale, useTranslations } from "@/i18n/translations";
import type { BoardInstance, Collection, Page, SetTemporaryOverrideRequest } from "@/lib/api";
import { api, isCollectionId } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

import { defaultDurationChoice, DurationStep } from "./duration-step";
import { boardGeometry, deviceFamilyLabel, HomeBoard } from "./home-board";
import { type DurationChoice, durationMinutes, formatClock, type ScheduleNextChange } from "./home-status";
import { nudgeDisplay, useRefreshHomeStatus } from "./use-home-data";
import { PHONE_QUERY, useMediaQuery } from "./use-media-query";

export interface ChangePageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The display to change; undefined → the primary (a one-board install). */
  board: BoardInstance | undefined;
  /** Its name, when `board` is unknown. */
  boardName?: string;
  isPrimary: boolean;
  scheduleEnabled: boolean;
  /** The page or collection on the display now ("Showing now"). */
  currentPageId?: string | null;
  /** Manual Mode: the page that comes back after a timed hold. */
  manualPageName?: string | null;
  /** The Override running on the display now; the new hold replaces it. */
  overrideName?: string | null;
  /** H2's next Schedule change on the display. */
  nextChange: ScheduleNextChange | null;
  /** Set while the display is silenced: Show now wakes it. */
  silence?: { until: string | null } | null;
  /** Open with this page already picked (the context menu, a page's "Show on…"). */
  initialPageId?: string | null;
  /** Injectable clock, for tests. */
  now?: () => Date;
}

type Kind = "pages" | "collections";

interface Choice {
  id: string;
  name: string;
  description?: string;
  isCollection: boolean;
}

/**
 * Change Page (07a §5, `310:27278`; phone `318:42097` → `310:30774`).
 *
 * One dialog replaces ForceSetDialog, the old page sheet and the "Override
 * temporarily / Turn off schedule" choice: pick (search · Pages / Collections ·
 * rows) → the bare "Preview · Not sent yet" row and board (DD-W15) → the shared
 * duration step → Show now. Below 640 px it is a bottom sheet in two steps.
 */
export function ChangePageDialog({
  open,
  onOpenChange,
  board,
  boardName,
  isPrimary,
  scheduleEnabled,
  currentPageId = null,
  manualPageName = null,
  overrideName = null,
  nextChange,
  silence = null,
  initialPageId = null,
  now = () => new Date(),
}: ChangePageDialogProps) {
  const t = useTranslations("changePage");
  const isPhone = useMediaQuery(PHONE_QUERY);
  const refresh = useRefreshHomeStatus();
  const displayName = board?.name ?? boardName ?? "";

  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind>("pages");
  const [selectedId, setSelectedId] = useState<string | null>(initialPageId);
  const [step, setStep] = useState<"pick" | "duration">(initialPageId ? "duration" : "pick");
  // null follows the default (07a preselects the next change, which may load
  // after the dialog opens); a tap on a chip pins the choice.
  const [choice, setChoice] = useState<DurationChoice | null>(null);

  // Reset each time it opens, during render so the first frame is already
  // clean (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([open]) && open) {
    setQuery("");
    setKind(initialPageId && isCollectionId(initialPageId) ? "collections" : "pages");
    setSelectedId(initialPageId);
    setStep(initialPageId ? "duration" : "pick");
    setChoice(null);
  }

  const { data: pagesData } = usePages();
  const { data: collectionsData } = useCollections();

  const pages = useMemo(() => {
    const all: Page[] = pagesData?.pages ?? [];
    return board ? all.filter((p) => pagesCompatibleWithBoard(p, board)) : all;
  }, [pagesData, board]);
  // A collection with no member that fits this display could only show
  // nothing here, and the override route does no size check (review S5).
  const collections: Collection[] = useMemo(() => {
    const all = collectionsData?.collections ?? [];
    if (!board) return all;
    const fitting = new Set(pages.map((p) => p.id));
    return all.filter((c) => c.page_ids.some((id) => fitting.has(id)));
  }, [collectionsData, board, pages]);

  // 07a's row meta: "Flagship · Schedule, 9:00 PM" / "Flagship · not in the
  // Schedule". From this display's schedule entries, today's resolved start.
  const locale = useLocale();
  const { data: schedulesData } = useQuery({
    queryKey: ["schedules", "list", board?.id ?? "primary"],
    queryFn: () => api.getSchedules(board?.id),
    enabled: open,
    staleTime: 30_000,
  });
  const scheduledAt = useMemo(() => {
    const at = new Map<string, string>();
    for (const entry of schedulesData?.schedules ?? []) {
      if (!entry.enabled || at.has(entry.page_id)) continue;
      const hhmm = entry.resolved_start_time ?? entry.start_time;
      const match = /^(\d{1,2}):(\d{2})/.exec(hhmm ?? "");
      if (!match) continue;
      const today = new Date();
      today.setHours(Number(match[1]), Number(match[2]), 0, 0);
      at.set(entry.page_id, formatClock(today, locale));
    }
    return at;
  }, [schedulesData, locale]);

  const choices: Choice[] = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const scheduleMeta = (id: string) => {
      const time = scheduledAt.get(id);
      return time ? t("inSchedule", { time }) : t("notInSchedule");
    };
    const list: Choice[] =
      kind === "pages"
        ? pages.map((p) => ({
            id: p.id,
            name: p.name,
            description: [deviceFamilyLabel(p.device_type), scheduleMeta(p.id)].filter(Boolean).join(" · "),
            isCollection: false,
          }))
        : collections.map((c) => ({
            id: c.id,
            name: c.name,
            description: [t("collectionPages", { count: c.page_ids.length }), scheduleMeta(c.id)].join(" · "),
            isCollection: true,
          }));
    return needle ? list.filter((c) => c.name.toLowerCase().includes(needle)) : list;
  }, [kind, pages, collections, query, t, scheduledAt]);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    const page = pagesData?.pages?.find((p) => p.id === selectedId);
    if (page) return { id: page.id, name: page.name, isCollection: false };
    const collection = collections.find((c) => c.id === selectedId);
    return collection ? { id: collection.id, name: collection.name, isCollection: true } : null;
  }, [selectedId, pagesData, collections]);

  // Never carry a chip that is no longer offered: "next-change" with no next
  // change would send no duration, an indefinite hold nobody chose (review
  // M2). Fall back to the explicit default instead.
  const effectiveChoice: DurationChoice =
    choice === null || (choice === "next-change" && !nextChange)
      ? defaultDurationChoice(nextChange, { scheduleEnabled })
      : choice;

  // "Until I cancel" in Manual Mode pins the page (Jev, p = 0.81).
  const pins = !scheduleEnabled && effectiveChoice === "until-cancel";
  const overrideRunning = overrideName != null;

  const submit = useMutation({
    mutationFn: async (picked: { id: string; name: string }) => {
      if (pins) {
        // The engine applies an override before the pinned page, and the PUT
        // does not clear one: drop this display's override FIRST (a "page"
        // revert writes active_page_id on clear, and the pin must win).
        if (overrideRunning) await api.clearTemporaryOverride(board?.id);
        const result = await api.setActivePage(picked.id, board?.id, { overrideSilence: true });
        return { picked, pinned: true, paused: result.paused === true, notSent: !!result.error };
      }
      const minutes = durationMinutes(effectiveChoice, nextChange, now());
      const request: SetTemporaryOverrideRequest = {
        ...(board?.id ? { board_id: board.id } : {}),
        page_id: picked.id,
        ...(minutes !== undefined ? { duration_minutes: minutes } : {}),
        revert_mode: "schedule",
      };
      await api.setTemporaryOverride(request);
      return { picked, pinned: false, paused: board?.paused === true, notSent: false };
    },
    onSuccess: ({ picked, pinned, paused, notSent }) => {
      refresh();
      // A pin is sent by its own PUT; an override waits for the display
      // loop's next pass, so nudge that one display (any extra pass after a
      // pin would spend a note array's 15 s send window on a repaint).
      if (!pinned) nudgeDisplay(board?.id);
      if (notSent) toast.error(t("toastNotSent", { board: displayName }));
      else if (paused) toast.info(t("toastPaused", { page: picked.name, board: displayName }));
      else toast.success(t("toastShown", { page: picked.name, board: displayName }));
      onOpenChange(false);
    },
    onError: () => {
      toast.error(t("toastError"));
    },
  });

  const pick = (id: string) => {
    setSelectedId(id);
    if (isPhone) setStep("duration");
  };

  const search = (
    <Flex gap="2" align="center" wrap>
      <Input
        type="search"
        aria-label={t("search")}
        placeholder={t("search")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="min-w-0 flex-[1_1_12rem]"
      />
      <SegmentedControl
        aria-label={t("kinds")}
        value={kind}
        onValueChange={(v) => setKind(v as Kind)}
        className={isPhone ? "w-full" : undefined}
        layout={isPhone ? "grid" : undefined}
        // 07a's 44 px phone segments (FiestaUI #385 touch size axis).
        size={isPhone ? "touch" : undefined}
      >
        <SegmentedControlItem value="pages">{t("pages")}</SegmentedControlItem>
        <SegmentedControlItem value="collections">{t("collections")}</SegmentedControlItem>
      </SegmentedControl>
    </Flex>
  );

  const rows =
    choices.length === 0 ? (
      <Text size="sm" tone="muted" className="py-4 text-center">
        {query.trim() ? t("empty", { query: query.trim() }) : t("emptyNone", { board: displayName })}
      </Text>
    ) : (
      // Button rows, not a ListRowGroup: the group is a role="list" of <li>
      // rows, and a row rendered as a <button> would leave the list with no
      // list items (axe aria-required-children). FiestaUI gap, see DD-W47.
      <Stack gap="0" className="divide-y divide-border">
        {choices.map((c) => {
          const isCurrent = c.id === currentPageId;
          const isSelected = !isPhone && c.id === selectedId;
          const description = [c.description, isCurrent ? t("showingNow") : null].filter(Boolean).join(" · ");
          const Icon = c.isCollection ? GalleryHorizontalEnd : FileText;
          return (
            <ListRow
              key={c.id}
              render={<button type="button" aria-pressed={isPhone ? undefined : isSelected} />}
              size={isPhone ? "touch" : "default"}
              onClick={() => pick(c.id)}
              leading={<Icon className="size-4 text-muted-foreground" aria-hidden="true" />}
              title={c.name}
              description={description || undefined}
              trailing={
                isPhone ? (
                  <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
                ) : isSelected ? (
                  <Check className="size-4" aria-hidden="true" />
                ) : null
              }
              className={isSelected ? "rounded-lg bg-tint-selected ring-1 ring-foreground/70" : undefined}
            />
          );
        })}
      </Stack>
    );

  const durationAndPreview = selected ? (
    <Stack gap="4">
      <PreviewRow
        pageId={selected.isCollection ? null : selected.id}
        label={t("notSentYet", { page: selected.name, board: displayName })}
        previewBadge={t("preview")}
        board={board}
      />
      <DurationStep
        name={selected.name}
        value={effectiveChoice}
        onValueChange={setChoice}
        nextChange={nextChange}
        nextPageName={nextPageNameFor(nextChange, pagesData?.pages, collections)}
        scheduleEnabled={scheduleEnabled}
        manualPageName={manualPageName}
        untilCancelPins
        replacesName={overrideName}
        layout={isPhone ? "grid" : "row"}
        now={now()}
      />
    </Stack>
  ) : null;

  const silenceNotice = silence ? (
    <SilenceNotice
      variant="warning"
      until={silence.until}
      description={t("silenceWarning", { board: displayName })}
      data-testid="change-page-silence"
    />
  ) : null;

  const showNow = (
    <Button
      onClick={() => selected && submit.mutate(selected)}
      disabled={!selected || submit.isPending}
      size={isPhone ? "lg" : "default"}
      className={isPhone ? "w-full" : undefined}
    >
      {submit.isPending ? t("showing") : t("showNow")}
    </Button>
  );

  if (isPhone) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" grabber className="max-h-[92dvh]">
          {step === "pick" || !selected ? (
            <>
              <SheetHeader className="pe-12 text-start">
                <SheetTitle>{t("title")}</SheetTitle>
                <SheetDescription>{t("stepOne", { board: displayName })}</SheetDescription>
              </SheetHeader>
              <Stack gap="3" className="pb-4">
                {search}
                <Text as="p" size="xs" tone="muted" className="font-mono uppercase tracking-wide">
                  {t("forBoard", { board: displayName })}
                </Text>
                {rows}
              </Stack>
            </>
          ) : (
            <>
              <SheetHeader className="pe-12 text-start">
                <Flex align="start" gap="2">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setStep("pick")}
                    aria-label={t("back")}
                    className="-ms-2 size-11 shrink-0"
                  >
                    <ChevronLeft className="size-5" aria-hidden="true" />
                  </Button>
                  <Stack gap="1" className="min-w-0 text-start">
                    <SheetTitle>{selected.name}</SheetTitle>
                    <SheetDescription>{t("stepTwo", { board: displayName })}</SheetDescription>
                  </Stack>
                </Flex>
              </SheetHeader>
              <Stack gap="4" className="pb-4">
                {durationAndPreview}
                {silenceNotice}
              </Stack>
              <SheetFooter>{showNow}</SheetFooter>
            </>
          )}
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description", { board: displayName })}</DialogDescription>
        </DialogHeader>
        <Stack gap="4">
          {search}
          <Box className="max-h-64 overflow-y-auto">{rows}</Box>
          {durationAndPreview}
          {silenceNotice}
        </Stack>
        <DialogFooter className="sticky bottom-0 -mx-6 -mb-6 bg-background px-6 pb-6 pt-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={submit.isPending}>
            {t("cancel")}
          </Button>
          {showNow}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function nextPageNameFor(
  next: ScheduleNextChange | null,
  pages: Page[] | undefined,
  collections: Collection[],
): string | null {
  if (!next?.pageId) return null;
  return pages?.find((p) => p.id === next.pageId)?.name ?? collections.find((c) => c.id === next.pageId)?.name ?? null;
}

/**
 * 07a's bare preview row (DD-W15): outline "Preview" badge · "Not sent yet ·
 * <page> on <display>" · the board at Tile sm. Not a NowShowingCard
 * `state="preview"`: 07a draws no card here.
 */
function PreviewRow({
  pageId,
  label,
  previewBadge,
  board,
}: {
  pageId: string | null;
  label: string;
  previewBadge: string;
  board: BoardInstance | undefined;
}) {
  const { data } = usePagePreview(pageId, { enabled: !!pageId });
  return (
    <Stack gap="2">
      <Flex align="center" gap="2">
        <Badge variant="outline">{previewBadge}</Badge>
        <Text size="xs" tone="muted">
          {label}
        </Text>
      </Flex>
      {pageId && (
        <Flex justify="center" className="overflow-x-hidden">
          <HomeBoard
            board={board}
            geometry={boardGeometry(board)}
            message={data?.message ?? null}
            isLoading={!data}
            size="sm"
          />
        </Flex>
      )}
    </Stack>
  );
}
