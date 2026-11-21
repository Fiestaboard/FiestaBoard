"use client";

import {
  Badge,
  Box,
  Button,
  type DeviceModel,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Save } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { DevicePreview } from "@/components/device-preview";
import { HomeConnectionNotice } from "@/components/home/connection-notice";
import { defaultDurationChoice, DurationStep } from "@/components/home/duration-step";
import { type DurationChoice, durationMinutes, type ScheduleNextChange } from "@/components/home/home-status";
import { dismissOverrideUndo, nudgeDisplay, useRefreshHomeStatus } from "@/components/home/use-home-data";
import { PHONE_QUERY, useMediaQuery } from "@/components/home/use-media-query";
import { PlainTextEditor } from "@/components/plain-text-editor";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { SilenceNotice } from "@/components/silence-notice";
import Link from "@/components/smart-link";
import { queryKeys } from "@/hooks/use-board";
import { useCloseOnBack } from "@/hooks/use-close-on-back";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useHubConnection } from "@/hooks/use-hub-connection";
import { useTranslations } from "@/i18n/translations";
import type { BoardLedLayout, DeviceType, PageCreate, SetTemporaryOverrideRequest } from "@/lib/api";
import { api } from "@/lib/api";
import { resolveDimensions } from "@/lib/board-dimensions";

const PREVIEW_DEBOUNCE_MS = 250;

interface ComposePageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Geometry of the board this message will be SENT to — which is the primary
   * board, not necessarily the one selected in the sidebar. The caller resolves
   * that; the dialog just previews and validates against what it is given.
   */
  deviceType?: DeviceType;
  notesWide?: number;
  notesTall?: number;
  /** A panel board's character grid (only used when deviceType === "panel"). */
  gridRows?: number | null;
  gridCols?: number | null;
  boardColor?: "black" | "white";
  code62Glyph?: "degree" | "heart";
  /** The destination display's name, for the description and the toast. */
  targetBoardLabel?: string;
  /**
   * The display to hold the message on (H1: every display has its own
   * override); omitted → the primary.
   */
  sendBoardId?: string;
  /** "Show on": pick the destination display (07a `310:20283`). */
  showOn?: { value: string; onValueChange: (id: string) => void; options: { id: string; label: string }[] };
  /** The destination is in Schedule Mode (the outcome line says what resumes). */
  scheduleEnabled?: boolean;
  /** H2's next Schedule change on the destination, for the "Until <time>" chip. */
  nextChange?: ScheduleNextChange | null;
  /** The page the Schedule resumes with after it. */
  nextPageName?: string | null;
  /** The destination draws capitals only (a split-flap board): the helper says so. */
  showsCapitals?: boolean;
  /** The destination board's device model: an LED board previews as its LED matrix. */
  model?: DeviceModel | null;
  /** The destination board's LED layout choices (`led_layout`), drawn with the model. */
  ledLayout?: BoardLedLayout | null;
  /** The destination (primary) board's id; omitted → the primary board. */
  targetBoardId?: string;
  /**
   * The destination board's silence, while it is silenced (#1943, #1944):
   * when it ends, and whether its schedule holds messages until then. Null or
   * omitted when the board is not silenced — the dialog is then unchanged.
   */
  silence?: { until: string | null; holds: boolean } | null;
}

/**
 * Compose a message (07a §4): Show on · Message · Preview · the shared
 * duration step · Show now. One of CANON's two verbs; it ends in the same
 * DurationChipGroup as Change Page, and the result is the Override state.
 *
 * A one-off message, sent without saving it (issue #1787).
 *
 * The send goes through the temporary-override machinery rather than a bare
 * "push these characters" call: that gives the message a defined lifetime, a
 * cancel affordance (the existing override badge on Home), and survival across
 * a restart. A naive send would instead live until some unrelated re-render of
 * the display loop happened to evict it.
 *
 * Saving is genuinely optional — Send never creates a page, and Save as Page
 * never sends.
 */
export function ComposePageDialog({
  open,
  onOpenChange,
  deviceType = "flagship",
  notesWide = 1,
  notesTall = 1,
  gridRows = null,
  gridCols = null,
  boardColor = "black",
  code62Glyph,
  targetBoardLabel,
  sendBoardId,
  showOn,
  scheduleEnabled = false,
  nextChange = null,
  nextPageName = null,
  showsCapitals = false,
  model = null,
  ledLayout = null,
  targetBoardId,
  silence = null,
}: ComposePageDialogProps) {
  const t = useTranslations("composeDialog");
  const isPhone = useMediaQuery(PHONE_QUERY);
  // Back closes the sheet and stays on the screen (BB-A-12).
  useCloseOnBack(open, () => onOpenChange(false));
  const tb = useTranslations("home.banners");
  const connection = useHubConnection();
  const sendsDisabled = !connection.deviceOnline || !connection.hubReachable;
  const queryClient = useQueryClient();
  const messageId = useId();
  const pageNameId = useId();
  const showOnId = useId();
  const refresh = useRefreshHomeStatus();
  const boardLabel = targetBoardLabel ?? "";

  const [text, setText] = useState("");
  const [debouncedText, setDebouncedText] = useState("");
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [pageName, setPageName] = useState("");
  // null follows the default (07a preselects the next change, which may load
  // after the dialog opens); a tap on a chip pins the choice.
  const [choice, setChoice] = useState<DurationChoice | null>(null);

  // Reset during render (not in an effect) so the first painted frame of a
  // reopened dialog is already empty — react-hooks/set-state-in-effect,
  // same pattern as the Change Page dialog (issue #1568).
  if (useDepsChanged([open]) && open) {
    setText("");
    setDebouncedText("");
    setShowSaveForm(false);
    setPageName("");
    setChoice(null);
  }
  // Show on picked another display: its chips differ, so start from its
  // default rather than carry the old display's choice over.
  if (useDepsChanged([sendBoardId]) && open) {
    setChoice(null);
  }
  // Never carry a chip that is no longer offered (the new display's next
  // change still loading, or gone): "next-change" with no next change would
  // send no duration, an indefinite hold nobody chose (review M2).
  const effectiveChoice: DurationChoice =
    choice === null || (choice === "next-change" && !nextChange)
      ? defaultDurationChoice(nextChange, { scheduleEnabled })
      : choice;

  const dims = useMemo(
    () => resolveDimensions(deviceType, notesWide, notesTall, gridRows, gridCols),
    [deviceType, notesWide, notesTall, gridRows, gridCols],
  );
  // The geometry fields a request needs beyond device_type: notes for a note
  // array, the character grid for a panel (the server rejects a panel without
  // it), nothing for a flagship or Note.
  const geometryFields = useMemo(() => {
    if (deviceType === "note_array") return { notes_wide: notesWide, notes_tall: notesTall };
    if (deviceType === "panel") return { grid_rows: dims.rows, grid_cols: dims.cols };
    return {};
  }, [deviceType, notesWide, notesTall, dims.rows, dims.cols]);
  const panelGrid = deviceType === "panel" ? { rows: dims.rows, cols: dims.cols } : null;

  const lines = useMemo(() => (text === "" ? [] : text.split("\n")), [text]);
  const isEmpty = lines.every((line) => line.trim() === "");
  const isOverLimit = lines.length > dims.rows;
  const canSend = !isEmpty && !isOverLimit;

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedText(text), PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [text]);

  const previewLines = useMemo(() => (debouncedText === "" ? [] : debouncedText.split("\n")), [debouncedText]);

  const { data: preview } = useQuery({
    // The note-array geometry is part of the key and the request: without it
    // the server previews every array as one 3x15 Note (issue #2032).
    queryKey: ["composePreview", previewLines, deviceType, notesWide, notesTall, gridRows, gridCols],
    queryFn: () => api.renderTemplate(previewLines, undefined, deviceType, notesWide, notesTall, panelGrid),
    enabled: open && previewLines.length > 0,
    staleTime: 10_000,
    // Hold the last preview while the next renders (BB-A-2): dropping to blank
    // between keystrokes would replay the flap cascade from blank each time.
    placeholderData: keepPreviousData,
  });
  // A cleared message disables the query; the held placeholder must not outlive it.
  const previewMessage = previewLines.length > 0 ? (preview?.rendered ?? "") : "";

  const sendMutation = useMutation({
    mutationFn: ({ request }: { request: SetTemporaryOverrideRequest; boardLabel: string }) => {
      dismissOverrideUndo(request.board_id);
      return api.setTemporaryOverride(request);
    },
    onSuccess: (_result, { request, boardLabel: submittedLabel }) => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["temporaryOverride"] });
      refresh();
      // Completion belongs to the submitted display even if Show on changes
      // while the request is in flight (review R1).
      nudgeDisplay(request.board_id);
      toast.success(submittedLabel ? t("toastSent", { board: submittedLabel }) : t("toastSentNoBoard"));
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastSendError"));
    },
  });

  // Hold until silence ends (#1944): POST /v1/boards/{board}/message answers
  // 202 `held: true` when the board's schedule holds messages. Unlike Send,
  // this never wakes the board.
  const holdMutation = useMutation({
    mutationFn: (holdLines: string[]) => api.sendBoardMessage(targetBoardId, { lines: holdLines }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.silenceStatus() });
      if (result.held) {
        toast.success(silence?.until ? t("toastHeld", { time: silence.until }) : t("toastHeldNoTime"));
      } else {
        // Silence ended between opening the dialog and pressing Hold.
        toast.success(boardLabel ? t("toastSent", { board: boardLabel }) : t("toastSentNoBoard"));
      }
      onOpenChange(false);
    },
    onError: () => {
      toast.error(t("toastHoldError"));
    },
  });

  const saveMutation = useMutation({
    mutationFn: (page: PageCreate) => api.createPage(page),
    onSuccess: (_result, page) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pages });
      toast.success(t("toastSaved", { pageName: page.name }));
      setShowSaveForm(false);
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastSaveError"));
    },
  });

  const handleSend = useCallback(() => {
    if (!canSend || sendsDisabled) return;
    // The shared duration step: a timed chip holds it that long, "Until I
    // cancel" sends no duration_minutes, so it stays until it is cancelled.
    const minutes = durationMinutes(effectiveChoice, nextChange, new Date());
    sendMutation.mutate({
      boardLabel,
      request: {
        ...(sendBoardId ? { board_id: sendBoardId } : {}),
        template: lines,
        device_type: deviceType,
        ...(minutes !== undefined ? { duration_minutes: minutes } : {}),
        ...geometryFields,
      },
    });
  }, [
    canSend,
    sendsDisabled,
    lines,
    deviceType,
    geometryFields,
    sendMutation,
    effectiveChoice,
    nextChange,
    sendBoardId,
    boardLabel,
  ]);

  const handleHold = useCallback(() => {
    if (!canSend || sendsDisabled) return;
    holdMutation.mutate(lines);
  }, [canSend, sendsDisabled, lines, holdMutation]);

  const handleSave = useCallback(() => {
    if (isEmpty || pageName.trim() === "") return;
    saveMutation.mutate({
      name: pageName.trim(),
      type: "template",
      device_type: deviceType,
      template: lines,
      ...geometryFields,
    });
  }, [isEmpty, pageName, lines, deviceType, geometryFields, saveMutation]);

  // 07a `310:25531`: on a phone Compose is a bottom sheet that scrolls as
  // one, so the duration choice is part of the flow, not below an inner
  // scroller's fold (BB-A-3). Wider screens keep the dialog.
  const buttonSize = isPhone ? ("touch" as const) : undefined;
  // BB-FH-2 (07a "Typing"): open with the caret in Message. The default lands
  // on the first control, the Show on select, where typing typeahead-picks
  // another display.
  const focusMessage = () => document.getElementById(messageId);
  const header = {
    title: t("title"),
    description: boardLabel ? t("description", { board: boardLabel }) : t("descriptionNoBoard"),
  };
  const body = (
    <Stack gap="4" className={isPhone ? "pb-2" : "min-h-0 overflow-y-auto py-2"}>
      <HomeConnectionNotice composing />
      {showOn && (
        <Stack gap="2">
          <Label htmlFor={showOnId}>{t("showOn")}</Label>
          <Select value={showOn.value} onValueChange={(v) => showOn.onValueChange(String(v))}>
            <SelectTrigger id={showOnId}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {showOn.options.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Stack>
      )}

      {silence && (
        <SilenceNotice
          variant={silence.holds ? "info" : "warning"}
          until={silence.until}
          data-testid="compose-silence"
          description={
            silence.holds ? (
              t("silenceHold", { time: silence.until ?? "—" })
            ) : (
              <>
                {t("silenceNoHold")}{" "}
                <Link
                  href="/settings?section=scheduling#silence-schedule"
                  className="font-medium underline underline-offset-2 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {t("openSettings")}
                </Link>
              </>
            )
          }
        />
      )}

      <Stack gap="2">
        <Label htmlFor={messageId}>{t("messageLabel")}</Label>
        <PlainTextEditor
          id={messageId}
          value={text}
          onChange={setText}
          placeholder={t("messagePlaceholder")}
          boardLines={dims.rows}
          boardWidth={dims.cols}
          help={
            // 07a's one line: "3 of 6 lines · longest line 12 of 22
            // characters · board shows capitals".
            <Text size="xs" tone="muted" className="mt-1">
              {[
                t("countLines", { lines: lines.length, max: dims.rows }),
                t("countLongest", {
                  longest: lines.reduce((m, l) => Math.max(m, l.length), 0),
                  width: dims.cols,
                }),
                showsCapitals ? t("countCapitals") : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </Text>
          }
        />
        {isOverLimit && (
          <Text size="xs" className="text-warning font-medium" role="alert">
            {t("tooManyLines", { max: dims.rows })}
          </Text>
        )}
      </Stack>

      <Stack gap="2">
        {/* 07a's bare preview row (DD-W15): what WILL show, not sent yet. */}
        <Flex align="center" gap="2">
          <Badge variant="outline">{t("previewLabel")}</Badge>
          <Text size="xs" tone="muted">
            {boardLabel ? t("notSentYetOn", { board: boardLabel }) : t("notSentYet")}
          </Text>
        </Flex>
        {/* On a phone the preview runs edge to edge in the kit's phone-hero
            placement, so a Flagship shows whole without Fit/Actual (BB-A-3). */}
        <Box className={isPhone ? "-mx-4 min-w-0" : "contents"}>
          <DevicePreview model={model} ledLayout={ledLayout} message={previewMessage} size="sm">
            <ScaledBoardDisplay
              message={previewMessage}
              size={isPhone ? undefined : "sm"}
              layout={isPhone ? "phone-hero" : undefined}
              boardType={boardColor}
              deviceType={deviceType}
              notesWide={notesWide}
              notesTall={notesTall}
              gridRows={panelGrid?.rows}
              gridCols={panelGrid?.cols}
              code62Glyph={code62Glyph}
            />
          </DevicePreview>
        </Box>
      </Stack>

      <DurationStep
        value={effectiveChoice}
        onValueChange={setChoice}
        nextChange={nextChange}
        nextPageName={nextPageName}
        scheduleEnabled={scheduleEnabled}
        now={new Date()}
      />

      {showSaveForm && (
        <Stack gap="2">
          <Label htmlFor={pageNameId}>{t("pageNameLabel")}</Label>
          <Flex gap="2" align="center">
            <Input
              id={pageNameId}
              value={pageName}
              onChange={(e) => setPageName(e.target.value)}
              placeholder={t("pageNamePlaceholder")}
              autoFocus
            />
            <Button
              variant="outline"
              onClick={handleSave}
              disabled={isEmpty || pageName.trim() === "" || saveMutation.isPending}
            >
              {saveMutation.isPending ? t("saving") : t("save")}
            </Button>
          </Flex>
        </Stack>
      )}
    </Stack>
  );
  const actions = (
    <>
      <Button
        variant="ghost"
        size={buttonSize}
        onClick={() => onOpenChange(false)}
        disabled={sendMutation.isPending || holdMutation.isPending}
      >
        {t("cancel")}
      </Button>
      {!showSaveForm && (
        <Button variant="outline" size={buttonSize} onClick={() => setShowSaveForm(true)} disabled={isEmpty}>
          <Save className="mr-1.5 h-4 w-4" />
          {t("saveAsPage")}
        </Button>
      )}
      {/* During silence the send is named for what it does: it wakes the
              board (#949). With holds on, Hold is the primary action, last. */}
      <Button
        variant={silence?.holds ? "outline" : "default"}
        size={buttonSize}
        onClick={handleSend}
        disabled={sendsDisabled || !canSend || sendMutation.isPending || holdMutation.isPending}
        data-testid={silence ? "compose-send-anyway" : undefined}
      >
        {sendMutation.isPending ? t("sending") : t("send")}
      </Button>
      {silence?.holds && (
        <Button
          size={buttonSize}
          onClick={handleHold}
          disabled={sendsDisabled || !canSend || holdMutation.isPending || sendMutation.isPending}
          data-testid="compose-hold"
        >
          <Clock className="mr-1.5 h-4 w-4" />
          {holdMutation.isPending ? t("holding") : silence.until ? t("hold", { time: silence.until }) : t("holdNoTime")}
        </Button>
      )}
    </>
  );

  if (isPhone) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" grabber className="max-h-[92dvh]" initialFocus={focusMessage}>
          <SheetHeader className="pe-12 text-start">
            <SheetTitle>{header.title}</SheetTitle>
            <SheetDescription>{header.description}</SheetDescription>
          </SheetHeader>
          {body}
          {sendsDisabled && (
            <Text size="sm" tone="muted">
              {tb("sendReason")}
            </Text>
          )}
          {/* 07a `310:25531`: Show now comes last, after the duration
              choice, in the one scrolling flow — never pinned above it. */}
          <Stack gap="2" className="pb-2 [&>button]:w-full" data-slot="compose-actions">
            {actions}
          </Stack>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col overflow-hidden" initialFocus={focusMessage}>
        <DialogHeader className="shrink-0">
          <DialogTitle>{header.title}</DialogTitle>
          <DialogDescription>{header.description}</DialogDescription>
        </DialogHeader>

        {body}

        {sendsDisabled && (
          <Text size="sm" tone="muted">
            {tb("sendReason")}
          </Text>
        )}
        <DialogFooter className="shrink-0 flex-wrap pt-2">{actions}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
