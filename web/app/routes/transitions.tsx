/**
 * Transition Lab (beta): transition-plugin test harness.
 *
 * Authors of transition plugins use this page to preview a frame-by-frame
 * animation between two real pages without sending anything to a real
 * board.  The page fetches the list of enabled transition plugins and the
 * user's pages, lets the user pick a plugin plus from/to pages, optionally
 * edit per-plugin config knobs, and then drives the resulting frame array
 * through a raw grid renderer with play / pause / step / scrub controls.
 * Each selected page is rendered through the normal page-preview endpoint
 * so the transition runs against exactly what the board would show.
 *
 * The whole feature sits behind beta.transition_plugins_enabled — when
 * the flag is off the backend 404s and this page shows an opt-in gate.
 */

import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Pause, Play, RotateCcw, SkipBack, SkipForward, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { TransitionGridDisplay } from "@/components/transitions/transition-grid-display";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType, TransitionPreviewResponse } from "@/lib/api";
import { api } from "@/lib/api";

const NOTE_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8];

export default function TransitionsLabPage() {
  const t = useTranslations("transitionLab");
  const router = useRouter();

  const [selectedPluginId, setSelectedPluginId] = useState<string>("");
  const [fromPageId, setFromPageId] = useState<string>("");
  const [toPageId, setToPageId] = useState<string>("");
  const [deviceType, setDeviceType] = useState<DeviceType>("flagship");
  const [notesWide, setNotesWide] = useState(2);
  const [notesTall, setNotesTall] = useState(1);
  const [configJson, setConfigJson] = useState<string>("{}");
  const [preview, setPreview] = useState<TransitionPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  // Playback state.
  const [frameIdx, setFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const playTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const betaQuery = useQuery({
    queryKey: ["settings", "beta"],
    queryFn: () => api.getBetaSettings(),
  });
  const betaEnabled = betaQuery.data?.settings.transition_plugins_enabled ?? false;

  const pluginsQuery = useQuery({
    queryKey: ["transition-plugins"],
    queryFn: () => api.listTransitionPlugins(),
    enabled: betaEnabled,
  });

  const plugins = useMemo(() => pluginsQuery.data?.plugins ?? [], [pluginsQuery.data]);

  const pagesQuery = useQuery({
    queryKey: ["pages"],
    queryFn: () => api.getPages(),
    enabled: betaEnabled,
  });

  const pages = useMemo(() => pagesQuery.data?.pages ?? [], [pagesQuery.data]);

  // Pick the first plugin once loaded so the page isn't empty.
  useEffect(() => {
    if (!selectedPluginId && plugins.length > 0) {
      setSelectedPluginId(plugins[0].id);
    }
  }, [plugins, selectedPluginId]);

  // Default the from/to pickers to the first two pages once loaded.
  useEffect(() => {
    if (pages.length === 0) return;
    if (!fromPageId) {
      setFromPageId(pages[0].id);
    }
    if (!toPageId) {
      setToPageId((pages[1] ?? pages[0]).id);
    }
  }, [pages, fromPageId, toPageId]);

  const selectedPlugin = useMemo(
    () => plugins.find((p) => p.id === selectedPluginId) ?? null,
    [plugins, selectedPluginId],
  );

  // Seed the config editor with the plugin's current config when the
  // selection changes, so authors aren't staring at an empty `{}` when
  // a plugin already has defaults.
  useEffect(() => {
    if (selectedPlugin) {
      setConfigJson(JSON.stringify(selectedPlugin.config ?? {}, null, 2));
    }
  }, [selectedPlugin]);

  const toPage = useMemo(() => pages.find((p) => p.id === toPageId) ?? null, [pages, toPageId]);

  // Match the preview canvas to the target page's geometry — a transition
  // on a real board always runs at the dimensions of the page being shown.
  // The device picker stays editable so authors can still experiment.
  useEffect(() => {
    if (!toPage) return;
    setDeviceType(toPage.device_type);
    if (toPage.device_type === "note_array") {
      setNotesWide(toPage.notes_wide ?? 1);
      setNotesTall(toPage.notes_tall ?? 1);
    }
  }, [toPage]);

  const stopPlayback = useCallback(() => {
    if (playTimerRef.current) {
      clearTimeout(playTimerRef.current);
      playTimerRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  // Drive playback: each frame schedules the next based on its delay_ms
  // (clamped so a long per-frame step delay doesn't stall the preview).
  useEffect(() => {
    if (!isPlaying || !preview) return;
    if (frameIdx >= preview.frames.length - 1) {
      setIsPlaying(false);
      return;
    }
    const rawDelay = preview.frames[frameIdx]?.delay_ms ?? 100;
    const playbackDelay = Math.min(rawDelay, 2000);
    playTimerRef.current = setTimeout(() => {
      setFrameIdx((idx) => Math.min(idx + 1, preview.frames.length - 1));
    }, playbackDelay);
    return () => {
      if (playTimerRef.current) {
        clearTimeout(playTimerRef.current);
        playTimerRef.current = null;
      }
    };
  }, [isPlaying, frameIdx, preview]);

  // When a new preview lands, reset playback to the first frame and
  // autoplay if it has frames.  Autoplay must happen HERE, not in
  // runPreview — this effect runs after the setPreview render, so a
  // setIsPlaying(true) in runPreview would be immediately reverted.
  useEffect(() => {
    setFrameIdx(0);
    setIsPlaying(Boolean(preview && preview.frames.length > 0));
  }, [preview]);

  const runPreview = useCallback(async () => {
    if (!selectedPluginId || !fromPageId || !toPageId) return;
    setPreviewError(null);
    setPreviewing(true);
    stopPlayback();
    try {
      let parsedConfig: Record<string, unknown> = {};
      try {
        parsedConfig = configJson.trim() ? JSON.parse(configJson) : {};
      } catch (err) {
        setPreviewError(t("configInvalid", { error: (err as Error).message }));
        setPreviewing(false);
        return;
      }
      // Render both pages through the normal preview pipeline so the
      // transition runs against exactly what the board would show.
      let fromMessage: string;
      let toMessage: string;
      try {
        const [fromPreview, toPreview] = await Promise.all([api.previewPage(fromPageId), api.previewPage(toPageId)]);
        fromMessage = fromPreview.message;
        toMessage = toPreview.message;
      } catch (err) {
        setPreviewError(t("pageRenderFailed", { error: (err as Error).message }));
        setPreviewing(false);
        return;
      }
      const result = await api.previewTransition({
        plugin_id: selectedPluginId,
        from_text: fromMessage,
        to_text: toMessage,
        device_type: deviceType,
        ...(deviceType === "note_array" ? { notes_wide: notesWide, notes_tall: notesTall } : {}),
        config: parsedConfig,
      });
      setPreview(result);
    } catch (err) {
      setPreviewError((err as Error).message);
    } finally {
      setPreviewing(false);
    }
  }, [configJson, deviceType, fromPageId, notesTall, notesWide, selectedPluginId, stopPlayback, t, toPageId]);

  // Frame to display: current playback index, or the to-grid when the
  // plugin produced no frames (e.g. from == to).
  const displayGrid = useMemo(() => {
    if (preview && preview.frames.length > 0) {
      return preview.frames[Math.min(frameIdx, preview.frames.length - 1)].grid;
    }
    if (preview) {
      return preview.to_grid;
    }
    return null;
  }, [preview, frameIdx]);

  const totalDuration = preview?.total_delay_ms ?? 0;
  const gridSize = deviceType === "flagship" ? "md" : "sm";

  if (betaQuery.isSuccess && !betaEnabled) {
    return (
      <PageLayout>
        <PageHeader icon={FlaskConical} title={t("title")} description={t("description")} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {t("betaGateTitle")}
              <Badge variant="secondary">{t("betaBadge")}</Badge>
            </CardTitle>
            <CardDescription>{t("betaGateDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => router.push("/settings")}>{t("betaGateCta")}</Button>
          </CardContent>
        </Card>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <PageHeader icon={FlaskConical} title={t("title")} description={t("description")} />

      <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t("setupTitle")}</CardTitle>
            <CardDescription>{t("setupDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="plugin-picker">{t("pluginLabel")}</Label>
              <Select value={selectedPluginId} onValueChange={(val: string) => setSelectedPluginId(val)}>
                <SelectTrigger id="plugin-picker">
                  <SelectValue placeholder={t("pluginPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {plugins.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedPlugin && <p className="text-xs text-muted-foreground">{selectedPlugin.description}</p>}
              {pluginsQuery.isSuccess && plugins.length === 0 && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Wand2 className="h-3 w-3" />
                  {t("noPlugins")}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="device-picker">{t("deviceLabel")}</Label>
              <Select value={deviceType} onValueChange={(val: string) => setDeviceType(val as DeviceType)}>
                <SelectTrigger id="device-picker">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="flagship">{t("deviceFlagship")}</SelectItem>
                  <SelectItem value="note">{t("deviceNote")}</SelectItem>
                  <SelectItem value="note_array">{t("deviceNoteArray")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {deviceType === "note_array" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="notes-wide">{t("notesWideLabel")}</Label>
                  <Select value={String(notesWide)} onValueChange={(val: string) => setNotesWide(Number(val))}>
                    <SelectTrigger id="notes-wide">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {NOTE_COUNTS.map((n) => (
                        <SelectItem key={n} value={String(n)}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="notes-tall">{t("notesTallLabel")}</Label>
                  <Select value={String(notesTall)} onValueChange={(val: string) => setNotesTall(Number(val))}>
                    <SelectTrigger id="notes-tall">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {NOTE_COUNTS.map((n) => (
                        <SelectItem key={n} value={String(n)}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="from-page">{t("fromPageLabel")}</Label>
              <Select value={fromPageId} onValueChange={(val: string) => setFromPageId(val)}>
                <SelectTrigger id="from-page">
                  <SelectValue placeholder={t("pagePlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {pages.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="to-page">{t("toPageLabel")}</Label>
              <Select value={toPageId} onValueChange={(val: string) => setToPageId(val)}>
                <SelectTrigger id="to-page">
                  <SelectValue placeholder={t("pagePlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {pages.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {pagesQuery.isSuccess && pages.length === 0 && (
                <p className="text-xs text-muted-foreground">{t("noPages")}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="config-json">{t("configLabel")}</Label>
              <Textarea
                id="config-json"
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
                rows={6}
                className="font-mono text-xs"
                spellCheck={false}
              />
            </div>

            <Button
              onClick={runPreview}
              disabled={!selectedPluginId || !fromPageId || !toPageId || previewing}
              className="w-full"
            >
              {previewing ? t("generating") : t("runPreview")}
            </Button>

            {previewError && <p className="text-sm text-destructive">{previewError}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("previewTitle")}</CardTitle>
            <CardDescription>
              {preview
                ? t("frameSummary", {
                    count: preview.frame_count,
                    seconds: (totalDuration / 1000).toFixed(1),
                  }) + (preview.capped ? ` ${t("cappedSuffix")}` : "")
                : t("previewEmptyHint")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {displayGrid ? (
              <TransitionGridDisplay grid={displayGrid} size={gridSize} />
            ) : (
              <div className="rounded-lg border-2 border-dashed p-12 text-center text-muted-foreground">
                {t("previewEmpty")}
              </div>
            )}

            {preview && preview.frames.length > 0 && (
              <>
                <div className="flex items-center gap-2">
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={() => {
                      stopPlayback();
                      setFrameIdx(0);
                    }}
                    aria-label={t("restart")}
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={() => {
                      stopPlayback();
                      setFrameIdx((i) => Math.max(0, i - 1));
                    }}
                    aria-label={t("prevFrame")}
                  >
                    <SkipBack className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="default"
                    onClick={() => setIsPlaying((p) => !p)}
                    aria-label={isPlaying ? t("pause") : t("play")}
                  >
                    {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={() => {
                      stopPlayback();
                      setFrameIdx((i) => Math.min(preview.frames.length - 1, i + 1));
                    }}
                    aria-label={t("nextFrame")}
                  >
                    <SkipForward className="h-4 w-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {t("frameCounter", { current: frameIdx + 1, total: preview.frames.length })}
                  </span>
                </div>

                <div className="space-y-2">
                  <Label>{t("scrubLabel")}</Label>
                  <Slider
                    value={[frameIdx]}
                    onValueChange={([v]) => {
                      stopPlayback();
                      setFrameIdx(v ?? 0);
                    }}
                    min={0}
                    max={Math.max(0, preview.frames.length - 1)}
                    step={1}
                  />
                </div>

                {preview.frames[frameIdx] && (
                  <p className="text-xs text-muted-foreground">
                    {t("frameDelay", { ms: preview.frames[frameIdx].delay_ms })}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
