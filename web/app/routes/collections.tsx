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
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Input,
  Label,
  PageHeader,
  PageLayout,
  PageToolbar,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  FileText,
  GalleryHorizontalEnd,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  Shuffle,
  Sigma,
  Trash2,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { VariableRuleRow } from "@/components/variable-rule-row";
import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type {
  Collection,
  CollectionCreate,
  CollectionSelectionMode,
  CollectionUpdate,
  Page,
  VariableRule,
} from "@/lib/api";
import { api } from "@/lib/api";

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
];

const POLL_PRESETS = [
  { labelKey: "interval5s", value: 5 },
  { labelKey: "interval10s", value: 10 },
  { labelKey: "interval15s", value: 15 },
  { labelKey: "interval30s", value: 30 },
  { labelKey: "interval1m", value: 60 },
];

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

interface CollectionFormProps {
  collection?: Collection;
  pages: Page[];
  onSubmit: (data: CollectionCreate | CollectionUpdate) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
}

function CollectionForm({ collection, pages, onSubmit, onCancel, onDelete }: CollectionFormProps) {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const isEdit = Boolean(collection);

  const [name, setName] = useState(collection?.name || "");
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>(collection?.page_ids || []);
  const [selectionMode, setSelectionMode] = useState<CollectionSelectionMode>(collection?.selection_mode || "time");
  const [intervalSeconds, setIntervalSeconds] = useState(
    collection?.selection_mode === "random"
      ? collection?.random?.interval_seconds || 30
      : collection?.time?.interval_seconds || 30,
  );
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

  const handleRuleDragOver = useCallback(
    (e: React.DragEvent, targetIndex: number) => {
      e.preventDefault();
      if (ruleDragIndex === null || ruleDragIndex === targetIndex) return;
      setRules((prev) => {
        const next = [...prev];
        const [moved] = next.splice(ruleDragIndex, 1);
        next.splice(targetIndex, 0, moved);
        return next;
      });
      setRuleDragIndex(targetIndex);
    },
    [ruleDragIndex],
  );

  const handleRuleDragEnd = useCallback(() => setRuleDragIndex(null), []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || selectedPageIds.length === 0) return;
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
        time: { interval_seconds: intervalSeconds },
        variable:
          selectionMode === "variable"
            ? {
                rules,
                default_page_id: defaultPageId,
                poll_seconds: pollSeconds,
              }
            : null,
        random: selectionMode === "random" ? { interval_seconds: intervalSeconds } : null,
      });
    } catch {
      setIsSubmitting(false);
    }
  };

  const canSubmit =
    name.trim().length > 0 &&
    selectedPageIds.length >= 1 &&
    (selectionMode !== "variable" ||
      (defaultPageId.length > 0 && rules.every((r) => r.expression.trim().length > 0 && r.page_id.length > 0)));

  return (
    <Box as="form" onSubmit={handleSubmit} className="space-y-6 mt-4">
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
          <Select value={String(intervalSeconds)} onValueChange={(v) => setIntervalSeconds(Number(v))}>
            <SelectTrigger id="collection-interval">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVAL_PRESETS.map((p) => (
                <SelectItem key={p.value} value={String(p.value)}>
                  {t(p.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 flex-shrink-0"
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
            <SelectTrigger className="mt-2">
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
                  <VariableRuleRow
                    key={index}
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
      <Flex justify="between" gap="2" className="pt-2">
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
          <Button type="submit" disabled={!canSubmit || isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? t("updateCollection") : t("createCollection")}
          </Button>
        </Flex>
      </Flex>
    </Box>
  );
}

export default function CollectionsPage() {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingCollection, setEditingCollection] = useState<Collection | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data: collectionsData, isLoading: isLoadingCollections } = useQuery({
    queryKey: queryKeys.collections,
    queryFn: api.getCollections,
  });

  const { data: pagesData } = useQuery({
    queryKey: queryKeys.pages,
    queryFn: api.getPages,
  });

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.collections });
    queryClient.invalidateQueries({ queryKey: queryKeys.activePage() });
  }, [queryClient]);

  const createMutation = useMutation({
    mutationFn: (data: CollectionCreate) => api.createCollection(data),
    onSuccess: () => {
      invalidateAll();
      toast.success(t("toastCreated"));
      setShowForm(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || t("toastCreateFailed"));
      throw err;
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: CollectionUpdate }) => api.updateCollection(id, data),
    onSuccess: () => {
      invalidateAll();
      toast.success(t("toastUpdated"));
      setShowForm(false);
      setEditingCollection(null);
    },
    onError: (err: Error) => {
      toast.error(err.message || t("toastUpdateFailed"));
      throw err;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      invalidateAll();
      toast.success(t("toastDeleted"));
      setDeleteId(null);
    },
    onError: () => toast.error(t("toastDeleteFailed")),
  });

  const handleSubmit = async (data: CollectionCreate | CollectionUpdate) => {
    if (editingCollection) {
      await updateMutation.mutateAsync({ id: editingCollection.id, data });
    } else {
      await createMutation.mutateAsync(data as CollectionCreate);
    }
  };

  const handleEdit = useCallback((collection: Collection) => {
    setEditingCollection(collection);
    setShowForm(true);
  }, []);

  const handleCloseForm = () => {
    setShowForm(false);
    setEditingCollection(null);
  };

  const collections = collectionsData?.collections || [];
  const pages = pagesData?.pages || [];

  const getPageName = (pageId: string) => pages.find((p) => p.id === pageId)?.name || pageId.slice(0, 8);

  const describeMode = (c: Collection): string => {
    if (c.selection_mode === "time") {
      return `${formatInterval(c.time.interval_seconds)} ${t("perPageShort")}`;
    }
    if (c.selection_mode === "random") {
      return `${formatInterval(c.random?.interval_seconds ?? 30)} ${t("perPageShort")}`;
    }
    const n = c.variable?.rules.length ?? 0;
    return t("variableModeBadge", { count: n });
  };

  if (isLoadingCollections) {
    return (
      <PageLayout>
        <Skeleton className="h-10 w-48 mb-4" />
        <Skeleton className="h-64 w-full" />
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <PageHeader icon={GalleryHorizontalEnd} title={t("title")} description={t("description")} />
      <PageToolbar
        right={
          <Button
            variant="brand"
            size="sm"
            onClick={() => {
              setEditingCollection(null);
              setShowForm(true);
            }}
            className="btn-lift"
          >
            <Plus className="h-4 w-4 mr-1" />
            {t("newCollection")}
          </Button>
        }
      />

      {/* Collections list */}
      {collections.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <GalleryHorizontalEnd className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <Text tone="muted" size="base" className="mb-2">
              {t("noCollectionsTitle")}
            </Text>
            <Text tone="muted" className="mb-4">
              {t("noCollectionsDescription")}
            </Text>
            <Button
              variant="brand"
              onClick={() => {
                setEditingCollection(null);
                setShowForm(true);
              }}
              className="btn-lift"
            >
              <Plus className="h-4 w-4 mr-1" />
              {t("createFirstCollection")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Stack gap="4">
          {collections.map((collection, idx) => (
            <Card
              key={collection.id}
              className="animate-card-fade-in card-interactive"
              style={{ animationDelay: `${idx * 50}ms` }}
            >
              <CardHeader className="pb-3">
                {/* min-w-0: CardHeader is a grid; without it this grid item
                    sizes to min-content and long names inflate the row. */}
                <Flex align="start" justify="between" gap="2" className="min-w-0">
                  <Flex align="center" gap="2" className="min-w-0">
                    <GalleryHorizontalEnd className="h-5 w-5 text-primary flex-shrink-0" />
                    <Box className="min-w-0">
                      <CardTitle className="text-base flex items-center gap-2 min-w-0">
                        <Text as="span" size="base" weight="semibold" className="truncate">
                          {collection.name}
                        </Text>
                        <Badge variant="outline" className="text-[10px] uppercase tracking-wide flex-shrink-0">
                          {collection.selection_mode === "time" ? (
                            <Clock className="h-3 w-3 mr-1" aria-hidden="true" />
                          ) : collection.selection_mode === "random" ? (
                            <Shuffle className="h-3 w-3 mr-1" aria-hidden="true" />
                          ) : (
                            <Sigma className="h-3 w-3 mr-1" aria-hidden="true" />
                          )}
                          {collection.selection_mode}
                        </Badge>
                        {collection.selection_mode === "variable" && (
                          <Badge variant="outline" className="text-[10px] uppercase tracking-wide flex-shrink-0">
                            {t("betaBadge")}
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="text-xs">
                        {collection.page_ids.length} page
                        {collection.page_ids.length !== 1 ? "s" : ""} &middot; {describeMode(collection)}
                      </CardDescription>
                    </Box>
                  </Flex>
                  <Button variant="ghost" size="sm" className="flex-shrink-0" onClick={() => handleEdit(collection)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                </Flex>
              </CardHeader>
              <CardContent className="pt-0">
                <Flex wrap gap="1.5">
                  {collection.page_ids.map((pid, i) => (
                    <Badge key={pid} variant="secondary" className="text-xs max-w-full">
                      {collection.selection_mode === "time" && (
                        <Text as="span" size="xs" tone="muted" className="mr-1 flex-shrink-0">
                          {i + 1}.
                        </Text>
                      )}
                      <Text as="span" size="xs" className="truncate">
                        {getPageName(pid)}
                      </Text>
                    </Badge>
                  ))}
                </Flex>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {/* Form Sheet */}
      <Sheet
        open={showForm}
        onOpenChange={(open) => {
          if (!open) handleCloseForm();
        }}
      >
        <SheetContent
          className="w-full sm:max-w-xl overflow-y-auto"
          onEscapeKeyDown={(e) => {
            // If the variable-autocomplete popover is open, let it handle Escape
            // and keep the Sheet open.
            if (document.documentElement.getAttribute("data-variable-autocomplete-open") === "1") {
              e.preventDefault();
            }
          }}
        >
          <SheetHeader>
            <SheetTitle>{editingCollection ? t("editCollection") : t("newCollection")}</SheetTitle>
            <SheetDescription>{editingCollection ? t("editDescription") : t("createDescription")}</SheetDescription>
          </SheetHeader>
          <CollectionForm
            collection={editingCollection || undefined}
            pages={pages}
            onSubmit={handleSubmit}
            onCancel={handleCloseForm}
            onDelete={
              editingCollection
                ? () => {
                    const id = editingCollection.id;
                    handleCloseForm();
                    setDeleteId(id);
                  }
                : undefined
            }
          />
        </SheetContent>
      </Sheet>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteCollection")}</AlertDialogTitle>
            <AlertDialogDescription>{t("deleteConfirmation")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tc("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteId && deleteMutation.mutate(deleteId)}>
              {tc("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
