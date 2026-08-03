"use client";

import {
  Badge,
  Box,
  Button,
  Flex,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { AlertCircle, Check, GripVertical, HelpCircle, Pencil, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { VariableRule } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  extractReferencedVariables,
  lintExpression,
  VariableAutocompleteTextarea,
} from "./variable-autocomplete-textarea";

const EXAMPLE_EXPRESSIONS = [
  "date_time.hour >= 17",
  'date_time.day_of_week == "Saturday"',
  "IF(weather.temp > 80, 1, 0)",
];

interface VariableRuleRowProps {
  rule: VariableRule;
  index: number;
  pages: Array<{ id: string; name: string }>;
  selectablePageIds: string[];
  isEditing: boolean;
  isDragging: boolean;
  /** Returns true if the editor opened; false if blocked (e.g. dirty confirm cancelled). */
  onRequestEdit: () => boolean;
  onSave: (next: VariableRule) => void;
  onCancelEdit: () => void;
  onRemove: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  /** Translations passed in to avoid re-fetching the namespace per row. */
  t: (key: string, params?: Record<string, string | number>) => string;
}

function rulesDiffer(a: VariableRule, b: VariableRule): boolean {
  return a.expression !== b.expression || a.page_id !== b.page_id;
}

export function VariableRuleRow({
  rule,
  index,
  pages,
  selectablePageIds,
  isEditing,
  isDragging,
  onRequestEdit,
  onSave,
  onCancelEdit,
  onRemove,
  onDirtyChange,
  onDragStart,
  onDragOver,
  onDragEnd,
  t,
}: VariableRuleRowProps) {
  const [draft, setDraft] = useState<VariableRule>(rule);
  const [knownVariables, setKnownVariables] = useState<Set<string>>(new Set());
  const [helpOpen, setHelpOpen] = useState(false);

  // When entering edit mode, snapshot the rule into the draft.
  useEffect(() => {
    if (isEditing) setDraft(rule);
  }, [isEditing, rule]);

  // Report dirty state to parent so it can prompt before switching rules.
  useEffect(() => {
    onDirtyChange(isEditing && rulesDiffer(draft, rule));
  }, [isEditing, draft, rule, onDirtyChange]);

  const pageName = (id: string): string => pages.find((p) => p.id === id)?.name || id;
  const summaryExpression = rule.expression.trim() || t("variableExpressionEmpty");
  const summaryTarget = rule.page_id ? pageName(rule.page_id) : t("variableRuleTargetPlaceholder");

  // Validation
  const trimmedExpr = draft.expression.trim();
  const referencedVars = useMemo(() => extractReferencedVariables(draft.expression), [draft.expression]);
  const unknownVars = useMemo(
    () => (knownVariables.size === 0 ? [] : referencedVars.filter((tok) => !knownVariables.has(tok))),
    [knownVariables, referencedVars],
  );
  const lintFindings = useMemo(() => lintExpression(draft.expression), [draft.expression]);
  const expressionMissing = trimmedExpr.length === 0;
  const targetMissing = draft.page_id.length === 0;
  const hasUnknownVars = unknownVars.length > 0;
  const canSave = !expressionMissing && !targetMissing;

  const applyLintFix = (finding: (typeof lintFindings)[number]) => {
    if (!finding.autoFix) return;
    setDraft((d) => ({ ...d, expression: finding.autoFix!(d.expression) }));
  };

  const insertExpressionAtCursor = (snippet: string) => {
    setDraft((d) => ({ ...d, expression: d.expression.length > 0 ? `${d.expression} ${snippet}` : snippet }));
  };

  return (
    <Box
      draggable={!isEditing}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      className={cn(
        "rounded-lg border bg-background",
        isEditing ? "p-3 space-y-2" : "p-2.5",
        !isEditing && "cursor-grab active:cursor-grabbing",
        isDragging && "opacity-50",
      )}
    >
      {isEditing ? (
        <>
          <Flex align="center" justify="between" gap="2">
            <Flex align="center" gap="1">
              <Text as="span" size="xs" tone="muted">
                {t("variableRuleEditingLabel", { index: index + 1 })}
              </Text>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => setHelpOpen((v) => !v)}
                aria-label={t("variableRuleSyntaxHelp")}
                aria-expanded={helpOpen}
              >
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </Flex>
            <Flex align="center" gap="1">
              <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onCancelEdit}>
                <X className="h-3.5 w-3.5 mr-1" />
                {t("variableRuleCancel")}
              </Button>
              <Button
                type="button"
                variant="default"
                size="sm"
                className="h-7 px-2"
                disabled={!canSave}
                onClick={() => onSave(draft)}
              >
                <Check className="h-3.5 w-3.5 mr-1" />
                {t("variableRuleSave")}
              </Button>
            </Flex>
          </Flex>
          {helpOpen && (
            <Stack gap="2" className="rounded-md border border-dashed bg-muted/40 p-2.5 text-xs">
              <Box>
                <Text size="xs" weight="medium" className="mb-1">
                  {t("variableRuleHelpOperatorsTitle")}
                </Text>
                <Text size="xs" tone="muted" className="font-mono">
                  ==, =, !=, &lt;&gt;, &lt;, &gt;, &lt;=, &gt;= · AND OR NOT (or &amp;&amp; || !) · + - * / %
                </Text>
              </Box>
              <Box>
                <Text size="xs" weight="medium" className="mb-1">
                  {t("variableRuleHelpFunctionsTitle")}
                </Text>
                <Text size="xs" tone="muted" className="font-mono">
                  IF(cond, then, else) · AND(a, b) · OR(a, b) · CONTAINS(s, sub) · STARTSWITH · LEN · UPPER · LOWER
                </Text>
              </Box>
              <Box>
                <Text size="xs" weight="medium" className="mb-1">
                  {t("variableRuleHelpExamplesTitle")}
                </Text>
                <Flex gap="1.5" className="flex-wrap">
                  {EXAMPLE_EXPRESSIONS.map((ex) => (
                    <button
                      type="button"
                      key={ex}
                      onClick={() => insertExpressionAtCursor(ex)}
                      className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] hover:bg-accent"
                    >
                      {ex}
                    </button>
                  ))}
                </Flex>
              </Box>
            </Stack>
          )}
          <VariableAutocompleteTextarea
            value={draft.expression}
            onChange={(v) => setDraft((d) => ({ ...d, expression: v }))}
            onKnownVariablesChange={setKnownVariables}
            placeholder={t("variableExpressionPlaceholder")}
            ariaLabel={t("variableExpressionAriaLabel", { index: index + 1 })}
          />
          {lintFindings.map((f) => (
            <Flex key={f.kind} align="start" gap="1.5" className="text-xs text-amber-600 dark:text-amber-400">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
              <Text as="span" size="xs" className="flex-1 text-amber-600 dark:text-amber-400">
                {f.message}
              </Text>
              {f.autoFix && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => applyLintFix(f)}
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  {t("variableRuleApplyFix")}
                </Button>
              )}
            </Flex>
          ))}
          {hasUnknownVars && (
            <Flex align="start" gap="1.5" className="text-xs text-amber-600 dark:text-amber-400">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
              <Text as="span" size="xs" className="text-amber-600 dark:text-amber-400">
                {t("variableRuleUnknownVars", { vars: unknownVars.slice(0, 3).join(", ") })}
              </Text>
            </Flex>
          )}
          <Select value={draft.page_id} onValueChange={(v) => setDraft((d) => ({ ...d, page_id: v }))}>
            <SelectTrigger>
              <SelectValue placeholder={t("variableRuleTargetPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {selectablePageIds.map((pid) => (
                <SelectItem key={pid} value={pid}>
                  {pageName(pid)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </>
      ) : (
        <Flex align="center" gap="2">
          <GripVertical className="h-4 w-4 text-muted-foreground flex-shrink-0" aria-hidden />
          <Badge variant="outline" className="text-xs tabular-nums flex-shrink-0">
            {index + 1}
          </Badge>
          <Box className="flex-1 min-w-0">
            <Text size="xs" className="font-mono truncate">
              {summaryExpression}
            </Text>
            <Text size="xs" tone="muted" className="truncate">
              {t("variableRuleSummaryArrow", { target: summaryTarget })}
            </Text>
          </Box>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 flex-shrink-0"
            onClick={() => onRequestEdit()}
            aria-label={t("variableRuleEdit", { index: index + 1 })}
          >
            <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 flex-shrink-0"
            onClick={onRemove}
            aria-label={t("variableRemoveRule")}
          >
            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        </Flex>
      )}
    </Box>
  );
}
