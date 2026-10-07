"use client";

// The Draw tab of the page editor's canvas panel: a pixel pad on an HTML
// canvas (brush, eraser, fill bucket, eyedropper, any RGB colour) that writes
// the canvas's `content.pixels` + `palette` (design PIXEL_CANVAS.md §5).

import { Box, Button, Flex, Input, Label, Stack, Switch, Text, Toggle, ToggleGroup } from "@fiestaboard/ui";
import { Eraser, Paintbrush, PaintBucket, Pipette, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { CanvasContent } from "@/lib/api";
import {
  decodePixels,
  encodePixels,
  floodFill,
  MAX_PALETTE_COLORS,
  normalizeHex,
  type PixelColor,
  type PixelGrid,
} from "@/lib/canvas-editing";

export type PadTool = "brush" | "eraser" | "fill" | "picker";

const ZOOMS = [2, 4, 6, 8, 12, 16];
const DEFAULT_ZOOM_INDEX = 3;

interface CanvasDrawTabProps {
  content: CanvasContent | null | undefined;
  /** The pad's pixel size: the content's own `size`, else the canvas's pixel size on the board. */
  width: number;
  height: number;
  onContentChange: (content: CanvasContent) => void;
}

/** Draw tab: tool bar + pixel pad. Painting writes `pixels`/`palette` and pins `size` to the pad. */
export function CanvasDrawTab({ content, width, height, onContentChange }: CanvasDrawTabProps) {
  const t = useTranslations("canvasEditor");
  const [tool, setTool] = useState<PadTool>("brush");
  const [color, setColor] = useState("#ff0000");
  const [hexDraft, setHexDraft] = useState("#ff0000");
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [showGrid, setShowGrid] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const gridSwitchId = useId();
  const hexId = useId();
  const colorId = useId();

  const grid = useMemo(() => decodePixels(content, width, height), [content, width, height]);

  const commit = useCallback(
    (next: PixelGrid) => {
      if (next === grid) return;
      try {
        const { palette, pixels } = encodePixels(next, content?.palette ?? {});
        setError(null);
        onContentChange({ ...(content ?? {}), size: content?.size ?? [width, height], palette, pixels });
      } catch {
        setError(t("tooManyColors", { max: MAX_PALETTE_COLORS }));
      }
    },
    [content, grid, height, onContentChange, t, width],
  );

  const chooseColor = (value: string) => {
    const hex = normalizeHex(value);
    setHexDraft(value);
    if (hex) setColor(hex);
  };

  return (
    <Stack gap="3">
      <Flex align="center" gap="2" className="flex-wrap">
        <ToggleGroup
          aria-label={t("toolsLabel")}
          segmented
          value={[tool]}
          onValueChange={(values) => values[0] && setTool(values[0] as PadTool)}
        >
          <Toggle value="brush" size="icon-sm" aria-label={t("toolBrush")}>
            <Paintbrush aria-hidden="true" />
          </Toggle>
          <Toggle value="eraser" size="icon-sm" aria-label={t("toolEraser")}>
            <Eraser aria-hidden="true" />
          </Toggle>
          <Toggle value="fill" size="icon-sm" aria-label={t("toolFill")}>
            <PaintBucket aria-hidden="true" />
          </Toggle>
          <Toggle value="picker" size="icon-sm" aria-label={t("toolPicker")}>
            <Pipette aria-hidden="true" />
          </Toggle>
        </ToggleGroup>
        <Flex align="center" gap="1.5">
          <Label htmlFor={colorId} className="sr-only">
            {t("colorLabel")}
          </Label>
          <Input
            id={colorId}
            type="color"
            value={color}
            onChange={(e) => chooseColor(e.target.value)}
            className="h-8 w-10 cursor-pointer p-0.5"
          />
          <Label htmlFor={hexId} className="sr-only">
            {t("hexLabel")}
          </Label>
          <Input
            id={hexId}
            value={hexDraft}
            onChange={(e) => chooseColor(e.target.value)}
            aria-invalid={normalizeHex(hexDraft) ? undefined : true}
            className="h-8 w-24 font-mono text-xs"
            spellCheck={false}
          />
        </Flex>
        <Flex align="center" gap="1">
          <Button
            size="icon-sm"
            variant="outline"
            aria-label={t("zoomOut")}
            disabled={zoomIndex === 0}
            onClick={() => setZoomIndex((z) => Math.max(0, z - 1))}
          >
            <ZoomOut aria-hidden="true" />
          </Button>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label={t("zoomIn")}
            disabled={zoomIndex === ZOOMS.length - 1}
            onClick={() => setZoomIndex((z) => Math.min(ZOOMS.length - 1, z + 1))}
          >
            <ZoomIn aria-hidden="true" />
          </Button>
        </Flex>
        <Flex align="center" gap="1.5">
          <Switch id={gridSwitchId} checked={showGrid} onCheckedChange={setShowGrid} />
          <Label htmlFor={gridSwitchId} className="text-xs">
            {t("gridToggle")}
          </Label>
        </Flex>
        <Button size="sm" variant="ghost" onClick={() => commit(grid.map((row) => row.map(() => null)))}>
          <Trash2 aria-hidden="true" />
          {t("clear")}
        </Button>
      </Flex>
      <Text size="xs" tone="muted">
        {t("padSize", { width, height })}
      </Text>
      <PixelPad
        grid={grid}
        tool={tool}
        color={color}
        zoom={ZOOMS[zoomIndex]}
        showGrid={showGrid}
        onChange={commit}
        onPick={(picked) => {
          if (picked) {
            setColor(picked);
            setHexDraft(picked);
          }
          setTool("brush");
        }}
      />
      {error && (
        <Text size="xs" tone="destructive" role="alert">
          {error}
        </Text>
      )}
    </Stack>
  );
}

interface PixelPadProps {
  grid: PixelGrid;
  tool: PadTool;
  color: string;
  /** Screen pixels per canvas pixel. */
  zoom: number;
  showGrid: boolean;
  onChange: (grid: PixelGrid) => void;
  onPick: (color: PixelColor) => void;
}

/**
 * The pixel pad: an HTML canvas the pointer paints on. Keyboard: the arrow
 * keys move a cursor and Space (or Enter) applies the tool there; the
 * cursor's position and colour are announced.
 */
export function PixelPad({ grid, tool, color, zoom, showGrid, onChange, onPick }: PixelPadProps) {
  const t = useTranslations("canvasEditor");
  const height = grid.length;
  const width = grid[0]?.length ?? 0;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paintingRef = useRef(false);
  // The grid as of the last paint of the current stroke, so a drag paints on
  // its own result before the parent re-renders.
  const strokeGridRef = useRef<PixelGrid>(grid);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const hintId = useId();

  useEffect(() => {
    strokeGridRef.current = grid;
  }, [grid]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext?.("2d");
    if (!canvas || !ctx) return;
    canvas.width = width * zoom;
    canvas.height = height * zoom;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const c = grid[y][x];
        // Transparent pixels show a checker so they read as "nothing here".
        ctx.fillStyle = c ?? ((x + y) % 2 === 0 ? "#3a3a3a" : "#2a2a2a");
        ctx.fillRect(x * zoom, y * zoom, zoom, zoom);
      }
    }
    if (showGrid && zoom >= 4) {
      ctx.strokeStyle = "rgba(255,255,255,0.12)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x <= width; x++) {
        ctx.moveTo(x * zoom + 0.5, 0);
        ctx.lineTo(x * zoom + 0.5, height * zoom);
      }
      for (let y = 0; y <= height; y++) {
        ctx.moveTo(0, y * zoom + 0.5);
        ctx.lineTo(width * zoom, y * zoom + 0.5);
      }
      ctx.stroke();
    }
    if (cursor) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.strokeRect(cursor.x * zoom + 1, cursor.y * zoom + 1, zoom - 2, zoom - 2);
    }
  }, [grid, width, height, zoom, showGrid, cursor]);

  const apply = useCallback(
    (x: number, y: number, continuing: boolean) => {
      if (x < 0 || y < 0 || x >= width || y >= height) return;
      const base = continuing ? strokeGridRef.current : grid;
      if (tool === "picker") {
        onPick(base[y][x]);
        return;
      }
      if (tool === "fill") {
        if (continuing) return;
        const next = floodFill(base, x, y, color);
        strokeGridRef.current = next;
        onChange(next);
        return;
      }
      const paint: PixelColor = tool === "eraser" ? null : color;
      if (base[y][x] === paint) return;
      const next = base.map((row, ry) => (ry === y ? row.map((c, rx) => (rx === x ? paint : c)) : row));
      strokeGridRef.current = next;
      onChange(next);
    },
    [color, grid, height, onChange, onPick, tool, width],
  );

  const cellAt = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: Math.floor((e.clientX - rect.left) / zoom), y: Math.floor((e.clientY - rect.top) / zoom) };
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    const at = cursor ?? { x: 0, y: 0 };
    if (e.key in moves) {
      e.preventDefault();
      const [dx, dy] = moves[e.key];
      setCursor({ x: Math.min(width - 1, Math.max(0, at.x + dx)), y: Math.min(height - 1, Math.max(0, at.y + dy)) });
    } else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      setCursor(at);
      apply(at.x, at.y, false);
    }
  };

  const cursorColor = cursor ? (grid[cursor.y]?.[cursor.x] ?? null) : null;

  return (
    <Stack gap="1">
      <Box className="max-h-[28rem] max-w-full overflow-auto rounded-md border bg-muted/30 p-1">
        <canvas
          ref={canvasRef}
          role="application"
          tabIndex={0}
          aria-label={t("padLabel", { width, height })}
          aria-describedby={hintId}
          data-testid="pixel-pad"
          width={width * zoom}
          height={height * zoom}
          style={{ width: width * zoom, height: height * zoom, imageRendering: "pixelated", touchAction: "none" }}
          className="block cursor-crosshair focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onPointerDown={(e) => {
            paintingRef.current = true;
            e.currentTarget.setPointerCapture?.(e.pointerId);
            const { x, y } = cellAt(e);
            apply(x, y, false);
          }}
          onPointerMove={(e) => {
            if (!paintingRef.current) return;
            const { x, y } = cellAt(e);
            apply(x, y, true);
          }}
          onPointerUp={() => {
            paintingRef.current = false;
          }}
          onPointerLeave={() => {
            paintingRef.current = false;
          }}
          onKeyDown={onKeyDown}
          onFocus={() => setCursor((c) => c ?? { x: 0, y: 0 })}
          onBlur={() => setCursor(null)}
        />
      </Box>
      <Text id={hintId} size="xs" tone="muted">
        {t("padHint")}
      </Text>
      <Text size="xs" tone="muted" aria-live="polite" data-testid="pixel-pad-cursor">
        {cursor ? t("padCursor", { x: cursor.x + 1, y: cursor.y + 1, color: cursorColor ?? t("transparent") }) : ""}
      </Text>
    </Stack>
  );
}
