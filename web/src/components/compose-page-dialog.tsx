"use client";

import {
  Badge,
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
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Save } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { DevicePreview } from "@/components/device-preview";
import { defaultDurationChoice, DurationStep } from "@/components/home/duration-step";
import { type DurationChoice, durationMinutes, type ScheduleNextChange } from "@/components/home/home-status";
import { useRefreshHomeStatus } from "@/components/home/use-home-data";
import { PlainTextEditor } from "@/components/plain-text-editor";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { SilenceNotice } from "@/components/silence-notice";
import Link from "@/components/smart-link";
import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
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
  model = null,
  ledLayout = null,
  targetBoardId,
  silence = null,
}: ComposePageDialogProps) {
  const t = useTranslations("composeDialog");
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
  const [choice, setChoice] = useState<DurationChoice>(() => defaultDurationChoice(nextChange, { scheduleEnabled }));

  // Reset during render (not in an effect) so the first painted frame of a
  // reopened dialog is already empty — react-hooks/set-state-in-effect,
  // same pattern as the Change Page dialog (issue #1568).
  if (useDepsChanged([open]) && open) {
    setText("");
    setDebouncedText("");
    setShowSaveForm(false);
    setPageName("");
    setChoice(defaultDurationChoice(nextChange, { scheduleEnabled }));
  }

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
  });

  const sendMutation = useMutation({
    mutationFn: (request: SetTemporaryOverrideRequest) => api.setTemporaryOverride(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["temporaryOverride"] });
      refresh();
      api.forceRefresh().catch(() => {});
      toast.success(boardLabel ? t("toastSent", { board: boardLabel }) : t("toastSentNoBoard"));
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
    if (!canSend) return;
    // The shared duration step: a timed chip holds it that long, "Until I
    // cancel" sends no duration_minutes, so it stays until it is cancelled.
    const minutes = durationMinutes(choice, nextChange, new Date());
    sendMutation.mutate({
      ...(sendBoardId ? { board_id: sendBoardId } : {}),
      template: lines,
      device_type: deviceType,
      ...(minutes !== undefined ? { duration_minutes: minutes } : {}),
      ...geometryFields,
    });
  }, [canSend, lines, deviceType, geometryFields, sendMutation, choice, nextChange, sendBoardId]);

  const handleHold = useCallback(() => {
    if (!canSend) return;
    holdMutation.mutate(lines);
  }, [canSend, lines, holdMutation]);

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {boardLabel ? t("description", { board: boardLabel }) : t("descriptionNoBoard")}
          </DialogDescription>
        </DialogHeader>

        <Stack gap="4" className="py-2">
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
            <DevicePreview model={model} ledLayout={ledLayout} message={preview?.rendered ?? ""} size="sm">
              <ScaledBoardDisplay
                message={preview?.rendered ?? ""}
                size="sm"
                boardType={boardColor}
                deviceType={deviceType}
                notesWide={notesWide}
                notesTall={notesTall}
                gridRows={panelGrid?.rows}
                gridCols={panelGrid?.cols}
                code62Glyph={code62Glyph}
              />
            </DevicePreview>
          </Stack>

          <DurationStep
            value={choice}
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

        <DialogFooter className="sticky bottom-0 -mx-6 -mb-6 flex-wrap bg-background px-6 pb-6 pt-2">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={sendMutation.isPending || holdMutation.isPending}
          >
            {t("cancel")}
          </Button>
          {!showSaveForm && (
            <Button variant="outline" onClick={() => setShowSaveForm(true)} disabled={isEmpty}>
              <Save className="mr-1.5 h-4 w-4" />
              {t("saveAsPage")}
            </Button>
          )}
          {/* During silence the send is named for what it does: it wakes the
              board (#949). With holds on, Hold is the primary action, last. */}
          <Button
            variant={silence?.holds ? "outline" : "default"}
            onClick={handleSend}
            disabled={!canSend || sendMutation.isPending || holdMutation.isPending}
            data-testid={silence ? "compose-send-anyway" : undefined}
          >
            {sendMutation.isPending ? t("sending") : t("send")}
          </Button>
          {silence?.holds && (
            <Button
              onClick={handleHold}
              disabled={!canSend || holdMutation.isPending || sendMutation.isPending}
              data-testid="compose-hold"
            >
              <Clock className="mr-1.5 h-4 w-4" />
              {holdMutation.isPending
                ? t("holding")
                : silence.until
                  ? t("hold", { time: silence.until })
                  : t("holdNoTime")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
