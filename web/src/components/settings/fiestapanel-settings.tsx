"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Button,
  Code,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  Label,
  PageSection,
  Skeleton,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Pencil, Trash2, Tv } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { toast } from "sonner";

import { TimePicker } from "@/components/ui/time-picker";
import { useTranslations } from "@/i18n/translations";
import { api, type Panel } from "@/lib/api";
import { appUrl } from "@/lib/base-path";

/** TV-diagonal presets offered as one-tap chips (inches) — never translated. */
const SIZE_PRESETS = [32, 43, 50, 55, 65, 75, 85] as const;

const PANELS_QUERY_KEY = ["panels"] as const;
const HDMI_QUERY_KEY = ["hdmi-kiosk"] as const;

function panelViewerUrl(panel: Pick<Panel, "id" | "short_code">): string {
  // Prefer the TV-typable short URL (/p/1); fall back to the full id for
  // panels created before short codes existed.
  const path = panel.short_code > 0 ? `/p/${panel.short_code}` : `/panel/${panel.id}`;
  return new URL(appUrl(path), window.location.origin).toString();
}

interface EditorState {
  mode: "create" | "edit";
  panelId?: string;
  name: string;
  diagonal: number;
  animationsEnabled: boolean;
  autoDimEnabled: boolean;
  autoDimStart: string;
  autoDimEnd: string;
  calibration: number;
}

const NEW_PANEL: EditorState = {
  mode: "create",
  name: "",
  diagonal: 55,
  animationsEnabled: true,
  autoDimEnabled: false,
  autoDimStart: "22:00",
  autoDimEnd: "07:00",
  calibration: 1,
};

function editorFromPanel(panel: Panel): EditorState {
  return {
    mode: "edit",
    panelId: panel.id,
    name: panel.name,
    diagonal: panel.screen_diagonal_inches,
    animationsEnabled: panel.animations_enabled,
    autoDimEnabled: panel.auto_dim.enabled,
    autoDimStart: panel.auto_dim.start,
    autoDimEnd: panel.auto_dim.end,
    calibration: panel.calibration_scale,
  };
}

export function FiestaPanelSettings() {
  const t = useTranslations("fiestaPanels");
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Panel | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: PANELS_QUERY_KEY,
    queryFn: () => api.listPanels(),
  });

  const hdmi = useQuery({
    queryKey: HDMI_QUERY_KEY,
    queryFn: () => api.getHdmiKiosk(),
    // Installs take minutes (apt on a Pi); poll while one is running.
    refetchInterval: (query) => (query.state.data?.status === "in_progress" ? 3000 : false),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: PANELS_QUERY_KEY });
    // A panel's virtual board shows up in every board-scoped surface.
    void queryClient.invalidateQueries({ queryKey: ["boardSettings"] });
  };

  const createMutation = useMutation({
    mutationFn: (state: EditorState) =>
      api.createPanel({
        name: state.name,
        screen_diagonal_inches: state.diagonal,
      }),
    onSuccess: () => {
      invalidate();
      setEditor(null);
      toast.success(t("created"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateMutation = useMutation({
    mutationFn: (state: EditorState) =>
      api.updatePanel(state.panelId ?? "", {
        name: state.name,
        screen_diagonal_inches: state.diagonal,
        animations_enabled: state.animationsEnabled,
        auto_dim: { enabled: state.autoDimEnabled, start: state.autoDimStart, end: state.autoDimEnd },
        calibration_scale: state.calibration,
      }),
    onSuccess: () => {
      invalidate();
      setEditor(null);
      toast.success(t("saved"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const hdmiMutation = useMutation({
    mutationFn: (enabled: boolean) => api.setHdmiKiosk(enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: HDMI_QUERY_KEY }),
    onError: (error: Error) => toast.error(error.message),
  });

  const displayMutation = useMutation({
    mutationFn: ({ panelId, isDisplay }: { panelId: string; isDisplay: boolean }) =>
      api.updatePanel(panelId, { is_display: isDisplay }),
    onSuccess: () => invalidate(),
    onError: (error: Error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (panelId: string) => api.deletePanel(panelId),
    onSuccess: () => {
      invalidate();
      setDeleteTarget(null);
      toast.success(t("deleted"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const copyUrl = async (panel: Panel) => {
    try {
      await navigator.clipboard.writeText(panelViewerUrl(panel));
      toast.success(t("urlCopied"));
    } catch {
      toast.error(t("urlCopyFailed"));
    }
  };

  if (isLoading) {
    return (
      <PageSection icon={<Tv />} title={t("title")} description={t("description")}>
        <Skeleton className="h-24 w-full" />
      </PageSection>
    );
  }

  const panels = data?.panels ?? [];
  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <PageSection icon={<Tv />} title={t("title")} description={t("description")} className="space-y-4">
      {panels.length === 0 ? (
        <Text tone="muted">{t("empty")}</Text>
      ) : (
        <Stack gap="3">
          {panels.map((panel) => (
            <Flex key={panel.id} gap="4" align="start" className="rounded-lg border border-border p-4">
              <Box aria-hidden="true" className="hidden rounded-md bg-white p-1.5 sm:block">
                <QRCodeSVG value={panelViewerUrl(panel)} size={72} />
              </Box>
              <Stack gap="1" className="min-w-0 flex-1">
                <Text className="font-medium">{panel.name}</Text>
                <Text size="sm" tone="muted">
                  {t("screenMeta", { inches: panel.screen_diagonal_inches })}
                  {panel.rows && panel.cols ? ` · ${t("gridMeta", { cols: panel.cols, rows: panel.rows })}` : ""}
                  {panel.board_missing ? ` · ${t("boardMissing")}` : ""}
                </Text>
                <Flex gap="2" align="center" className="min-w-0">
                  <Code className="truncate text-xs">{panelViewerUrl(panel)}</Code>
                  <Button variant="ghost" size="icon-sm" aria-label={t("copyUrl")} onClick={() => void copyUrl(panel)}>
                    <Copy />
                  </Button>
                </Flex>
                <Text size="xs" tone="muted">
                  {t("openOnTv")}
                </Text>
                <Flex gap="2" align="center">
                  <Switch
                    id={`panel-display-${panel.id}`}
                    checked={panel.is_display}
                    disabled={displayMutation.isPending}
                    onCheckedChange={(checked) =>
                      displayMutation.mutate({ panelId: panel.id, isDisplay: checked === true })
                    }
                  />
                  <Label htmlFor={`panel-display-${panel.id}`} className="text-sm font-normal">
                    {t("displayOutput")}
                  </Label>
                </Flex>
                {panel.is_display && (
                  <Text size="xs" tone="muted">
                    {t("displayOutputHint")}
                  </Text>
                )}
              </Stack>
              <Flex gap="1">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("editPanel")}
                  onClick={() => setEditor(editorFromPanel(panel))}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("deletePanel")}
                  onClick={() => setDeleteTarget(panel)}
                >
                  <Trash2 />
                </Button>
              </Flex>
            </Flex>
          ))}
        </Stack>
      )}

      <Button onClick={() => setEditor(NEW_PANEL)}>{t("createPanel")}</Button>

      {hdmi.data?.supported && (
        <Stack gap="2" className="rounded-lg border border-border p-4">
          <Flex gap="3" align="center">
            <Switch
              id="hdmi-kiosk"
              checked={hdmi.data.status === "enabled" || hdmi.data.status === "in_progress"}
              disabled={hdmi.data.status === "in_progress" || hdmiMutation.isPending}
              onCheckedChange={(checked) => hdmiMutation.mutate(checked === true)}
            />
            <Label htmlFor="hdmi-kiosk">{t("hdmiTitle")}</Label>
          </Flex>
          <Text size="xs" tone="muted">
            {hdmi.data.status === "in_progress"
              ? t("hdmiInstalling")
              : hdmi.data.status === "failed"
                ? t("hdmiFailed")
                : hdmi.data.status === "enabled"
                  ? t("hdmiEnabledHint")
                  : t("hdmiHelp")}
          </Text>
        </Stack>
      )}

      <Dialog open={editor !== null} onOpenChange={(open) => !open && setEditor(null)}>
        <DialogContent>
          {editor && (
            <>
              <DialogHeader>
                <DialogTitle>{editor.mode === "create" ? t("createPanel") : t("editPanel")}</DialogTitle>
                <DialogDescription>{t("editorHelp")}</DialogDescription>
              </DialogHeader>
              <Stack gap="4">
                <Stack gap="2">
                  <Label htmlFor="panel-name">{t("panelName")}</Label>
                  <Input
                    id="panel-name"
                    value={editor.name}
                    onChange={(e) => setEditor({ ...editor, name: e.target.value })}
                  />
                </Stack>
                <Stack gap="2">
                  <Label>{t("screenSize")}</Label>
                  <Flex gap="2" wrap>
                    {SIZE_PRESETS.map((inches) => (
                      <Button
                        key={inches}
                        type="button"
                        size="sm"
                        variant={editor.diagonal === inches ? "default" : "outline"}
                        onClick={() => setEditor({ ...editor, diagonal: inches })}
                      >
                        {inches}&quot;
                      </Button>
                    ))}
                  </Flex>
                  <Flex gap="2" align="center">
                    <Label htmlFor="panel-custom-size" className="text-sm font-normal">
                      {t("screenSizeCustom")}
                    </Label>
                    <Input
                      id="panel-custom-size"
                      type="number"
                      min={10}
                      max={200}
                      step={0.5}
                      className="w-24"
                      value={editor.diagonal}
                      onChange={(e) => {
                        const parsed = Number(e.target.value);
                        if (Number.isFinite(parsed)) setEditor({ ...editor, diagonal: parsed });
                      }}
                    />
                  </Flex>
                  <Text size="xs" tone="muted">
                    {t("autoFitHint")}
                  </Text>
                </Stack>
                {editor.mode === "edit" && (
                  <>
                    <Flex gap="3" align="center">
                      <Switch
                        id="panel-animations"
                        checked={editor.animationsEnabled}
                        onCheckedChange={(checked) => setEditor({ ...editor, animationsEnabled: checked === true })}
                      />
                      <Label htmlFor="panel-animations">{t("flapAnimation")}</Label>
                    </Flex>
                    <Flex gap="3" align="center">
                      <Switch
                        id="panel-auto-dim"
                        checked={editor.autoDimEnabled}
                        onCheckedChange={(checked) => setEditor({ ...editor, autoDimEnabled: checked === true })}
                      />
                      <Label htmlFor="panel-auto-dim">{t("autoDim")}</Label>
                    </Flex>
                    {editor.autoDimEnabled && (
                      <Flex gap="4">
                        <Stack gap="2">
                          <Label htmlFor="panel-dim-start">{t("autoDimStart")}</Label>
                          <TimePicker
                            id="panel-dim-start"
                            value={editor.autoDimStart}
                            onChange={(value) => setEditor({ ...editor, autoDimStart: value })}
                          />
                        </Stack>
                        <Stack gap="2">
                          <Label htmlFor="panel-dim-end">{t("autoDimEnd")}</Label>
                          <TimePicker
                            id="panel-dim-end"
                            value={editor.autoDimEnd}
                            onChange={(value) => setEditor({ ...editor, autoDimEnd: value })}
                          />
                        </Stack>
                      </Flex>
                    )}
                    <Stack gap="2">
                      <Label htmlFor="panel-calibration">{t("calibration")}</Label>
                      <Input
                        id="panel-calibration"
                        type="number"
                        min={0.85}
                        max={1.15}
                        step={0.01}
                        className="w-24"
                        value={editor.calibration}
                        onChange={(e) => {
                          const parsed = Number(e.target.value);
                          if (Number.isFinite(parsed)) setEditor({ ...editor, calibration: parsed });
                        }}
                      />
                      <Text size="xs" tone="muted">
                        {t("calibrationHelp")}
                      </Text>
                    </Stack>
                  </>
                )}
              </Stack>
              <DialogFooter>
                <Button variant="outline" onClick={() => setEditor(null)} disabled={saving}>
                  {t("cancel")}
                </Button>
                <Button
                  onClick={() =>
                    editor.mode === "create" ? createMutation.mutate(editor) : updateMutation.mutate(editor)
                  }
                  disabled={saving || !editor.name.trim() || editor.diagonal < 10 || editor.diagonal > 200}
                >
                  {editor.mode === "create" ? t("create") : t("save")}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("deleteConfirmBody", { name: deleteTarget?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {t("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageSection>
  );
}
