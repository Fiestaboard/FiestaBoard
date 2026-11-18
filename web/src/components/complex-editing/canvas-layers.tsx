"use client";

import { Heading, type LayerItem, LayersPanel, Stack, Text } from "@fiestaboard/ui";
import { Blend, Circle, Hexagon, Minus, Square, Type } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { CanvasShape } from "@/lib/api";

type Translate = (key: string, params?: Record<string, unknown>) => string;

const ICONS: Record<CanvasShape["type"], ReactNode> = {
  rect: <Square className="size-4" aria-hidden="true" />,
  circle: <Circle className="size-4" aria-hidden="true" />,
  ellipse: <Circle className="size-4" aria-hidden="true" />,
  line: <Minus className="size-4" aria-hidden="true" />,
  polygon: <Hexagon className="size-4" aria-hidden="true" />,
  text: <Type className="size-4" aria-hidden="true" />,
  gradient: <Blend className="size-4" aria-hidden="true" />,
};

const isExpression = (value: unknown) => typeof value === "string" && value.includes("{{");

/** Whether a shape draws from data: a `{{…}}` field, a repeat, or a condition. */
export function shapeIsBound(shape: CanvasShape): boolean {
  return Object.entries(shape).some(([key, value]) =>
    key === "foreach" ? true : key === "if" ? typeof value === "string" : isExpression(value),
  );
}

const show = (value: unknown) => (isExpression(value) ? "ƒ" : String(value ?? "–"));

/** A layer's name and its geometry in words, e.g. "Rectangle 1" / "x 30, y 26 · 14 × 8". */
export function describeShape(shape: CanvasShape, index: number, t: Translate): { name: string; meta: string } {
  const n = index + 1;
  switch (shape.type) {
    case "rect":
      return {
        name: t("layerRect", { n }),
        meta: t("layerMetaBox", { x: show(shape.x), y: show(shape.y), w: show(shape.w), h: show(shape.h) }),
      };
    case "circle":
      return {
        name: t("layerCircle", { n }),
        meta: t("layerMetaCircle", { x: show(shape.cx), y: show(shape.cy), r: show(shape.r) }),
      };
    case "ellipse":
      return {
        name: t("layerEllipse", { n }),
        meta: t("layerMetaCircle", {
          x: show(shape.cx),
          y: show(shape.cy),
          r: `${show(shape.rx)} × ${show(shape.ry)}`,
        }),
      };
    case "line":
      return {
        name: t("layerLine", { n }),
        meta: t("layerMetaLine", { x1: show(shape.x1), y1: show(shape.y1), x2: show(shape.x2), y2: show(shape.y2) }),
      };
    case "polygon":
      return {
        name: t("layerPolygon", { n }),
        meta: t("layerMetaPolygon", { count: Array.isArray(shape.points) ? shape.points.length : "ƒ" }),
      };
    case "text":
      return {
        name: isExpression(shape.text) ? t("layerText", { n }) : t("layerTextNamed", { text: shape.text }),
        meta: t("layerMetaText", { font: shape.font ?? "5x7", x: show(shape.x), y: show(shape.y) }),
      };
    case "gradient":
      return {
        name: t("layerGradient", { n }),
        meta: t("layerMetaGradient", { from: show(shape.from), to: show(shape.to) }),
      };
  }
}

/**
 * 04b `135:140352` Layers panel for the active canvas: its shapes front to
 * back (the last drawn is on top), reorderable, with the ones that draw from
 * data marked. The canvas model has no editor-only visibility, so the eye
 * reports a shape's `if: false` rather than toggling it (DD-W).
 */
export function CanvasLayers({
  canvasId,
  shapes,
  onShapesChange,
}: {
  canvasId: string;
  shapes: readonly CanvasShape[];
  onShapesChange: (shapes: CanvasShape[]) => void;
}) {
  const t = useTranslations("complexEditing");
  const [selectedId, setSelectedId] = useState<string>();
  const layers = useMemo<LayerItem[]>(
    () =>
      shapes
        .map((shape, index) => {
          const { name, meta } = describeShape(shape, index, t);
          const bound = shapeIsBound(shape);
          return {
            id: String(index),
            name,
            meta,
            type: ICONS[shape.type],
            bound,
            boundValue: bound ? t("layerBound") : undefined,
            visible: shape.if !== false,
          };
        })
        .reverse(),
    [shapes, t],
  );
  if (shapes.length === 0) return null;
  return (
    <Stack gap="2" data-slot="canvas-layers">
      <Heading level={4} className="text-sm font-medium">
        {t("layersTitle", { canvas: canvasId })}
      </Heading>
      <LayersPanel
        aria-label={t("layersTitle", { canvas: canvasId })}
        layers={layers}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onReorder={(next) => {
          const reordered = [...next].reverse().map((layer) => shapes[Number(layer.id)]);
          // Layer ids are model positions: keep the selection on the same shape.
          if (selectedId !== undefined) setSelectedId(String(reordered.indexOf(shapes[Number(selectedId)])));
          onShapesChange(reordered);
        }}
      />
      <Text size="xs" tone="muted">
        {t("layersHint")}
      </Text>
    </Stack>
  );
}
