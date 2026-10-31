import {
  Grid,
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
import { useId } from "react";

import type { FlexibleStyle } from "@/lib/api";

export function Choice({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <Stack gap="1">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value || "inherit"} onValueChange={(v) => onChange(v === "inherit" ? "" : v)}>
        <SelectTrigger id={id} aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[...new Set(["inherit", ...values, ...(value ? [value] : [])])].map((v) => (
            <SelectItem key={v} value={v}>
              {v}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Stack>
  );
}

export function StyleFields({
  label,
  style,
  onChange,
}: {
  label: string;
  style?: FlexibleStyle | null;
  onChange: (style: FlexibleStyle) => void;
}) {
  const change = (key: string, value: string) => {
    const parsed = (key === "size" || key === "height") && /^\d+(\.\d+)?$/.test(value) ? Number(value) : value;
    onChange({ ...style, [key]: value === "" ? null : parsed });
  };
  return (
    <Grid className="grid-cols-2 gap-3">
      {["font", "size", "color", "background", "height"].map((key) => (
        <label key={key} className="space-y-1">
          <Text as="span" className="text-sm">
            {label} {key}
          </Text>
          <Input
            aria-label={`${label} ${key}`}
            value={String(style?.[key] ?? "")}
            placeholder="inherit"
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      <Choice
        label={`${label} align`}
        value={String(style?.align ?? "")}
        values={["left", "center", "right"]}
        onChange={(v) => change("align", v)}
      />
      <Choice
        label={`${label} case`}
        value={String(style?.case ?? "")}
        values={["as-is", "upper", "lower"]}
        onChange={(v) => change("case", v)}
      />
      <Choice
        label={`${label} overflow`}
        value={String(style?.overflow ?? "")}
        values={["wrap", "shrink", "ellipsis"]}
        onChange={(v) => change("overflow", v)}
      />
    </Grid>
  );
}
