// The preview card's header controls (UX-4-1, DD-W156): Figma 307:46094's
// `Live | Sample | Missing` and `🕓 At 7:00 AM` chip, then one ⋯ View menu
// for what the frames don't draw (Preview at a time…, Inspect, zoom, ruler),
// so the header is one 40 px row at every width.

"use client";

import {
  BoardPreviewModeToggle,
  Button,
  type DataSource,
  DataSourceSwitch,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
  Flex,
  Text,
} from "@fiestaboard/ui";
import { Clock, Ellipsis, X } from "lucide-react";
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";

import { TimePicker } from "@/components/ui/time-picker";
import { useTranslations } from "@/i18n/translations";
import {
  EDITOR_SHORTCUTS,
  hasOpenOverlay,
  isTypingTarget,
  matchesShortcut,
  primaryChord,
} from "@/lib/editor-shortcuts";

/** The formula IDE's preview state, as the header shows and changes it. */
export interface PreviewDataView {
  mode: DataSource;
  onModeChange: (mode: DataSource) => void;
  /** `HH:MM`, or "" for now. */
  atTime: string;
  onAtTimeChange: (value: string) => void;
  inspect: boolean;
  onInspectChange: (inspect: boolean) => void;
}

export type PreviewTile = "sm" | "md" | "lg";

/** Fit / Actual size, and on big boards the tile size Actual uses. */
export interface PreviewZoom {
  mode: "fit" | "actual";
  onModeChange: (mode: "fit" | "actual") => void;
  /** Big boards (04b): the tile size, offered as Tile sm · md · lg. */
  tile?: PreviewTile;
  onTileChange?: (tile: PreviewTile) => void;
}

export interface PreviewToggle {
  on: boolean;
  onChange: (on: boolean) => void;
}

export interface PreviewHeaderControlsProps {
  /** The formula IDE's data controls; null where the IDE is off (canvases, the dock). */
  data: PreviewDataView | null;
  zoom: PreviewZoom | null;
  /** The column ruler (big boards). */
  ruler?: PreviewToggle | null;
  /** More View rows from the host (board colour, D3). */
  viewItems?: ReactNode;
  size: "default" | "touch";
}

function shortcutHint(keys: (typeof EDITOR_SHORTCUTS)[keyof typeof EDITOR_SHORTCUTS]) {
  return <DropdownMenuShortcut>{primaryChord(keys).join("")}</DropdownMenuShortcut>;
}

/**
 * F (Fit / Actual size) and 1 (Actual size), outside text, while the header
 * offers zoom. A focused BoardViewport handles F itself first (FiestaUI 1.5a)
 * and marks the event handled, so the two never both toggle.
 */
function useZoomKeys(zoom: PreviewZoom | null, enabled: boolean) {
  const latest = useRef(zoom);
  useEffect(() => {
    latest.current = zoom;
  });
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      const current = latest.current;
      if (!current || event.defaultPrevented || isTypingTarget(event.target) || hasOpenOverlay()) return;
      if (event.key.toLowerCase() === "f" && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
        event.preventDefault();
        current.onModeChange(current.mode === "fit" ? "actual" : "fit");
      } else if (matchesShortcut(event, EDITOR_SHORTCUTS.previewActualSize)) {
        event.preventDefault();
        current.onModeChange("actual");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enabled]);
}

/**
 * The preview header's width (px) under which the title, the data modes and
 * View no longer fit one row: the modes then move into View. A 1024 px window
 * with the Explorer open leaves the card about 290 px; the At chip needs more.
 */
const NARROW_HEADER = 410;
const NARROW_HEADER_WITH_CHIP = 540;

/** Whether the preview card's header is too narrow for the modes; measured before paint. */
function useNarrowHeader(enabled: boolean, chip: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);
  useLayoutEffect(() => {
    const header = ref.current?.closest<HTMLElement>('[data-slot="editor-preview-header"]');
    if (!enabled || !header) return;
    const floor = chip ? NARROW_HEADER_WITH_CHIP : NARROW_HEADER;
    const measure = () => setNarrow(header.clientWidth > 0 && header.clientWidth < floor);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => observer.disconnect();
  }, [enabled, chip]);
  return { ref, narrow };
}

/** Figma 307:46094's `🕓 At 7:00 AM ×`: a state in the row, not a control of its own. */
function PreviewTimeChip({
  atTime,
  onAtTimeChange,
  picking,
  onPickingChange,
}: {
  atTime: string;
  onAtTimeChange: (value: string) => void;
  picking: boolean;
  /** `cleared`: × reset the time, so the chip goes away. */
  onPickingChange: (picking: boolean, cleared?: boolean) => void;
}) {
  const t = useTranslations("formulaIde");
  const tv = useTranslations("previewView");
  if (!atTime && !picking) return null;
  return (
    <Flex
      align="center"
      gap="1"
      data-testid="preview-time-chip"
      className="h-7 shrink-0 rounded-md border border-border bg-background pl-2"
    >
      <Clock aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      <Text as="span" size="xs" className="shrink-0 pl-1">
        {tv("at")}
      </Text>
      <TimePicker
        value={atTime}
        onChange={onAtTimeChange}
        placeholder={t("atNow")}
        aria-label={t("renderAtLabel")}
        open={picking}
        onOpenChange={(open) => onPickingChange(open)}
        className="ml-0.5 h-6 w-auto border-0 bg-transparent px-1 text-xs text-foreground shadow-none hover:bg-transparent [&>svg]:hidden"
      />
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={t("renderAtReset")}
        onClick={() => {
          onAtTimeChange("");
          onPickingChange(false, true);
        }}
      >
        <X aria-hidden />
      </Button>
    </Flex>
  );
}

export function PreviewHeaderControls({ data, zoom, ruler, viewItems, size }: PreviewHeaderControlsProps) {
  const t = useTranslations("formulaIde");
  const tv = useTranslations("previewView");
  const tz = useTranslations("complexEditing");
  const tb = useTranslations("boardDisplay");
  const [picking, setPicking] = useState(false);
  // The desktop pane's header carries the View menu when it has more than Fit / Actual to offer.
  const view = size === "default" && (data !== null || zoom?.tile !== undefined || !!ruler || !!viewItems);
  // Bound wherever the header zooms, so the list's F and 1 are true on the dock too.
  useZoomKeys(zoom, zoom !== null);
  const viewTrigger = useRef<HTMLButtonElement>(null);
  // The chip unmounts when the picker closes without a time, or on ×: focus
  // goes back to View, where "Preview at a time…" was chosen (OPUS-2651).
  const closePicker = (open: boolean, cleared = false) => {
    setPicking(open);
    if (!open && (cleared || !data?.atTime)) requestAnimationFrame(() => viewTrigger.current?.focus());
  };
  const { ref, narrow } = useNarrowHeader(view && data !== null, !!data?.atTime || picking);

  if (!view) {
    return zoom ? (
      <BoardPreviewModeToggle
        mode={zoom.mode}
        onModeChange={zoom.onModeChange}
        size={size}
        labels={{ previewSize: tb("previewSizeLabel"), fit: tb("fitMode"), actual: tb("actualMode") }}
      />
    ) : null;
  }

  return (
    <Flex ref={ref} align="center" gap="2" className="shrink-0 flex-nowrap" data-testid="preview-data-controls">
      {data && (
        <>
          {!narrow && (
            <DataSourceSwitch
              aria-label={t("dataSourceLabel")}
              value={data.mode}
              onValueChange={data.onModeChange}
              size={size}
              options={[
                { value: "live", label: t("live") },
                { value: "sample", label: t("sample") },
                { value: "missing", label: t("missing") },
              ]}
            />
          )}
          <PreviewTimeChip
            atTime={data.atTime}
            onAtTimeChange={data.onAtTimeChange}
            picking={picking}
            onPickingChange={closePicker}
          />
        </>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button ref={viewTrigger} variant="ghost" size="sm" data-testid="preview-view-menu" className="shrink-0">
            <Ellipsis aria-hidden />
            {tv("view")}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          {data && narrow && (
            <>
              <DropdownMenuGroup>
                <DropdownMenuLabel>{t("dataSourceLabel")}</DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  value={data.mode}
                  onValueChange={(value) => data.onModeChange(value as DataSource)}
                >
                  {(["live", "sample", "missing"] as const).map((mode) => (
                    <DropdownMenuRadioItem closeOnClick key={mode} value={mode}>
                      {t(mode)}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
            </>
          )}
          {data && (
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setPicking(true)}>
                <Clock aria-hidden />
                {tv("previewAt")}
              </DropdownMenuItem>
              <DropdownMenuCheckboxItem
                closeOnClick
                checked={data.inspect}
                onCheckedChange={(checked) => data.onInspectChange(checked)}
                aria-keyshortcuts="I"
                data-testid="inspect-toggle"
              >
                {t("inspect")}
                {shortcutHint(EDITOR_SHORTCUTS.inspect)}
              </DropdownMenuCheckboxItem>
            </DropdownMenuGroup>
          )}
          {zoom && (
            <>
              {data && <DropdownMenuSeparator />}
              <DropdownMenuGroup>
                <DropdownMenuLabel>{tv("zoom")}</DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  value={zoom.mode}
                  onValueChange={(value) => zoom.onModeChange(value as "fit" | "actual")}
                >
                  <DropdownMenuRadioItem closeOnClick value="fit" aria-keyshortcuts="F">
                    {tb("fitMode")}
                    <DropdownMenuShortcut>F</DropdownMenuShortcut>
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem closeOnClick value="actual" aria-keyshortcuts="1">
                    {tb("actualMode")}
                    {shortcutHint(EDITOR_SHORTCUTS.previewActualSize)}
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuGroup>
              {zoom.tile !== undefined && (
                <DropdownMenuGroup>
                  <DropdownMenuLabel>{tz("zoomSizes")}</DropdownMenuLabel>
                  <DropdownMenuRadioGroup
                    value={zoom.mode === "actual" ? zoom.tile : ""}
                    onValueChange={(value) => zoom.onTileChange?.(value as PreviewTile)}
                  >
                    {(["sm", "md", "lg"] as const).map((tile) => (
                      <DropdownMenuRadioItem closeOnClick key={tile} value={tile}>
                        {tz(tile === "sm" ? "zoomSm" : tile === "md" ? "zoomMd" : "zoomLg")}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuGroup>
              )}
            </>
          )}
          {ruler && (
            <DropdownMenuCheckboxItem
              closeOnClick
              checked={ruler.on}
              onCheckedChange={(checked) => ruler.onChange(checked)}
            >
              {tv("ruler")}
            </DropdownMenuCheckboxItem>
          )}
          {viewItems}
        </DropdownMenuContent>
      </DropdownMenu>
    </Flex>
  );
}

/** The dock's data controls (< 1024 px), in its ⋯ More instead of a row over the board (UX-10-2). */
export function PreviewDataControls({ data }: { data: PreviewDataView }) {
  const t = useTranslations("formulaIde");
  return (
    <Flex align="center" gap="2" wrap data-testid="preview-data-controls">
      <DataSourceSwitch
        aria-label={t("dataSourceLabel")}
        value={data.mode}
        onValueChange={data.onModeChange}
        size="touch"
        options={[
          { value: "live", label: t("live") },
          { value: "sample", label: t("sample") },
          { value: "missing", label: t("missing") },
        ]}
      />
      <Flex align="center" gap="1">
        <Clock aria-hidden className="size-4 text-muted-foreground" />
        <TimePicker
          value={data.atTime}
          onChange={data.onAtTimeChange}
          placeholder={t("atNow")}
          aria-label={t("renderAtLabel")}
        />
        {data.atTime && (
          <Button
            variant="ghost"
            size="icon-touch"
            aria-label={t("renderAtReset")}
            onClick={() => data.onAtTimeChange("")}
          >
            <X aria-hidden />
          </Button>
        )}
      </Flex>
    </Flex>
  );
}
