"use client";

import {
  Badge,
  Box,
  Button,
  Code,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Flex,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Check,
  Ellipsis,
  HelpCircle,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useDepsChanged } from "@/hooks/use-deps-changed";
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
  isLifted: boolean;
  actionsDisabled?: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onKeyDown: React.KeyboardEventHandler<HTMLDivElement>;
  result?: { value: string; error: string | null; message: string | null; matched: boolean };
  /** Returns true if the editor opened; false if blocked (e.g. dirty confirm cancelled). */
  onRequestEdit: () => boolean;
  onSave: (next: VariableRule) => void;
  onCancelEdit: () => void;
  onRemove: () => void;
  onDirtyChange: (dirty: boolean) => void;
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
  isLifted,
  actionsDisabled = false,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onKeyDown,
  result,
  onRequestEdit,
  onSave,
  onCancelEdit,
  onRemove,
  onDirtyChange,
  t,
}: VariableRuleRowProps) {
  const [draft, setDraft] = useState<VariableRule>(rule);
  const [knownVariables, setKnownVariables] = useState<Set<string>>(new Set());
  const [helpOpen, setHelpOpen] = useState(false);

  // When entering edit mode, snapshot the rule into the draft. Done during
  // render so the editor opens on the rule's values instead of the previous
  // row's for a frame (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([isEditing, rule]) && isEditing) {
    setDraft(rule);
  }

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
      id={`collection-rule-${index}`}
      tabIndex={isEditing ? undefined : 0}
      aria-label={t("ruleLabel", { number: index + 1 })}
      aria-describedby={!isEditing ? "collection-rule-instructions" : undefined}
      onKeyDown={onKeyDown}
      className={cn(
        "rounded-xl border bg-card p-3.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isEditing && "space-y-2",
        isLifted && "ring-2 ring-primary bg-accent",
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
                aria-label={`${t("variableRuleSave")} ${t("ruleLabel", { number: index + 1 })}`}
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
                {/* Operator cheat-sheet: formula syntax, identical in every locale. */}
                <Text size="xs" tone="muted" className="font-mono">
                  <Code className="bg-transparent px-0 py-0 text-xs text-muted-foreground">
                    ==, =, !=, &lt;&gt;, &lt;, &gt;, &lt;=, &gt;= · AND OR NOT (or &amp;&amp; || !) · + - * / %
                  </Code>
                </Text>
              </Box>
              <Box>
                <Text size="xs" weight="medium" className="mb-1">
                  {t("variableRuleHelpFunctionsTitle")}
                </Text>
                {/* Function cheat-sheet: formula syntax, identical in every locale. */}
                <Text size="xs" tone="muted" className="font-mono">
                  <Code className="bg-transparent px-0 py-0 text-xs text-muted-foreground">
                    IF(cond, then, else) · AND(a, b) · OR(a, b) · CONTAINS(s, sub) · STARTSWITH · LEN · UPPER · LOWER
                  </Code>
                </Text>
              </Box>
              <Box>
                <Text size="xs" weight="medium" className="mb-1">
                  {t("variableRuleHelpExamplesTitle")}
                </Text>
                <Flex gap="1.5" className="flex-wrap">
                  {EXAMPLE_EXPRESSIONS.map((ex) => (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      key={ex}
                      onClick={() => insertExpressionAtCursor(ex)}
                      className="font-mono"
                    >
                      {ex}
                    </Button>
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
            <SelectTrigger
              aria-label={`${t("ruleLabel", { number: index + 1 })} · ${t("variableRuleTargetPlaceholder")}`}
            >
              <SelectValue placeholder={t("variableRuleTargetPlaceholder")}>
                {draft.page_id ? pageName(draft.page_id) : undefined}
              </SelectValue>
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
        <Stack gap="2">
          <Flex align="center" gap="2" wrap>
            <Badge variant="outline">{t("ruleLabel", { number: index + 1 })}</Badge>
            <Text size="sm" tone="muted">
              {t("ruleWhen")}
            </Text>
            {/* The whole expression, wrapping, not a one-line field that
                hid `= "Saturday"` at phone width (BB-B-26). Opens the editor. */}
            <Button
              type="button"
              variant="outline"
              disabled={actionsDisabled}
              aria-label={t("variableExpressionAriaLabel", { index: index + 1 })}
              onClick={() => onRequestEdit()}
              className="h-auto min-h-9 min-w-32 flex-[1_1_10rem] justify-start whitespace-normal break-words py-1.5 text-left font-mono text-sm font-normal"
            >
              {summaryExpression}
            </Button>
            <Text size="sm" tone="muted">
              {t("ruleShow")}
            </Text>
            <Text size="sm" className="min-w-24 flex-1">
              {summaryTarget}
            </Text>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={actionsDisabled}
                  aria-label={t("ruleActions", { number: index + 1 })}
                >
                  <Ellipsis aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onRequestEdit()}>
                  <Pencil aria-hidden="true" />
                  {t("variableRuleEdit", { index: index + 1 })}
                </DropdownMenuItem>
                <DropdownMenuItem disabled={!canMoveUp} onClick={onMoveUp}>
                  <ArrowUp aria-hidden="true" />
                  {t("moveRuleUp", { number: index + 1 })}
                </DropdownMenuItem>
                <DropdownMenuItem disabled={!canMoveDown} onClick={onMoveDown}>
                  <ArrowDown aria-hidden="true" />
                  {t("moveRuleDown", { number: index + 1 })}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={onRemove}>
                  <Trash2 aria-hidden="true" />
                  {t("variableRemoveRule")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </Flex>
          {result && (
            <Flex gap="2" align="center">
              <Badge variant={result.error ? "destructive" : "formula"}>{result.value}</Badge>
              <Text size="xs" tone={result.error ? "destructive" : "muted"}>
                {result.message || t("savedRuleResult")}
              </Text>
            </Flex>
          )}
        </Stack>
      )}
    </Box>
  );
}
