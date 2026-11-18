// Builder mode (04c 118:5246): six recipes, each a form that writes plain
// formula text with real functions only. The list recipe sums its column
// budget against the board width. Builder → Code is lossless: "Edit in Code"
// opens the same text.

"use client";

import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  ChoiceChip,
  ChoiceChipGroup,
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
  TruncationMap,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Code2, Plus, Sigma, Trash2 } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { prettyPrint } from "@/lib/formula-ide/pretty";
import {
  buildRecipe,
  columnBudget,
  type ListColumn,
  RECIPE_IDS,
  type RecipeForm,
  type RecipeId,
} from "@/lib/formula-ide/recipes";

import { WorkbenchHeader } from "./workbench-header";
import type { WorkbenchProps } from "./workbench-types";

interface ArrayVariable {
  path: string;
  fields: string[];
}

function useArrayVariables(): ArrayVariable[] {
  const { data } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
    staleTime: 5 * 60 * 1000,
  });
  return useMemo(() => {
    const out: ArrayVariable[] = [];
    for (const [plugin, fields] of Object.entries(data?.variable_metadata ?? {})) {
      for (const [name, meta] of Object.entries(fields)) {
        const entry = meta as { type?: string; item_fields?: string[] };
        if (entry.type === "array") out.push({ path: `${plugin}.${name}`, fields: entry.item_fields ?? [] });
      }
    }
    return out;
  }, [data]);
}

const DEFAULT_FORMS: { [K in RecipeId]: Extract<RecipeForm, { recipe: K }> } = {
  either: { recipe: "either", condition: "", then: "", otherwise: "" },
  fallback: { recipe: "fallback", value: "", fallback: "--" },
  threshold: { recipe: "threshold", value: "", threshold: 80, above: "red", below: "green" },
  list: { recipe: "list", list: "", take: 3, columns: [], empty: "" },
  countdown: { recipe: "countdown", value: "", unit: "minutes", suffix: "" },
  date: { recipe: "date", value: "", pattern: "ddd MMM DD" },
};

function TextField({
  label,
  value,
  onChange,
  mono = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  const id = useId();
  return (
    <Stack gap="1">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={mono ? "font-mono" : undefined}
      />
    </Stack>
  );
}

function ColumnRow({
  column,
  onChange,
  onRemove,
}: {
  column: ListColumn;
  onChange: (column: ListColumn) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("formulaIde");
  const id = useId();
  return (
    <Flex align="end" gap="2" wrap className="rounded-lg border bg-muted/40 p-2" data-testid="list-column">
      <Stack gap="1" className="min-w-28 flex-1">
        <Label htmlFor={`${id}-field`}>{t("columnField")}</Label>
        <Input
          id={`${id}-field`}
          value={column.field}
          className="font-mono"
          onChange={(e) => onChange({ ...column, field: e.target.value, label: e.target.value })}
        />
      </Stack>
      <Stack gap="1" className="w-32">
        <Label htmlFor={`${id}-cut`}>{t("columnFit")}</Label>
        <Select
          value={column.format ? "format" : column.cut}
          onValueChange={(v) =>
            onChange({
              ...column,
              cut: v === "format" ? column.cut : (v as ListColumn["cut"]),
              format: v === "format" ? (column.format ?? "hh:mm") : undefined,
            })
          }
        >
          <SelectTrigger id={`${id}-cut`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pad">{t("fitPad")}</SelectItem>
            <SelectItem value="left">{t("fitLeft")}</SelectItem>
            <SelectItem value="none">{t("fitNone")}</SelectItem>
            <SelectItem value="format">{t("fitFormat")}</SelectItem>
          </SelectContent>
        </Select>
      </Stack>
      {column.format !== undefined && (
        <Stack gap="1" className="w-28">
          <Label htmlFor={`${id}-format`}>{t("columnFormat")}</Label>
          <Input
            id={`${id}-format`}
            value={column.format}
            className="font-mono"
            onChange={(e) => onChange({ ...column, format: e.target.value })}
          />
        </Stack>
      )}
      <Stack gap="1" className="w-20">
        <Label htmlFor={`${id}-width`}>{t("columnWidth")}</Label>
        <Input
          id={`${id}-width`}
          type="number"
          min={1}
          max={99}
          value={column.width}
          onChange={(e) => onChange({ ...column, width: Math.max(1, Number(e.target.value) || 1) })}
        />
      </Stack>
      <Flex align="center" gap="2" className="h-9">
        <Checkbox
          id={`${id}-upper`}
          checked={column.upper}
          onCheckedChange={(checked) => onChange({ ...column, upper: checked === true })}
        />
        <Label htmlFor={`${id}-upper`}>{t("columnUpper")}</Label>
      </Flex>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t("removeColumn", { field: column.field || "?" })}
        onClick={onRemove}
      >
        <Trash2 aria-hidden />
      </Button>
    </Flex>
  );
}

function ListRecipeForm({
  form,
  setForm,
  boardCols,
}: {
  form: Extract<RecipeForm, { recipe: "list" }>;
  setForm: (form: RecipeForm) => void;
  boardCols: number;
}) {
  const t = useTranslations("formulaIde");
  const arrays = useArrayVariables();
  const id = useId();
  const budget = columnBudget(form.columns, boardCols);
  const pickList = (path: string) => {
    const fields = arrays.find((a) => a.path === path)?.fields ?? [];
    setForm({
      ...form,
      list: path,
      columns: fields.slice(0, 3).map((field) => ({ field, label: field, upper: true, width: 5, cut: "pad" })),
    });
  };
  return (
    <Stack gap="3">
      <Flex align="end" gap="2" wrap>
        <Stack gap="1" className="min-w-48 flex-1">
          <Label htmlFor={`${id}-list`}>{t("listLabel")}</Label>
          {arrays.length > 0 ? (
            <Select value={form.list} onValueChange={pickList}>
              <SelectTrigger id={`${id}-list`} className="font-mono">
                <SelectValue placeholder={t("listPlaceholder")} />
              </SelectTrigger>
              <SelectContent>
                {arrays.map((a) => (
                  <SelectItem key={a.path} value={a.path} className="font-mono">
                    {a.path}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              id={`${id}-list`}
              value={form.list}
              className="font-mono"
              onChange={(e) => setForm({ ...form, list: e.target.value })}
            />
          )}
        </Stack>
        <Stack gap="1" className="w-24">
          <Label htmlFor={`${id}-take`}>{t("listTake")}</Label>
          <Input
            id={`${id}-take`}
            type="number"
            min={1}
            max={99}
            value={form.take}
            onChange={(e) => setForm({ ...form, take: Math.max(1, Number(e.target.value) || 1) })}
          />
        </Stack>
      </Flex>
      <Stack gap="2">
        <Text size="sm" weight="medium">
          {t("eachRowShows")}
        </Text>
        {form.columns.map((column, index) => (
          <ColumnRow
            key={index}
            column={column}
            onChange={(next) => setForm({ ...form, columns: form.columns.map((c, i) => (i === index ? next : c)) })}
            onRemove={() => setForm({ ...form, columns: form.columns.filter((_, i) => i !== index) })}
          />
        ))}
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() =>
            setForm({
              ...form,
              columns: [...form.columns, { field: "", label: "", upper: false, width: 5, cut: "pad" }],
            })
          }
        >
          <Plus aria-hidden />
          {t("addColumn")}
        </Button>
      </Stack>
      {form.columns.length > 0 && (
        <Stack gap="1" data-testid="column-budget">
          <TruncationMap
            columns={boardCols}
            title={t("columnBudget")}
            lines={[
              {
                row: 1,
                length: Math.min(budget.total, boardCols),
                ...(budget.fits
                  ? {}
                  : {
                      overflow: {
                        column: boardCols + 1,
                        count: budget.total - boardCols,
                        description: t("budgetOver", { count: budget.total - boardCols }),
                      },
                    }),
              },
            ]}
          />
          <Text size="xs" tone={budget.fits ? "success" : "destructive"} className="font-mono">
            {t(budget.fits ? "budgetFits" : "budgetOverflows", {
              sum: [...budget.widths].join(" + 1 + "),
              total: budget.total,
              cols: boardCols,
            })}
          </Text>
        </Stack>
      )}
      <TextField label={t("listEmpty")} value={form.empty} onChange={(empty) => setForm({ ...form, empty })} />
    </Stack>
  );
}

function RecipeFields({
  form,
  setForm,
  boardCols,
}: {
  form: RecipeForm;
  setForm: (f: RecipeForm) => void;
  boardCols: number;
}) {
  const t = useTranslations("formulaIde");
  const id = useId();
  switch (form.recipe) {
    case "list":
      return <ListRecipeForm form={form} setForm={setForm} boardCols={boardCols} />;
    case "either":
      return (
        <Stack gap="2">
          <TextField
            label={t("fieldCondition")}
            value={form.condition}
            onChange={(condition) => setForm({ ...form, condition })}
          />
          <TextField label={t("fieldThen")} value={form.then} onChange={(then) => setForm({ ...form, then })} />
          <TextField
            label={t("fieldOtherwise")}
            value={form.otherwise}
            onChange={(otherwise) => setForm({ ...form, otherwise })}
          />
        </Stack>
      );
    case "fallback":
      return (
        <Stack gap="2">
          <TextField label={t("fieldValue")} value={form.value} onChange={(value) => setForm({ ...form, value })} />
          <TextField
            label={t("fieldFallback")}
            value={form.fallback}
            onChange={(fallback) => setForm({ ...form, fallback })}
          />
        </Stack>
      );
    case "threshold":
      return (
        <Stack gap="2">
          <TextField label={t("fieldValue")} value={form.value} onChange={(value) => setForm({ ...form, value })} />
          <Stack gap="1">
            <Label htmlFor={`${id}-threshold`}>{t("fieldThreshold")}</Label>
            <Input
              id={`${id}-threshold`}
              type="number"
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
            />
          </Stack>
          <TextField label={t("fieldAbove")} value={form.above} onChange={(above) => setForm({ ...form, above })} />
          <TextField label={t("fieldBelow")} value={form.below} onChange={(below) => setForm({ ...form, below })} />
        </Stack>
      );
    case "countdown":
      return (
        <Stack gap="2">
          <TextField label={t("fieldWhen")} value={form.value} onChange={(value) => setForm({ ...form, value })} />
          <Stack gap="1">
            <Label htmlFor={`${id}-unit`}>{t("fieldUnit")}</Label>
            <Select value={form.unit} onValueChange={(unit) => setForm({ ...form, unit: unit as typeof form.unit })}>
              <SelectTrigger id={`${id}-unit`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="minutes">{t("unitMinutes")}</SelectItem>
                <SelectItem value="hours">{t("unitHours")}</SelectItem>
                <SelectItem value="days">{t("unitDays")}</SelectItem>
              </SelectContent>
            </Select>
          </Stack>
          <TextField label={t("fieldSuffix")} value={form.suffix} onChange={(suffix) => setForm({ ...form, suffix })} />
        </Stack>
      );
    case "date":
      return (
        <Stack gap="2">
          <TextField label={t("fieldDateValue")} value={form.value} onChange={(value) => setForm({ ...form, value })} />
          <TextField
            label={t("fieldPattern")}
            value={form.pattern}
            onChange={(pattern) => setForm({ ...form, pattern })}
          />
        </Stack>
      );
  }
}

/** Left column in Builder mode. */
export function FormulaBuilderCard(props: WorkbenchProps) {
  const { open, setOpen, formula, boardCols } = props;
  const t = useTranslations("formulaIde");
  const [recipe, setRecipe] = useState<RecipeId>("list");
  const [forms, setForms] = useState(DEFAULT_FORMS);
  const form = forms[recipe];
  const generated = buildRecipe(form);

  useEffect(() => {
    if (generated) setOpen((current) => (current ? { ...current, draft: generated } : current));
  }, [generated, setOpen]);

  if (!open) return null;
  return (
    <Card data-testid="formula-builder-card" className="gap-3 border-ring py-3">
      <CardContent className="px-4">
        <WorkbenchHeader line={formula?.line ?? null} tab="builder" setOpen={setOpen} />
        <Stack gap="3" className="mt-3">
          <ChoiceChipGroup
            aria-label={t("recipesLabel")}
            value={recipe}
            onValueChange={(v) => setRecipe(v as RecipeId)}
            className="flex-wrap"
          >
            {RECIPE_IDS.map((id) => (
              <ChoiceChip key={id} value={id} label={t(`recipe_${id}`)} />
            ))}
          </ChoiceChipGroup>
          <RecipeFields
            form={form}
            setForm={(next) => setForms((all) => ({ ...all, [next.recipe]: next }))}
            boardCols={boardCols}
          />
          <Flex align="center" justify="between" gap="2" wrap>
            <Text size="xs" tone="muted">
              {t("builderNote")}
            </Text>
            <Flex gap="2">
              <Button
                variant="ghost"
                onClick={() => {
                  open.cancel();
                  setOpen(null);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                disabled={!generated}
                onClick={() => {
                  open.apply(generated);
                  setOpen(null);
                }}
              >
                <Sigma aria-hidden />
                {t("updateFormula")}
              </Button>
            </Flex>
          </Flex>
        </Stack>
      </CardContent>
    </Card>
  );
}

/** Right column in Builder mode: "What the Builder wrote". */
export function GeneratedCodeCard({ open, setOpen }: WorkbenchProps) {
  const t = useTranslations("formulaIde");
  const text = open?.draft ?? open?.expression ?? "";
  return (
    <Card data-testid="generated-code" className="gap-2 py-4">
      <CardHeader className="px-4">
        <Flex align="center" justify="between" gap="2">
          <CardTitle as="h3" icon={<Code2 aria-hidden />}>
            {t("builderWrote")}
          </CardTitle>
          <Button variant="link" size="sm" onClick={() => setOpen((c) => (c ? { ...c, tab: "code" } : c))}>
            {t("editInCode")}
          </Button>
        </Flex>
      </CardHeader>
      <CardContent className="px-4">
        <Box className="rounded-lg border bg-muted/40 p-3">
          <Text as="p" size="sm" className="font-mono whitespace-pre-wrap" data-testid="generated-code-text">
            {text ? prettyPrint(text).text : t("builderEmpty")}
          </Text>
        </Box>
      </CardContent>
    </Card>
  );
}
