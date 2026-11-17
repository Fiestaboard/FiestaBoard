import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  arrayMove,
  Badge,
  Box,
  Button,
  Card,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Flex,
  Heading,
  Input,
  Label,
  SegmentedControl,
  SegmentedControlItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { ChevronLeft, Clock, Plus, Send, Trash2 } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { CollectionPageList } from "@/components/collection-page-list";
import { VariableRuleRow } from "@/components/variable-rule-row";
import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { useLocale, useTranslations } from "@/i18n/translations";
import type {
  Collection,
  CollectionCreate,
  CollectionSelectionMode,
  CollectionUpdate,
  Page,
  VariableRule,
} from "@/lib/api";
import { collectionCapabilities } from "@/lib/api";

// Page-duration bounds. These mirror MIN_INTERVAL_SECONDS / MAX_INTERVAL_SECONDS
// in src/collections/models.py — the server rejects anything outside them, so
// the form validates locally rather than round-tripping a 422.
const MIN_INTERVAL_SECONDS = 5;
const MAX_INTERVAL_SECONDS = 86400; // 24 hours

/** Sentinel Select value that switches the duration field into custom entry. */
const CUSTOM_INTERVAL = "custom";

const INTERVAL_PRESETS = [
  { labelKey: "interval5s", value: 5 },
  { labelKey: "interval10s", value: 10 },
  { labelKey: "interval15s", value: 15 },
  { labelKey: "interval30s", value: 30 },
  { labelKey: "interval1m", value: 60 },
  { labelKey: "interval2m", value: 120 },
  { labelKey: "interval5m", value: 300 },
  { labelKey: "interval10m", value: 600 },
  { labelKey: "interval15m", value: 900 },
  { labelKey: "interval30m", value: 1800 },
  { labelKey: "interval45m", value: 2700 },
  { labelKey: "interval1h", value: 3600 },
  { labelKey: "interval2h", value: 7200 },
  { labelKey: "interval4h", value: 14400 },
  { labelKey: "interval8h", value: 28800 },
  { labelKey: "interval12h", value: 43200 },
  { labelKey: "interval24h", value: 86400 },
];

export type IntervalUnit = "seconds" | "minutes" | "hours";

const UNIT_SECONDS: Record<IntervalUnit, number> = {
  seconds: 1,
  minutes: 60,
  hours: 3600,
};

const UNIT_OPTIONS: { value: IntervalUnit; labelKey: string }[] = [
  { value: "seconds", labelKey: "unitSeconds" },
  { value: "minutes", labelKey: "unitMinutes" },
  { value: "hours", labelKey: "unitHours" },
];

function isPresetInterval(seconds: number): boolean {
  return INTERVAL_PRESETS.some((p) => p.value === seconds);
}

/**
 * Express a duration in the largest unit that divides it exactly, so an
 * existing 5400s collection reopens as "90 minutes" rather than "5400 seconds".
 */
export function splitInterval(seconds: number): { amount: number; unit: IntervalUnit } {
  if (seconds > 0 && seconds % UNIT_SECONDS.hours === 0) {
    return { amount: seconds / UNIT_SECONDS.hours, unit: "hours" };
  }
  if (seconds > 0 && seconds % UNIT_SECONDS.minutes === 0) {
    return { amount: seconds / UNIT_SECONDS.minutes, unit: "minutes" };
  }
  return { amount: seconds, unit: "seconds" };
}

/**
 * Convert a raw custom-entry amount into seconds. Returns null when the entry
 * is not a whole number or falls outside the server-accepted range.
 */
export function parseCustomInterval(amount: string, unit: IntervalUnit): number | null {
  const trimmed = amount.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const seconds = Number(trimmed) * UNIT_SECONDS[unit];
  if (!Number.isSafeInteger(seconds)) return null;
  if (seconds < MIN_INTERVAL_SECONDS || seconds > MAX_INTERVAL_SECONDS) return null;
  return seconds;
}

const POLL_PRESETS = [
  { labelKey: "interval5s", value: 5 },
  { labelKey: "interval10s", value: 10 },
  { labelKey: "interval15s", value: 15 },
  { labelKey: "interval30s", value: 30 },
  { labelKey: "interval1m", value: 60 },
];

export function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

interface CollectionFormProps {
  collection?: Collection;
  pages: Page[];
  onSubmit: (data: CollectionCreate | CollectionUpdate) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  onShowNow?: () => void;
  onTestAtTime?: () => void;
  preview?: (dirty: boolean) => ReactNode;
  ruleResults?: Array<{ index: number; value: string; error: string | null; message: string | null; matched: boolean }>;
}

export function CollectionForm({
  collection,
  pages,
  onSubmit,
  onCancel,
  onDelete,
  onDirtyChange,
  onShowNow,
  onTestAtTime,
  preview,
  ruleResults,
}: CollectionFormProps) {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const locale = useLocale();
  const durationLabel = (seconds: number) => {
    const { amount, unit } = splitInterval(seconds);
    return new Intl.NumberFormat(locale, { style: "unit", unit: unit.slice(0, -1), unitDisplay: "short" }).format(
      amount,
    );
  };
  const isEdit = Boolean(collection);

  const [name, setName] = useState(collection?.name || "");
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>(collection?.page_ids || []);
  const [selectionMode, setSelectionMode] = useState<CollectionSelectionMode>(collection?.selection_mode || "time");
  // A collection saved with a custom duration (or one saved before a preset was
  // removed) must reopen in custom mode showing its real value — snapping it to
  // the nearest preset would silently rewrite the user's setting on save.
  const initialInterval =
    collection?.selection_mode === "random"
      ? collection?.random?.interval_seconds || 30
      : collection?.time?.interval_seconds || 30;
  const initialCustomEntry = splitInterval(initialInterval);

  const [intervalSeconds, setIntervalSeconds] = useState(initialInterval);
  const [isCustomInterval, setIsCustomInterval] = useState(() => !isPresetInterval(initialInterval));
  const [customAmount, setCustomAmount] = useState(String(initialCustomEntry.amount));
  const [customUnit, setCustomUnit] = useState<IntervalUnit>(initialCustomEntry.unit);
  const [rules, setRules] = useState<VariableRule[]>(collection?.variable?.rules || []);
  const [defaultPageId, setDefaultPageId] = useState<string>(collection?.variable?.default_page_id || "");
  const [pollSeconds, setPollSeconds] = useState(collection?.variable?.poll_seconds || 10);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const coarsePointer = useCoarsePointer();

  // Rule-editor state: only one rule is editable at a time.
  const [editingRuleIndex, setEditingRuleIndex] = useState<number | null>(null);
  const [editingRuleDirty, setEditingRuleDirty] = useState(false);
  const [pendingSwitchIndex, setPendingSwitchIndex] = useState<number | null>(null);
  // Track a freshly-added rule so we can drop it from the list if the user cancels
  // without ever saving.
  const [newRuleIndex, setNewRuleIndex] = useState<number | null>(null);
  const [liftedRule, setLiftedRule] = useState<number | null>(null);
  const [ruleOrderBeforeLift, setRuleOrderBeforeLift] = useState<VariableRule[]>([]);
  const [ruleAnnouncement, setRuleAnnouncement] = useState("");
  useLayoutEffect(() => {
    if (liftedRule !== null) document.getElementById(`collection-rule-${liftedRule}`)?.focus();
  }, [liftedRule]);

  const snapshot = JSON.stringify({
    name,
    selectedPageIds,
    selectionMode,
    intervalSeconds,
    isCustomInterval,
    customAmount,
    customUnit,
    defaultPageId,
    rules,
    pollSeconds,
  });
  const [initialSnapshot] = useState(snapshot);
  const dirty = snapshot !== initialSnapshot || editingRuleDirty || newRuleIndex !== null;
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  // SortableList is controlled: each keyboard step, Move up / Move down and
  // pointer drop lands here as one move.
  const handleMovePage = useCallback((from: number, to: number) => {
    setSelectedPageIds((prev) => arrayMove(prev, from, to));
  }, []);

  const availablePages = useMemo(() => pages.filter((p) => !selectedPageIds.includes(p.id)), [pages, selectedPageIds]);

  const handleAddPage = useCallback(
    (pageId: string) => {
      if (!selectedPageIds.includes(pageId)) {
        setSelectedPageIds((prev) => [...prev, pageId]);
      }
    },
    [selectedPageIds],
  );

  const handleRemovePage = useCallback(
    (index: number) => {
      setSelectedPageIds((prev) => {
        const removed = prev[index];
        const next = prev.filter((_, i) => i !== index);
        // Drop any variable-mode references to the removed page so we don't
        // leave dangling rules or a default that points at a non-member.
        if (removed === defaultPageId) {
          setDefaultPageId("");
        }
        setRules((rs) => rs.filter((r) => r.page_id !== removed));
        // Editing state may now point at a removed rule — reset to be safe.
        setEditingRuleIndex(null);
        setEditingRuleDirty(false);
        setNewRuleIndex(null);
        return next;
      });
    },
    [defaultPageId],
  );

  const handleAddRule = useCallback(() => {
    // Opening a fresh rule counts as a "switch" too; if the current edit is
    // dirty, ask before discarding.
    if (editingRuleIndex !== null && editingRuleDirty) {
      setPendingSwitchIndex(-1); // sentinel: -1 means "open a new rule after discard"
      return;
    }
    setRules((prev) => {
      const idx = prev.length;
      setEditingRuleIndex(idx);
      setNewRuleIndex(idx);
      return [...prev, { expression: "", page_id: "" }];
    });
  }, [editingRuleIndex, editingRuleDirty]);

  const handleRequestEditRule = useCallback(
    (index: number): boolean => {
      if (editingRuleIndex === index) return true;
      if (editingRuleIndex !== null && editingRuleDirty) {
        setPendingSwitchIndex(index);
        return false;
      }
      setEditingRuleIndex(index);
      return true;
    },
    [editingRuleIndex, editingRuleDirty],
  );

  const handleSaveRule = useCallback((index: number, next: VariableRule) => {
    setRules((prev) => prev.map((r, i) => (i === index ? next : r)));
    setEditingRuleIndex(null);
    setEditingRuleDirty(false);
    setNewRuleIndex((n) => (n === index ? null : n));
  }, []);

  const handleCancelEditRule = useCallback(() => {
    // If cancelling a never-saved fresh rule, drop it from the list entirely.
    if (newRuleIndex !== null && newRuleIndex === editingRuleIndex) {
      const idx = newRuleIndex;
      setRules((prev) => prev.filter((_, i) => i !== idx));
      setNewRuleIndex(null);
    }
    setEditingRuleIndex(null);
    setEditingRuleDirty(false);
  }, [newRuleIndex, editingRuleIndex]);

  const handleRemoveRule = useCallback(
    (index: number) => {
      setRules((prev) => prev.filter((_, i) => i !== index));
      setNewRuleIndex((current) =>
        current === null || current < index ? current : current === index ? null : current - 1,
      );
      // If we removed the rule currently being edited, exit edit mode.
      if (editingRuleIndex === index) {
        setEditingRuleIndex(null);
        setEditingRuleDirty(false);
      } else if (editingRuleIndex !== null && index < editingRuleIndex) {
        setEditingRuleIndex(editingRuleIndex - 1);
      }
    },
    [editingRuleIndex],
  );

  const handleConfirmDiscardSwitch = useCallback(() => {
    if (pendingSwitchIndex === null) return;
    const target = pendingSwitchIndex;
    // Drop the unsaved fresh rule (if any) before switching.
    if (newRuleIndex !== null && newRuleIndex === editingRuleIndex) {
      const droppedIdx = newRuleIndex;
      setRules((prev) => prev.filter((_, i) => i !== droppedIdx));
      setNewRuleIndex(null);
      // If user wanted to open another existing rule whose index shifts after drop:
      if (target >= 0 && target > droppedIdx) {
        setEditingRuleIndex(target - 1);
      } else if (target === -1) {
        // open a brand-new rule at the end (after drop)
        setRules((prev) => {
          const idx = prev.length;
          setEditingRuleIndex(idx);
          setNewRuleIndex(idx);
          return [...prev, { expression: "", page_id: "" }];
        });
      } else {
        setEditingRuleIndex(target);
      }
    } else if (target === -1) {
      setRules((prev) => {
        const idx = prev.length;
        setEditingRuleIndex(idx);
        setNewRuleIndex(idx);
        return [...prev, { expression: "", page_id: "" }];
      });
    } else {
      setEditingRuleIndex(target);
    }
    setEditingRuleDirty(false);
    setPendingSwitchIndex(null);
  }, [pendingSwitchIndex, newRuleIndex, editingRuleIndex]);

  const handleCancelDiscardSwitch = useCallback(() => {
    setPendingSwitchIndex(null);
  }, []);

  const moveRule = useCallback(
    (fromIndex: number, targetIndex: number) => {
      // Rule editors are keyed by position; protect a live expression draft.
      if (editingRuleDirty || fromIndex === targetIndex || targetIndex < 0 || targetIndex >= rules.length) return;
      setRules((prev) => {
        const next = [...prev];
        const [moved] = next.splice(fromIndex, 1);
        next.splice(targetIndex, 0, moved);
        return next;
      });
      const movedIndex = (index: number | null) => {
        if (index === null) return null;
        if (index === fromIndex) return targetIndex;
        if (fromIndex < index && index <= targetIndex) return index - 1;
        if (targetIndex <= index && index < fromIndex) return index + 1;
        return index;
      };
      setNewRuleIndex(movedIndex);
      setEditingRuleIndex(movedIndex);
    },
    [editingRuleDirty, rules.length],
  );

  // The duration control only exists in time and random mode; a half-typed
  // custom value must not block saving a variable-mode collection, whose
  // rotation is driven by rules rather than by a page duration.
  const durationModeActive = selectionMode === "time" || selectionMode === "random";
  const customIntervalActive = durationModeActive && isCustomInterval;
  const customIntervalSeconds = useMemo(
    () => (customIntervalActive ? parseCustomInterval(customAmount, customUnit) : null),
    [customIntervalActive, customAmount, customUnit],
  );
  const customIntervalInvalid = customIntervalActive && customIntervalSeconds === null;
  const resolvedIntervalSeconds = customIntervalActive ? customIntervalSeconds : intervalSeconds;

  const handleIntervalChange = useCallback(
    (value: string) => {
      if (!value) return;
      if (value === CUSTOM_INTERVAL) {
        const entry = splitInterval(intervalSeconds);
        setCustomAmount(String(entry.amount));
        setCustomUnit(entry.unit);
        setIsCustomInterval(true);
        return;
      }
      setIsCustomInterval(false);
      setIntervalSeconds(Number(value));
    },
    [intervalSeconds],
  );

  const hasUnsavedRule =
    selectionMode === "variable" && (editingRuleDirty || newRuleIndex !== null || liftedRule !== null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (hasUnsavedRule) {
      toast.error(t("variableSaveOrCancelRule"));
      return;
    }
    if (!name.trim() || selectedPageIds.length === 0) return;
    if (resolvedIntervalSeconds === null) {
      toast.error(t("customDurationError"));
      return;
    }
    if (selectionMode === "variable") {
      if (!defaultPageId) {
        toast.error(t("variableDefaultRequired"));
        return;
      }
      if (rules.some((r) => !r.expression.trim() || !r.page_id)) {
        toast.error(t("variableRulesIncomplete"));
        return;
      }
    }
    setIsSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        page_ids: selectedPageIds,
        selection_mode: selectionMode,
        time: { interval_seconds: resolvedIntervalSeconds },
        variable:
          selectionMode === "variable"
            ? {
                rules,
                default_page_id: defaultPageId,
                poll_seconds: pollSeconds,
              }
            : null,
        random: selectionMode === "random" ? { interval_seconds: resolvedIntervalSeconds } : null,
      });
    } catch {
      setIsSubmitting(false);
    }
  };

  const canSubmit =
    name.trim().length > 0 &&
    selectedPageIds.length >= 1 &&
    !customIntervalInvalid &&
    !hasUnsavedRule &&
    (selectionMode !== "variable" ||
      (defaultPageId.length > 0 && rules.every((r) => r.expression.trim().length > 0 && r.page_id.length > 0)));

  return (
    <Box as="form" onSubmit={handleSubmit} className="space-y-5 min-w-0">
      <Flex align="center" gap="3" wrap>
        <Button type="button" variant="ghost" size={coarsePointer ? "touch" : "default"} onClick={onCancel}>
          <ChevronLeft aria-hidden="true" />
          {t("title")}
        </Button>
        <Stack gap="0.5" className="flex-1 min-w-40">
          <Heading level={1} size="2xl">
            {name || t(isEdit ? "editCollection" : "newCollection")}
          </Heading>
          <Text size="xs" tone="muted" className="font-mono uppercase">
            {t("editorMeta", { count: selectedPageIds.length })} ·{" "}
            {selectionMode === "variable"
              ? t("ruleCount", { count: rules.length })
              : t(selectionMode === "random" ? "randomEvery" : "rotationTotal", {
                  duration: durationLabel(
                    (resolvedIntervalSeconds ?? intervalSeconds) *
                      (selectionMode === "time" ? selectedPageIds.length : 1),
                  ),
                })}
          </Text>
        </Stack>
        <Flex gap="2" wrap>
          {isEdit && onDelete && (
            <Button type="button" variant="ghost" onClick={onDelete} disabled={isSubmitting}>
              <Trash2 aria-hidden="true" />
              {t("deleteAction")}
            </Button>
          )}
          {isEdit && onShowNow && (
            <Button type="button" variant="outline" onClick={onShowNow} disabled={dirty || isSubmitting}>
              <Send aria-hidden="true" />
              {t("showNowAction")}
            </Button>
          )}
          <Button type="submit" loading={isSubmitting} disabled={!canSubmit || isSubmitting}>
            {isEdit ? tc("save") : t("createCollection")}
          </Button>
        </Flex>
      </Flex>
      <Box className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,405px)]">
        {preview && <Box className="min-w-0 lg:col-start-2 lg:row-start-1">{preview(dirty)}</Box>}
        <Card className="min-w-0 p-4 md:p-6 lg:col-start-1 lg:row-start-1">
          <Stack gap="5">
            {/* Name */}
            <Stack gap="2">
              <Label htmlFor="collection-name">{t("editorNameLabel")}</Label>
              <Input
                className="max-w-[260px]"
                id="collection-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("namePlaceholder")}
                maxLength={100}
              />
            </Stack>

            {/* Selection mode */}
            <Stack gap="2">
              <Label id="collection-mode-label">{t("selectionModeLabel")}</Label>
              <SegmentedControl
                aria-labelledby="collection-mode-label"
                value={selectionMode}
                onValueChange={(v) => {
                  if (v) setSelectionMode(v as CollectionSelectionMode);
                }}
                wrap
                className="max-w-full"
                size={coarsePointer ? "touch" : "md"}
              >
                <SegmentedControlItem value="time">{t("modeTimeLabel")}</SegmentedControlItem>
                <SegmentedControlItem value="random">{t("modeRandomLabel")}</SegmentedControlItem>
                <SegmentedControlItem value="variable">{t("modeVariableLabel")}</SegmentedControlItem>
              </SegmentedControl>
            </Stack>

            {/* Page-duration controls (time + random modes) */}
            {(selectionMode === "time" || selectionMode === "random") && (
              <Stack gap="2">
                <Label htmlFor="collection-interval">
                  {t(selectionMode === "random" ? "changeEvery" : "pageDurationLabel")}
                </Label>
                <Text size="xs" tone="muted">
                  {selectionMode === "random" ? t("randomDurationDescription") : t("pageDurationDescription")}
                </Text>
                <Select
                  value={isCustomInterval ? CUSTOM_INTERVAL : String(intervalSeconds)}
                  onValueChange={handleIntervalChange}
                >
                  <SelectTrigger id="collection-interval">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {INTERVAL_PRESETS.map((p) => (
                      <SelectItem key={p.value} value={String(p.value)}>
                        {t(p.labelKey)}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_INTERVAL}>{t("intervalCustom")}</SelectItem>
                  </SelectContent>
                </Select>

                {isCustomInterval && (
                  <Flex gap="2" align="end" className="flex-wrap">
                    <Stack gap="1" className="flex-1 min-w-[7rem]">
                      <Label htmlFor="collection-interval-amount">{t("customDurationLabel")}</Label>
                      <Input
                        id="collection-interval-amount"
                        type="number"
                        inputMode="numeric"
                        min={1}
                        value={customAmount}
                        onChange={(e) => setCustomAmount(e.target.value)}
                        aria-invalid={customIntervalInvalid || undefined}
                        aria-describedby={customIntervalInvalid ? "collection-interval-error" : undefined}
                      />
                    </Stack>
                    <Stack gap="1" className="w-40">
                      <Label htmlFor="collection-interval-unit">{t("customDurationUnitLabel")}</Label>
                      <Select value={customUnit} onValueChange={(v) => v && setCustomUnit(v as IntervalUnit)}>
                        <SelectTrigger id="collection-interval-unit">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {UNIT_OPTIONS.map((u) => (
                            <SelectItem key={u.value} value={u.value}>
                              {t(u.labelKey)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Stack>
                  </Flex>
                )}
                {isCustomInterval &&
                  (customIntervalInvalid ? (
                    <Text id="collection-interval-error" size="xs" tone="destructive" role="alert">
                      {t("customDurationError")}
                    </Text>
                  ) : (
                    <Text size="xs" tone="muted">
                      {t("customDurationResolved", { duration: formatInterval(customIntervalSeconds ?? 0) })}
                    </Text>
                  ))}
              </Stack>
            )}

            {selectionMode !== "variable" && (
              <>
                {/* Selected Pages (reorderable) */}
                <Stack gap="2">
                  <Label>{t("pagesInCollection")}</Label>
                  <Text size="xs" tone="muted">
                    {/* The hint follows the pointer, like the rows (DD-W27): touch copy for a
              finger at any width, the keyboard copy for a mouse or trackpad. */}
                    {selectionMode === "time"
                      ? t(coarsePointer ? "dragToReorderTouch" : "dragToReorder")
                      : selectionMode === "random"
                        ? t("randomMembershipHint")
                        : t("variableMembershipHint")}
                  </Text>

                  {selectedPageIds.length === 0 ? (
                    <Text tone="muted" className="border border-dashed rounded-lg p-4 text-center">
                      {t("noPagesAdded")}
                    </Text>
                  ) : (
                    <CollectionPageList
                      pageIds={selectedPageIds}
                      pages={pages}
                      mode={selectionMode}
                      onMove={handleMovePage}
                      onRemove={handleRemovePage}
                    />
                  )}

                  {availablePages.length > 0 && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button type="button" variant="outline" className="self-start">
                          <Plus aria-hidden="true" />
                          {t("addPageAction")}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start">
                        {availablePages.map((page) => (
                          <DropdownMenuItem key={page.id} onClick={() => handleAddPage(page.id)}>
                            {page.name}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                  {selectionMode === "random" && !collectionCapabilities.editableNoRepeat && (
                    <Text size="xs" tone="muted">
                      {t("randomNoRepeatFixed")}
                    </Text>
                  )}
                </Stack>
              </>
            )}
            {/* Variable-mode controls */}
            {selectionMode === "variable" && (
              <Stack gap="4" className="">
                <Stack gap="2">
                  <Label>{t("variableRulesLabel")}</Label>
                  <Text id="collection-rule-instructions" size="xs" tone="muted">
                    {t("sortInstructions")}
                  </Text>
                  <Text size="xs" tone="muted">
                    {t("variableRulesDescription")}
                  </Text>

                  {rules.length === 0 ? (
                    <Text tone="muted" className="border border-dashed rounded-lg p-4 text-center">
                      {t("variableNoRules")}
                    </Text>
                  ) : (
                    <Stack gap="2.5">
                      {rules.map((rule, index) => (
                        <VariableRuleRow
                          key={index}
                          rule={rule}
                          index={index}
                          pages={pages}
                          selectablePageIds={selectedPageIds}
                          isEditing={editingRuleIndex === index}
                          isLifted={liftedRule === index}
                          onRequestEdit={() => handleRequestEditRule(index)}
                          onSave={(next) => handleSaveRule(index, next)}
                          onCancelEdit={handleCancelEditRule}
                          onRemove={() => handleRemoveRule(index)}
                          onDirtyChange={(dirty) => {
                            if (editingRuleIndex === index) setEditingRuleDirty(dirty);
                          }}
                          canMoveUp={!editingRuleDirty && liftedRule === null && index > 0}
                          canMoveDown={!editingRuleDirty && liftedRule === null && index < rules.length - 1}
                          onMoveUp={() => moveRule(index, index - 1)}
                          onMoveDown={() => moveRule(index, index + 1)}
                          result={!dirty ? ruleResults?.find((r) => r.index === index) : undefined}
                          onKeyDown={(event) => {
                            if (
                              event.target !== event.currentTarget ||
                              editingRuleDirty ||
                              editingRuleIndex !== null ||
                              newRuleIndex !== null
                            )
                              return;
                            if (event.key === " " && liftedRule === null) {
                              event.preventDefault();
                              setRuleOrderBeforeLift(rules);
                              setLiftedRule(index);
                              setRuleAnnouncement(t("ruleLifted", { number: index + 1 }));
                            } else if (
                              liftedRule !== null &&
                              [" ", "Escape", "ArrowUp", "ArrowDown"].includes(event.key)
                            ) {
                              event.preventDefault();
                              if (event.key === "Escape") {
                                setRules(ruleOrderBeforeLift);
                                setLiftedRule(null);
                                setRuleAnnouncement(t("ruleMoveCancelled"));
                              } else if (event.key === " ") {
                                setLiftedRule(null);
                                setRuleAnnouncement(t("ruleDropped", { number: index + 1 }));
                              } else {
                                const next = index + (event.key === "ArrowUp" ? -1 : 1);
                                if (next >= 0 && next < rules.length) {
                                  moveRule(index, next);
                                  setLiftedRule(next);
                                  setRuleAnnouncement(t("ruleMoved", { number: next + 1 }));
                                }
                              }
                            }
                          }}
                          t={t}
                        />
                      ))}
                      <Text role="status" aria-live="polite" size="xs" tone="muted">
                        {ruleAnnouncement}
                      </Text>
                    </Stack>
                  )}

                  <Stack gap="2" className="rounded-xl bg-muted p-3.5">
                    <Label htmlFor="collection-default">{t("variableDefaultLabel")}</Label>
                    <Text size="xs" tone="muted">
                      {t("variableDefaultDescription")}
                    </Text>
                    <Select
                      value={defaultPageId}
                      onValueChange={setDefaultPageId}
                      disabled={selectedPageIds.length === 0}
                    >
                      <SelectTrigger id="collection-default">
                        <SelectValue placeholder={t("variableDefaultPlaceholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {selectedPageIds.map((pid) => {
                          const page = pages.find((p) => p.id === pid);
                          return (
                            <SelectItem key={pid} value={pid}>
                              {page?.name || pid}
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>
                  </Stack>

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddRule}
                    disabled={selectedPageIds.length === 0}
                    className="mt-2"
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    {t("variableAddRule")}
                  </Button>
                  {onTestAtTime && (
                    <Button
                      type="button"
                      variant="ghost"
                      className="self-start"
                      onClick={onTestAtTime}
                      disabled={dirty}
                    >
                      <Clock aria-hidden="true" />
                      {t("testAtTime")}
                    </Button>
                  )}

                  <AlertDialog
                    open={pendingSwitchIndex !== null}
                    onOpenChange={(open) => !open && handleCancelDiscardSwitch()}
                  >
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>{t("variableDiscardTitle")}</AlertDialogTitle>
                        <AlertDialogDescription>{t("variableDiscardDescription")}</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel onClick={handleCancelDiscardSwitch}>{tc("cancel")}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmDiscardSwitch}>
                          {t("variableDiscardConfirm")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                  {hasUnsavedRule && (
                    <Text role="status" size="sm" tone="muted">
                      {t("variableSaveOrCancelRule")}
                    </Text>
                  )}
                </Stack>

                <Stack gap="2">
                  <Label htmlFor="collection-poll">{t("variablePollLabel")}</Label>
                  <Text size="xs" tone="muted">
                    {t("variablePollDescription")}
                  </Text>
                  <Select value={String(pollSeconds)} onValueChange={(v) => setPollSeconds(Number(v))}>
                    <SelectTrigger id="collection-poll">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {POLL_PRESETS.map((p) => (
                        <SelectItem key={p.value} value={String(p.value)}>
                          {t(p.labelKey)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Stack>
              </Stack>
            )}
            {selectionMode === "variable" && (
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button type="button" variant="ghost">
                    {t("pagesInCollection")}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  {" "}
                  {/* Selected Pages (reorderable) */}
                  <Stack gap="2">
                    <Label>{t("pagesInCollection")}</Label>
                    <Text size="xs" tone="muted">
                      {/* The hint follows the pointer, like the rows (DD-W27): touch copy for a
              finger at any width, the keyboard copy for a mouse or trackpad. */}
                      {t("variableMembershipHint")}
                    </Text>

                    {selectedPageIds.length === 0 ? (
                      <Text tone="muted" className="border border-dashed rounded-lg p-4 text-center">
                        {t("noPagesAdded")}
                      </Text>
                    ) : (
                      <CollectionPageList
                        pageIds={selectedPageIds}
                        pages={pages}
                        mode={selectionMode}
                        onMove={handleMovePage}
                        onRemove={handleRemovePage}
                      />
                    )}

                    {availablePages.length > 0 && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button type="button" variant="outline" className="self-start">
                            <Plus aria-hidden="true" />
                            {t("addPageAction")}
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {availablePages.map((page) => (
                            <DropdownMenuItem key={page.id} onClick={() => handleAddPage(page.id)}>
                              {page.name}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </Stack>
                </CollapsibleContent>
              </Collapsible>
            )}
          </Stack>
        </Card>
      </Box>
    </Box>
  );
}
