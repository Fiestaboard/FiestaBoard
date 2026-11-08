import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Box,
  Button,
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
} from "@fiestaboard/ui";
import { ArrowDown, ArrowUp, Clock, FileText, GripVertical, Plus, Shuffle, Sigma, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { VariableRuleRow } from "@/components/variable-rule-row";
import { useTranslations } from "@/i18n/translations";
import type {
  Collection,
  CollectionCreate,
  CollectionSelectionMode,
  CollectionUpdate,
  Page,
  VariableRule,
} from "@/lib/api";

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
}

export function CollectionForm({
  collection,
  pages,
  onSubmit,
  onCancel,
  onDelete,
  onDirtyChange,
}: CollectionFormProps) {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
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
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  // Rule-editor state: only one rule is editable at a time.
  const [editingRuleIndex, setEditingRuleIndex] = useState<number | null>(null);
  const [editingRuleDirty, setEditingRuleDirty] = useState(false);
  const [pendingSwitchIndex, setPendingSwitchIndex] = useState<number | null>(null);
  // Track a freshly-added rule so we can drop it from the list if the user cancels
  // without ever saving.
  const [newRuleIndex, setNewRuleIndex] = useState<number | null>(null);
  // Separate drag index for the rules list so it doesn't collide with page dragging.
  const [ruleDragIndex, setRuleDragIndex] = useState<number | null>(null);

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

  const movePage = (index: number, direction: -1 | 1) => {
    setSelectedPageIds((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

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

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDragOver = useCallback(
    (e: React.DragEvent, targetIndex: number) => {
      e.preventDefault();
      if (dragIndex === null || dragIndex === targetIndex) return;
      setSelectedPageIds((prev) => {
        const next = [...prev];
        const [moved] = next.splice(dragIndex, 1);
        next.splice(targetIndex, 0, moved);
        return next;
      });
      setDragIndex(targetIndex);
    },
    [dragIndex],
  );

  const handleDragEnd = useCallback(() => setDragIndex(null), []);

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

  const handleRuleDragStart = useCallback((index: number) => {
    setRuleDragIndex(index);
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

  const handleRuleDragOver = useCallback(
    (e: React.DragEvent, targetIndex: number) => {
      e.preventDefault();
      if (editingRuleDirty || ruleDragIndex === null || ruleDragIndex === targetIndex) return;
      moveRule(ruleDragIndex, targetIndex);
      setRuleDragIndex(targetIndex);
    },
    [ruleDragIndex, editingRuleDirty, moveRule],
  );

  const handleRuleDragEnd = useCallback(() => setRuleDragIndex(null), []);

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

  const hasUnsavedRule = selectionMode === "variable" && (editingRuleDirty || newRuleIndex !== null);

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
    <Box as="form" onSubmit={handleSubmit} className="space-y-6">
      {/* Name */}
      <Stack gap="2">
        <Label htmlFor="collection-name">{t("nameLabel")}</Label>
        <Input
          id="collection-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("namePlaceholder")}
          maxLength={100}
        />
      </Stack>

      {/* Selection mode */}
      <Stack gap="2">
        <Label htmlFor="collection-mode">{t("selectionModeLabel")}</Label>
        <Text size="xs" tone="muted">
          {t("selectionModeDescription")}
        </Text>
        <Select value={selectionMode} onValueChange={(v) => setSelectionMode(v as CollectionSelectionMode)}>
          <SelectTrigger id="collection-mode">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="time">
              <Flex align="center" gap="2">
                <Clock className="h-4 w-4" aria-hidden="true" />
                <Text as="span">{t("modeTimeLabel")}</Text>
              </Flex>
            </SelectItem>
            <SelectItem value="variable">
              <Flex align="center" gap="2">
                <Sigma className="h-4 w-4" aria-hidden="true" />
                <Text as="span">{t("modeVariableLabel")}</Text>
                <Badge variant="outline" className="text-[10px] uppercase tracking-wide ml-1 py-0">
                  {t("betaBadge")}
                </Badge>
              </Flex>
            </SelectItem>
            <SelectItem value="random">
              <Flex align="center" gap="2">
                <Shuffle className="h-4 w-4" aria-hidden="true" />
                <Text as="span">{t("modeRandomLabel")}</Text>
              </Flex>
            </SelectItem>
          </SelectContent>
        </Select>
      </Stack>

      {/* Page-duration controls (time + random modes) */}
      {(selectionMode === "time" || selectionMode === "random") && (
        <Stack gap="2">
          <Label htmlFor="collection-interval">{t("pageDurationLabel")}</Label>
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

      {/* Selected Pages (reorderable) */}
      <Stack gap="2">
        <Label>{t("pagesInCollection")}</Label>
        <Text size="xs" tone="muted">
          {selectionMode === "time"
            ? t("dragToReorder")
            : selectionMode === "random"
              ? t("randomMembershipHint")
              : t("variableMembershipHint")}
        </Text>

        {selectedPageIds.length === 0 ? (
          <Text tone="muted" className="border border-dashed rounded-lg p-4 text-center">
            {t("noPagesAdded")}
          </Text>
        ) : (
          <Stack gap="1">
            {selectedPageIds.map((pid, index) => {
              const page = pages.find((p) => p.id === pid);
              return (
                <Flex
                  key={pid}
                  align="center"
                  gap="2"
                  draggable={selectionMode === "time"}
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDragEnd={handleDragEnd}
                  className={`rounded-lg border p-2.5 bg-background ${
                    selectionMode === "time" ? "cursor-grab active:cursor-grabbing" : ""
                  } ${dragIndex === index ? "opacity-50" : ""}`}
                >
                  {selectionMode === "time" && <GripVertical className="h-4 w-4 text-muted-foreground flex-shrink-0" />}
                  {selectionMode === "time" && (
                    <Badge variant="outline" className="text-xs tabular-nums flex-shrink-0">
                      {index + 1}
                    </Badge>
                  )}
                  <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <Text as="span" className="truncate flex-1">
                    {page?.name || pid}
                  </Text>
                  {selectionMode === "time" && (
                    <Flex gap="1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        disabled={index === 0}
                        aria-label={t("movePageUp", { name: page?.name || pid })}
                        onClick={() => movePage(index, -1)}
                      >
                        <ArrowUp className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        disabled={index === selectedPageIds.length - 1}
                        aria-label={t("movePageDown", { name: page?.name || pid })}
                        onClick={() => movePage(index, 1)}
                      >
                        <ArrowDown className="h-4 w-4" />
                      </Button>
                    </Flex>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 flex-shrink-0"
                    aria-label={t("removePage", { name: page?.name || pid })}
                    onClick={() => handleRemovePage(index)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </Flex>
              );
            })}
          </Stack>
        )}

        {availablePages.length > 0 && (
          <Select onValueChange={handleAddPage} value="">
            <SelectTrigger className="mt-2" aria-label={t("addPagePlaceholder")}>
              <SelectValue placeholder={t("addPagePlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {availablePages.map((page) => (
                <SelectItem key={page.id} value={page.id}>
                  {page.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Stack>

      {/* Variable-mode controls */}
      {selectionMode === "variable" && (
        <Stack gap="4" className="border-t pt-4">
          <Flex
            align="start"
            gap="2"
            className="rounded-md border border-dashed bg-muted/40 p-2.5 text-xs text-muted-foreground"
          >
            <Badge variant="outline" className="text-[10px] uppercase tracking-wide py-0">
              {t("betaBadge")}
            </Badge>
            <Text as="span" size="xs" tone="muted">
              {t("variableModeBetaNote")}
            </Text>
          </Flex>
          <Stack gap="2">
            <Label htmlFor="collection-default">{t("variableDefaultLabel")}</Label>
            <Text size="xs" tone="muted">
              {t("variableDefaultDescription")}
            </Text>
            <Select value={defaultPageId} onValueChange={setDefaultPageId} disabled={selectedPageIds.length === 0}>
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

          <Stack gap="2">
            <Label>{t("variableRulesLabel")}</Label>
            <Text size="xs" tone="muted">
              {t("variableRulesDescription")}
            </Text>

            {rules.length === 0 ? (
              <Text tone="muted" className="border border-dashed rounded-lg p-4 text-center">
                {t("variableNoRules")}
              </Text>
            ) : (
              <Stack gap="2">
                {rules.map((rule, index) => (
                  <Stack key={index} gap="1">
                    <VariableRuleRow
                      rule={rule}
                      index={index}
                      pages={pages}
                      selectablePageIds={selectedPageIds}
                      isEditing={editingRuleIndex === index}
                      isDragging={ruleDragIndex === index}
                      onRequestEdit={() => handleRequestEditRule(index)}
                      onSave={(next) => handleSaveRule(index, next)}
                      onCancelEdit={handleCancelEditRule}
                      onRemove={() => handleRemoveRule(index)}
                      onDirtyChange={(dirty) => {
                        if (editingRuleIndex === index) setEditingRuleDirty(dirty);
                      }}
                      onDragStart={() => handleRuleDragStart(index)}
                      onDragOver={(e) => handleRuleDragOver(e, index)}
                      onDragEnd={handleRuleDragEnd}
                      t={t}
                    />
                    <Flex gap="1" justify="end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        disabled={editingRuleDirty || index === 0}
                        aria-label={t("moveRuleUp", { number: index + 1 })}
                        onClick={() => moveRule(index, index - 1)}
                      >
                        <ArrowUp className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        disabled={editingRuleDirty || index === rules.length - 1}
                        aria-label={t("moveRuleDown", { number: index + 1 })}
                        onClick={() => moveRule(index, index + 1)}
                      >
                        <ArrowDown className="h-4 w-4" />
                      </Button>
                    </Flex>
                  </Stack>
                ))}
              </Stack>
            )}

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

      {/* Actions */}
      <Flex justify="between" gap="2" wrap className="pt-2">
        <Box>
          {isEdit && onDelete && (
            <Button type="button" variant="destructive" onClick={onDelete} disabled={isSubmitting}>
              <Trash2 className="mr-2 h-4 w-4" />
              {tc("delete")}
            </Button>
          )}
        </Box>
        <Flex gap="2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {tc("cancel")}
          </Button>
          <Button type="submit" loading={isSubmitting} disabled={!canSubmit || isSubmitting}>
            {isEdit ? t("updateCollection") : t("createCollection")}
          </Button>
        </Flex>
      </Flex>
    </Box>
  );
}
