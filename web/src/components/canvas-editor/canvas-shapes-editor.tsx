"use client";

// The Shapes tab of the page editor's canvas panel: add, edit, reorder and
// delete a canvas's shapes with typed fields (every field also takes a
// `{{…}}` expression, with variable autocompletion), or edit them all as
// JSON. Core is the validator: its message for a bad shape is shown by the
// panel (design PIXEL_CANVAS.md §1, §5).

import {
  Button,
  Card,
  CardContent,
  Flex,
  Grid,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Switch,
  Text,
  Textarea,
} from "@fiestaboard/ui";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";

import { VariableAutocompleteTextarea } from "@/components/variable-autocomplete-textarea";
import { useTranslations } from "@/i18n/translations";
import type { CanvasShape } from "@/lib/api";

export type ShapeType = CanvasShape["type"];

/** Each shape's own fields, required first (src/canvas/models.py). */
export const SHAPE_FIELDS: Record<ShapeType, { name: string; required: boolean; kind: "num" | "color" | "text" }[]> = {
  rect: [
    { name: "x", required: true, kind: "num" },
    { name: "y", required: true, kind: "num" },
    { name: "w", required: true, kind: "num" },
    { name: "h", required: true, kind: "num" },
    { name: "fill", required: false, kind: "color" },
    { name: "stroke", required: false, kind: "color" },
  ],
  circle: [
    { name: "cx", required: true, kind: "num" },
    { name: "cy", required: true, kind: "num" },
    { name: "r", required: true, kind: "num" },
    { name: "fill", required: false, kind: "color" },
    { name: "stroke", required: false, kind: "color" },
  ],
  ellipse: [
    { name: "cx", required: true, kind: "num" },
    { name: "cy", required: true, kind: "num" },
    { name: "rx", required: true, kind: "num" },
    { name: "ry", required: true, kind: "num" },
    { name: "fill", required: false, kind: "color" },
    { name: "stroke", required: false, kind: "color" },
  ],
  line: [
    { name: "x1", required: true, kind: "num" },
    { name: "y1", required: true, kind: "num" },
    { name: "x2", required: true, kind: "num" },
    { name: "y2", required: true, kind: "num" },
    { name: "stroke", required: true, kind: "color" },
    { name: "width", required: false, kind: "num" },
  ],
  polygon: [
    { name: "points", required: true, kind: "text" },
    { name: "fill", required: false, kind: "color" },
    { name: "stroke", required: false, kind: "color" },
  ],
  text: [
    { name: "x", required: true, kind: "num" },
    { name: "y", required: true, kind: "num" },
    { name: "text", required: true, kind: "text" },
    { name: "color", required: true, kind: "color" },
    { name: "font", required: false, kind: "text" },
  ],
  gradient: [
    { name: "from", required: true, kind: "color" },
    { name: "to", required: true, kind: "color" },
    { name: "angle", required: false, kind: "num" },
    { name: "x", required: false, kind: "num" },
    { name: "y", required: false, kind: "num" },
    { name: "w", required: false, kind: "num" },
    { name: "h", required: false, kind: "num" },
  ],
};

export const SHAPE_TYPES = Object.keys(SHAPE_FIELDS) as ShapeType[];

/** A new shape of *type* with sensible starting values. */
export function defaultShape(type: ShapeType): CanvasShape {
  switch (type) {
    case "rect":
      return { type, x: 0, y: 0, w: 8, h: 8, fill: "#ff0000" };
    case "circle":
      return { type, cx: 8, cy: 8, r: 4, fill: "#ffcc00" };
    case "ellipse":
      return { type, cx: 8, cy: 8, rx: 6, ry: 3, fill: "#00aaff" };
    case "line":
      return { type, x1: 0, y1: 0, x2: 8, y2: 8, stroke: "#ffffff" };
    case "polygon":
      return {
        type,
        points: [
          [0, 8],
          [4, 0],
          [8, 8],
        ],
        fill: "#7ed321",
      };
    case "text":
      return { type, x: 0, y: 0, text: "HI", color: "#ffffff" };
    case "gradient":
      return { type, from: "#000033", to: "#3366ff" };
  }
}

/** A field's text as typed -> its JSON value: numbers stay numbers, everything else stays text. */
export function parseFieldValue(name: string, raw: string): unknown {
  const text = raw.trim();
  if (text === "") return undefined;
  if (name === "points" && text.startsWith("[")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  if (/^-?\d+(\.\d+)?$/.test(text)) return Number(text);
  return raw;
}

function fieldText(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

interface CanvasShapesEditorProps {
  shapes: CanvasShape[];
  onChange: (shapes: CanvasShape[]) => void;
}

export function CanvasShapesEditor({ shapes, onChange }: CanvasShapesEditorProps) {
  const t = useTranslations("canvasEditor");
  const [newType, setNewType] = useState<ShapeType>("rect");
  const [jsonMode, setJsonMode] = useState(false);
  const jsonSwitchId = useId();
  const typeId = useId();

  const update = (index: number, shape: CanvasShape) => onChange(shapes.map((s, i) => (i === index ? shape : s)));
  const move = (index: number, by: number) => {
    const next = [...shapes];
    const [shape] = next.splice(index, 1);
    next.splice(index + by, 0, shape);
    onChange(next);
  };

  return (
    <Stack gap="3">
      <Flex align="center" justify="between" gap="2" className="flex-wrap">
        <Flex align="center" gap="2">
          <Label htmlFor={typeId} className="sr-only">
            {t("shapeType")}
          </Label>
          <Select value={newType} onValueChange={(v) => v && setNewType(v as ShapeType)}>
            <SelectTrigger id={typeId} className="h-8 w-36 text-xs" aria-label={t("shapeType")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SHAPE_TYPES.map((type) => (
                <SelectItem key={type} value={type} className="text-xs">
                  {t(`shapeTypes.${type}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={() => onChange([...shapes, defaultShape(newType)])}>
            <Plus aria-hidden="true" />
            {t("addShape")}
          </Button>
        </Flex>
        <Flex align="center" gap="1.5">
          <Switch id={jsonSwitchId} checked={jsonMode} onCheckedChange={setJsonMode} />
          <Label htmlFor={jsonSwitchId} className="text-xs">
            {t("jsonToggle")}
          </Label>
        </Flex>
      </Flex>
      <Text size="xs" tone="muted">
        {t("fieldHint", { example: "{{weather.temperature}}" })}
      </Text>

      {jsonMode ? (
        <ShapesJsonEditor shapes={shapes} onChange={onChange} />
      ) : shapes.length === 0 ? (
        <Text size="sm" tone="muted">
          {t("shapesEmpty")}
        </Text>
      ) : (
        <Stack gap="2" role="list" aria-label={t("shapesListLabel")}>
          {shapes.map((shape, index) => (
            <ShapeCard
              key={index}
              shape={shape}
              index={index}
              count={shapes.length}
              onChange={(s) => update(index, s)}
              onMove={(by) => move(index, by)}
              onDelete={() => onChange(shapes.filter((_, i) => i !== index))}
            />
          ))}
        </Stack>
      )}
    </Stack>
  );
}

interface ShapeCardProps {
  shape: CanvasShape;
  index: number;
  count: number;
  onChange: (shape: CanvasShape) => void;
  onMove: (by: number) => void;
  onDelete: () => void;
}

function ShapeCard({ shape, index, count, onChange, onMove, onDelete }: ShapeCardProps) {
  const t = useTranslations("canvasEditor");
  const n = index + 1;
  const record = shape as unknown as Record<string, unknown>;
  const setField = (name: string, raw: string) => {
    const next = { ...record };
    const value = parseFieldValue(name, raw);
    if (value === undefined) delete next[name];
    else next[name] = value;
    onChange(next as unknown as CanvasShape);
  };
  const fields = SHAPE_FIELDS[shape.type] ?? [];

  return (
    <Card role="listitem" className="gap-2 py-3">
      <CardContent className="space-y-2 px-3">
        <Flex align="center" justify="between">
          <Text size="sm" weight="medium">
            {t("shapeTitle", { index: n, type: t(`shapeTypes.${shape.type}`) })}
          </Text>
          <Flex gap="1">
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label={t("moveUp", { index: n })}
              disabled={index === 0}
              onClick={() => onMove(-1)}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label={t("moveDown", { index: n })}
              disabled={index === count - 1}
              onClick={() => onMove(1)}
            >
              <ArrowDown aria-hidden="true" />
            </Button>
            <Button size="icon-xs" variant="ghost" aria-label={t("deleteShape", { index: n })} onClick={onDelete}>
              <Trash2 aria-hidden="true" />
            </Button>
          </Flex>
        </Flex>
        <Grid cols="2" sm="3" gap="2">
          {fields.map((field) => (
            <ShapeField
              key={field.name}
              label={t(`fields.${field.name}`)}
              required={field.required}
              value={fieldText(record[field.name])}
              onChange={(raw) => setField(field.name, raw)}
            />
          ))}
        </Grid>
        <Grid cols="1" sm="3" gap="2">
          <ShapeField
            label={t("conditionLabel")}
            value={fieldText(record.if)}
            onChange={(raw) => setField("if", raw)}
          />
          <ShapeField
            label={t("foreachLabel")}
            value={fieldText(record.foreach)}
            onChange={(raw) => setField("foreach", raw)}
          />
          <ShapeField label={t("asLabel")} value={fieldText(record.as)} onChange={(raw) => setField("as", raw)} />
        </Grid>
      </CardContent>
    </Card>
  );
}

function ShapeField({
  label,
  value,
  required,
  onChange,
}: {
  label: string;
  value: string;
  required?: boolean;
  onChange: (raw: string) => void;
}) {
  const id = useId();
  // Typed text is kept as typed ("1." stays "1." until it parses), and
  // refreshed when the shape changes from outside (JSON edit, reorder).
  const [draft, setDraft] = useState(value);
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setDraft(value);
  }
  return (
    <Stack gap="1">
      <Label htmlFor={id} className="text-xs">
        {label}
        {required ? " *" : ""}
      </Label>
      <VariableAutocompleteTextarea
        id={id}
        value={draft}
        onChange={(next) => {
          const single = next.replace(/\n/g, "");
          setDraft(single);
          onChange(single);
        }}
        className="min-h-8 resize-none py-1 font-mono text-xs"
      />
    </Stack>
  );
}

function ShapesJsonEditor({ shapes, onChange }: { shapes: CanvasShape[]; onChange: (s: CanvasShape[]) => void }) {
  const t = useTranslations("canvasEditor");
  const id = useId();
  const [text, setText] = useState(() => JSON.stringify(shapes, null, 2));
  const [error, setError] = useState<string | null>(null);
  return (
    <Stack gap="1">
      <Label htmlFor={id} className="text-xs">
        {t("jsonLabel")}
      </Label>
      <Textarea
        id={id}
        value={text}
        rows={10}
        spellCheck={false}
        aria-invalid={error ? true : undefined}
        className="font-mono text-xs"
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed: unknown = JSON.parse(e.target.value);
            if (!Array.isArray(parsed)) {
              setError(t("jsonNotList"));
              return;
            }
            setError(null);
            onChange(parsed as CanvasShape[]);
          } catch (err) {
            setError(t("jsonInvalid", { message: (err as Error).message }));
          }
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
