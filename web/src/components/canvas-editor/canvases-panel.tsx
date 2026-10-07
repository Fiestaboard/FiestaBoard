"use client";

// The page editor's pixel canvases (LED pixel boards only): the page's
// canvases, "Add canvas", and for the one being edited its area, bleed,
// scale and text mode, and the Draw / Shapes / Source tabs. Core validates,
// rasterises and previews them (design PIXEL_CANVAS.md §5).

import {
  Button,
  Checkbox,
  Flex,
  Grid,
  Heading,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
  Toggle,
  ToggleGroup,
} from "@fiestaboard/ui";
import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";

import { CanvasAreaPicker } from "@/components/canvas-editor/canvas-area-picker";
import { CanvasDrawTab } from "@/components/canvas-editor/canvas-draw-tab";
import { CanvasShapesEditor } from "@/components/canvas-editor/canvas-shapes-editor";
import { CanvasSourcePicker } from "@/components/canvas-editor/canvas-source-picker";
import { useTranslations } from "@/i18n/translations";
import type { Canvas, CanvasArea, CanvasBleedSide, CanvasContent, CanvasIssue } from "@/lib/api";
import {
  canvasPixelSize,
  makeCanvas,
  MAX_CANVASES,
  MAX_PIXELS,
  MAX_SCALE,
  nextCanvasId,
  type PixelBoard,
} from "@/lib/canvas-editing";

const SIDES: Exclude<CanvasBleedSide, "all">[] = ["top", "left", "right", "bottom"];
const CANVAS_ID = /^[a-z0-9_-]{1,16}$/;

interface CanvasesPanelProps {
  canvases: Canvas[];
  onChange: (canvases: Canvas[]) => void;
  /** The page's character grid. */
  gridRows: number;
  gridCols: number;
  /** The pixel board the page is previewed on. */
  board: PixelBoard;
  /** Problems the last preview met drawing the canvases. */
  issues: CanvasIssue[];
  /** Core's refusal of the canvases (a 422 from the preview), if any. */
  error: string | null;
}

export function CanvasesPanel({ canvases, onChange, gridRows, gridCols, board, issues, error }: CanvasesPanelProps) {
  const t = useTranslations("canvasEditor");
  const [activeId, setActiveId] = useState<string | null>(canvases[0]?.id ?? null);
  const active = canvases.find((c) => c.id === activeId) ?? canvases[0] ?? null;

  const add = () => {
    const id = nextCanvasId(canvases);
    // Starts over the top-left half of the board: easy to see, easy to move.
    const area = {
      row: 1,
      col: 1,
      rows: Math.max(1, Math.ceil(gridRows / 2)),
      cols: Math.max(1, Math.ceil(gridCols / 2)),
    };
    onChange([...canvases, makeCanvas(id, area)]);
    setActiveId(id);
  };
  const replace = (id: string, next: Canvas) => onChange(canvases.map((c) => (c.id === id ? next : c)));
  const remove = (id: string) => {
    const rest = canvases.filter((c) => c.id !== id);
    onChange(rest);
    setActiveId(rest[0]?.id ?? null);
  };

  return (
    <Stack gap="3" data-testid="canvases-panel">
      <Flex align="center" justify="between" gap="2" className="flex-wrap">
        <Stack gap="0.5">
          <Heading level={3} className="text-sm font-medium">
            {t("title")}
          </Heading>
          <Text size="xs" tone="muted">
            {t("description")}
          </Text>
        </Stack>
        <Button size="sm" variant="outline" onClick={add} disabled={canvases.length >= MAX_CANVASES}>
          <Plus aria-hidden="true" />
          {t("add")}
        </Button>
      </Flex>
      {canvases.length >= MAX_CANVASES && (
        <Text size="xs" tone="muted">
          {t("limitReached", { max: MAX_CANVASES })}
        </Text>
      )}
      {error && (
        <Text size="xs" tone="destructive" role="alert" data-testid="canvas-error">
          {t("serverError", { message: error })}
        </Text>
      )}
      {issues.length > 0 && (
        <Stack
          gap="0.5"
          data-testid="canvas-issues"
          className="rounded-md border border-warning/50 bg-warning/10 px-3 py-2"
        >
          <Text size="xs" weight="medium" tone="warning">
            {t("issuesTitle")}
          </Text>
          {issues.map((issue, i) => (
            <Text key={i} size="xs" tone="warning">
              {t("issue", { canvas: issue.canvas_id, path: issue.path, message: issue.message })}
            </Text>
          ))}
        </Stack>
      )}

      {canvases.length === 0 ? (
        <Text size="sm" tone="muted">
          {t("empty")}
        </Text>
      ) : (
        <>
          <ToggleGroup
            aria-label={t("listLabel")}
            value={active ? [active.id] : []}
            onValueChange={(values) => values[0] && setActiveId(values[0])}
            className="flex-wrap"
          >
            {canvases.map((c) => (
              <Toggle key={c.id} value={c.id} size="sm" variant="outline" aria-label={t("selectCanvas", { id: c.id })}>
                {c.id}
              </Toggle>
            ))}
          </ToggleGroup>
          {active && (
            <CanvasEditor
              key={canvases.indexOf(active)}
              canvas={active}
              canvases={canvases}
              gridRows={gridRows}
              gridCols={gridCols}
              board={board}
              onChange={(next) => {
                replace(active.id, next);
                if (next.id !== active.id) setActiveId(next.id);
              }}
              onDelete={() => remove(active.id)}
            />
          )}
        </>
      )}
    </Stack>
  );
}

interface CanvasEditorProps {
  canvas: Canvas;
  canvases: Canvas[];
  gridRows: number;
  gridCols: number;
  board: PixelBoard;
  onChange: (canvas: Canvas) => void;
  onDelete: () => void;
}

function CanvasEditor({ canvas, canvases, gridRows, gridCols, board, onChange, onDelete }: CanvasEditorProps) {
  const t = useTranslations("canvasEditor");
  const idFieldId = useId();
  const scaleId = useId();
  const [idDraft, setIdDraft] = useState(canvas.id);
  // A new id from outside (another canvas picked, an AI edit) resets the draft.
  const [seenId, setSeenId] = useState(canvas.id);
  if (seenId !== canvas.id) {
    setSeenId(canvas.id);
    setIdDraft(canvas.id);
  }
  const idTaken = canvases.some((c) => c !== canvas && c.id === idDraft);
  const idValid = CANVAS_ID.test(idDraft) && !idTaken;

  const setArea = (area: CanvasArea) => onChange({ ...canvas, area });
  const setContent = (content: CanvasContent) => onChange({ ...canvas, content });
  const bleed = canvas.bleed ?? [];
  const allBleed = bleed.includes("all");
  const toggleSide = (side: Exclude<CanvasBleedSide, "all">, on: boolean) => {
    const sides = new Set<CanvasBleedSide>(allBleed ? SIDES : bleed);
    if (on) sides.add(side);
    else sides.delete(side);
    sides.delete("all");
    onChange({ ...canvas, bleed: sides.size === SIDES.length ? ["all"] : SIDES.filter((s) => sides.has(s)) });
  };

  const padSize = (() => {
    const size = canvas.content?.size;
    if (size) return { width: size[0], height: size[1] };
    return canvasPixelSize(canvas, board) ?? { width: 32, height: 32 };
  })();
  const padWidth = Math.min(MAX_PIXELS, padSize.width);
  const padHeight = Math.min(MAX_PIXELS, padSize.height);

  return (
    <Stack gap="3" className="rounded-md border p-3" data-testid={`canvas-editor-${canvas.id}`}>
      <Flex align="end" justify="between" gap="2" className="flex-wrap">
        <Stack gap="1">
          <Label htmlFor={idFieldId} className="text-xs">
            {t("idLabel")}
          </Label>
          <Input
            id={idFieldId}
            value={idDraft}
            aria-invalid={idValid ? undefined : true}
            aria-describedby={`${idFieldId}-hint`}
            className="h-8 w-40 font-mono text-xs"
            onChange={(e) => {
              const value = e.target.value;
              setIdDraft(value);
              if (CANVAS_ID.test(value) && !canvases.some((c) => c !== canvas && c.id === value)) {
                onChange({ ...canvas, id: value });
              }
            }}
          />
          <Text id={`${idFieldId}-hint`} size="xs" tone={idValid ? "muted" : "destructive"}>
            {idValid ? t("idHint") : t("idInvalid")}
          </Text>
        </Stack>
        <Button
          size="sm"
          variant="destructive"
          onClick={onDelete}
          aria-label={t("deleteCanvasAria", { id: canvas.id })}
        >
          <Trash2 aria-hidden="true" />
          {t("delete")}
        </Button>
      </Flex>

      <Stack gap="2">
        <Text size="xs" weight="medium">
          {t("areaLabel")}
        </Text>
        <Grid cols="2" sm="4" gap="2">
          <AreaField
            label={t("areaRow")}
            value={canvas.area.row}
            max={gridRows}
            onChange={(row) => setArea({ ...canvas.area, row })}
          />
          <AreaField
            label={t("areaCol")}
            value={canvas.area.col}
            max={gridCols}
            onChange={(col) => setArea({ ...canvas.area, col })}
          />
          <AreaField
            label={t("areaRows")}
            value={canvas.area.rows}
            max={gridRows}
            onChange={(rows) => setArea({ ...canvas.area, rows })}
          />
          <AreaField
            label={t("areaCols")}
            value={canvas.area.cols}
            max={gridCols}
            onChange={(cols) => setArea({ ...canvas.area, cols })}
          />
        </Grid>
        <CanvasAreaPicker
          rows={gridRows}
          cols={gridCols}
          canvases={canvases}
          activeId={canvas.id}
          onAreaChange={setArea}
        />
      </Stack>

      <Flex gap="4" className="flex-wrap">
        <Stack gap="1" role="group" aria-labelledby={`${idFieldId}-bleed`}>
          <Text id={`${idFieldId}-bleed`} size="xs" weight="medium">
            {t("bleedLabel")}
          </Text>
          <Flex gap="3" className="flex-wrap">
            {SIDES.map((side) => {
              const id = `${idFieldId}-bleed-${side}`;
              return (
                <Flex key={side} align="center" gap="1.5">
                  <Checkbox
                    id={id}
                    checked={allBleed || bleed.includes(side)}
                    onChange={(e) => toggleSide(side, e.target.checked)}
                  />
                  <Label htmlFor={id} className="text-xs">
                    {t(`bleed.${side}`)}
                  </Label>
                </Flex>
              );
            })}
          </Flex>
        </Stack>
        <Stack gap="1">
          <Label htmlFor={scaleId} className="text-xs">
            {t("scaleLabel")}
          </Label>
          <Select
            value={String(canvas.scale ?? 1)}
            onValueChange={(v) => v && onChange({ ...canvas, scale: Number(v) })}
          >
            <SelectTrigger id={scaleId} className="h-8 w-28 text-xs" aria-label={t("scaleLabel")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: MAX_SCALE }, (_, i) => i + 1).map((n) => (
                <SelectItem key={n} value={String(n)} className="text-xs">
                  {t("scaleOption", { n })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Stack>
        <Stack gap="1">
          <Text size="xs" weight="medium" id={`${idFieldId}-text`}>
            {t("textModeLabel")}
          </Text>
          <ToggleGroup
            aria-labelledby={`${idFieldId}-text`}
            segmented
            value={[canvas.text ?? "hide"]}
            onValueChange={(values) => values[0] && onChange({ ...canvas, text: values[0] as "hide" | "flow" })}
          >
            <Toggle value="hide" size="sm">
              {t("textHide")}
            </Toggle>
            <Toggle value="flow" size="sm">
              {t("textFlow")}
            </Toggle>
          </ToggleGroup>
        </Stack>
      </Flex>

      <Tabs defaultValue="draw">
        <TabsList>
          <TabsTrigger value="draw">{t("tabDraw")}</TabsTrigger>
          <TabsTrigger value="shapes">{t("tabShapes")}</TabsTrigger>
          <TabsTrigger value="source">{t("tabSource")}</TabsTrigger>
        </TabsList>
        <TabsContent value="draw" className="pt-3">
          <CanvasDrawTab content={canvas.content} width={padWidth} height={padHeight} onContentChange={setContent} />
        </TabsContent>
        <TabsContent value="shapes" className="pt-3">
          <CanvasShapesEditor
            shapes={canvas.content?.shapes ?? []}
            onChange={(shapes) => setContent({ ...(canvas.content ?? {}), shapes })}
          />
        </TabsContent>
        <TabsContent value="source" className="pt-3">
          <CanvasSourcePicker source={canvas.source} onChange={(source) => onChange({ ...canvas, source })} />
        </TabsContent>
      </Tabs>
    </Stack>
  );
}

function AreaField({
  label,
  value,
  max,
  onChange,
}: {
  label: string;
  value: number;
  max: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  return (
    <Stack gap="1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        min={1}
        max={max}
        value={value}
        className="h-8 text-xs"
        onChange={(e) => {
          const n = Math.floor(Number(e.target.value));
          if (Number.isFinite(n) && n >= 1) onChange(n);
        }}
      />
    </Stack>
  );
}
