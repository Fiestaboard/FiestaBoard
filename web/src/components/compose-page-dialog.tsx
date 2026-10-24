"use client";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  Label,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, MonitorSmartphone, PencilLine, Save, Send } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { PlainTextEditor } from "@/components/plain-text-editor";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { PausedNotice, SilenceNotice } from "@/components/silence-notice";
import Link from "@/components/smart-link";
import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType, PageCreate, SetTemporaryOverrideRequest } from "@/lib/api";
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
  /**
   * Name of the destination board, set only when it differs from the board the
   * user currently has selected. Renders a short note so a multi-board user is
   * never surprised by which board lights up.
   */
  targetBoardName?: string;
  targetBoardId?: string;
  silence?: { until: string | null; holds: boolean } | null;
  paused?: boolean;
}

/**
 * Compose a one-off message and send it to the board without saving it
 * (issue #1787).
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
  targetBoardName,
  targetBoardId,
  silence = null,
  paused = false,
}: ComposePageDialogProps) {
  const t = useTranslations("composeDialog");
  const tActive = useTranslations("activeDisplay");
  const queryClient = useQueryClient();
  const messageId = useId();
  const pageNameId = useId();

  const [text, setText] = useState("");
  const [debouncedText, setDebouncedText] = useState("");
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [pageName, setPageName] = useState("");

  // Reset during render (not in an effect) so the first painted frame of a
  // reopened dialog is already empty — react-hooks/set-state-in-effect,
  // same pattern as ForceSetDialog (issue #1568).
  if (useDepsChanged([open]) && open) {
    setText("");
    setDebouncedText("");
    setShowSaveForm(false);
    setPageName("");
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
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["temporaryOverride"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.silenceStatus(targetBoardId) });
      const refresh = await api.forceRefresh().catch(() => null);
      if (refresh?.sent) toast.success(t("toastSent"));
      else if (refresh) toast.info(tActive("toastResendNotSent"));
      else toast.error(t("toastSendError"));
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
      } else if (result.sent) {
        // Silence ended between opening the dialog and pressing Hold.
        toast.success(t("toastSent"));
      } else {
        toast.info(tActive("toastResendNotSent"));
        return;
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
    sendMutation.mutate({
      template: lines,
      device_type: deviceType,
      // Deliberately no duration_minutes: a one-off stays until it is
      // cancelled. In manual mode a message that silently vanishes after N
      // minutes is not what was asked for.
      ...geometryFields,
    });
  }, [canSend, lines, deviceType, geometryFields, sendMutation]);

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
          <DialogTitle className="flex items-center gap-2">
            <PencilLine className="h-5 w-5" />
            {t("title")}
          </DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>

        <Stack gap="4" className="py-2">
          {targetBoardName && (
            <Flex align="start" gap="2" className="rounded-md border border-border bg-muted/40 p-3">
              <MonitorSmartphone className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <Text size="xs" tone="muted">
                {t("primaryBoardNote", { boardName: targetBoardName })}
              </Text>
            </Flex>
          )}

          {paused && <PausedNotice data-testid="compose-paused" />}
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
                      href="/settings?section=behavior#silence-schedule"
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
            <Text size="xs" tone="muted">
              {t("previewLabel")}
            </Text>
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
          </Stack>

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

        <DialogFooter className="flex-wrap">
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
            <Send className="mr-1.5 h-4 w-4" />
            {sendMutation.isPending ? t("sending") : silence ? t("sendNowAnyway") : t("send")}
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
