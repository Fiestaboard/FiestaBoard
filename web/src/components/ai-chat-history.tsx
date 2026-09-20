"use client";

import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Button,
  EmptyState,
  Flex,
  Input,
  Label,
  ScrollArea,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Download, History, Pencil, Play, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { ReadOnlyTranscript } from "@/components/ai-chat-transcript";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type ConversationSummary } from "@/lib/api";
import { formatRelativeTime } from "@/lib/relative-time";
import { settleSavedTranscript } from "@/lib/use-ai-chat";

// The History view of the FiestaBot drawer (#2022): the list of saved
// conversations, and one conversation opened read-only with a Continue
// button that makes it the live chat again. Both read the store the hook
// autosaves into; the list is a TanStack query so a delete, rename or
// clear invalidates it and the rows follow.

export const CONVERSATIONS_QUERY_KEY = ["ai-conversations"] as const;

/** How long the search box waits after the last keystroke before asking. */
const SEARCH_DEBOUNCE_MS = 250;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function AiHistoryList({
  onOpen,
  onDeleted,
  onCleared,
}: {
  onOpen: (id: string) => void;
  /** A conversation was deleted (the panel drops it if it is the live one). */
  onDeleted?: (id: string) => void;
  /** Every conversation was deleted. */
  onCleared?: () => void;
}) {
  const t = useTranslations("aiChatPanel");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);

  // The list follows the search box a beat behind it, and keeps the last
  // rows on screen while the next answer is on its way, so typing never
  // blanks the list.
  const trimmed = useDebounced(query.trim(), SEARCH_DEBOUNCE_MS);
  const list = useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, trimmed],
    queryFn: () => api.listConversations(trimmed || undefined),
    placeholderData: keepPreviousData,
  });
  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY }),
    [queryClient],
  );

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: (_result, id) => {
      toast.success(t("history.deleted"));
      onDeleted?.(id);
      void invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.renameConversation(id, title),
    onSuccess: () => {
      setRenamingId(null);
      void invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });
  const clear = useMutation({
    mutationFn: () => api.clearConversations(),
    onSuccess: () => {
      setConfirmClear(false);
      toast.success(t("history.cleared"));
      onCleared?.();
      void invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const rows = list.data?.conversations ?? [];
  const nothingSaved = list.isSuccess && rows.length === 0 && !trimmed;

  return (
    <Flex direction="col" className="min-h-0 flex-1">
      <Box className="flex-shrink-0 border-b px-3 py-2">
        <Label htmlFor="ai-history-search" className="sr-only">
          {t("history.searchAriaLabel")}
        </Label>
        <Input
          id="ai-history-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("history.searchPlaceholder")}
          className="h-8 text-sm"
        />
      </Box>

      <ScrollArea className="min-h-0 flex-1">
        <Box className="px-2 py-2">
          {list.isPending ? (
            <Flex justify="center" className="py-6">
              <Spinner size="sm" label={null} />
            </Flex>
          ) : list.isError ? (
            <Alert variant="destructive" className="text-xs">
              <AlertCircle className="h-3.5 w-3.5" />
              <AlertDescription>{list.error.message}</AlertDescription>
            </Alert>
          ) : nothingSaved ? (
            <EmptyState icon={History} title={t("history.empty")} description={t("history.emptyDescription")} />
          ) : rows.length === 0 ? (
            <Text size="sm" tone="muted" className="px-2 py-6 text-center">
              {t("history.noMatches")}
            </Text>
          ) : (
            <Stack gap="1">
              {rows.map((row) => (
                <HistoryRow
                  key={row.id}
                  row={row}
                  locale={locale}
                  renaming={renamingId === row.id}
                  onOpen={() => onOpen(row.id)}
                  onStartRename={() => setRenamingId(row.id)}
                  onCancelRename={() => setRenamingId(null)}
                  onRename={(title) => rename.mutate({ id: row.id, title })}
                  onDelete={() => remove.mutate(row.id)}
                  busy={remove.isPending || rename.isPending}
                />
              ))}
            </Stack>
          )}
        </Box>
      </ScrollArea>

      {rows.length > 0 || trimmed ? (
        <Box className="flex-shrink-0 border-t px-3 py-2">
          <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-destructive hover:text-destructive"
              onClick={() => setConfirmClear(true)}
              disabled={clear.isPending}
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              {t("history.clearAll")}
            </Button>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t("history.clearAllTitle")}</AlertDialogTitle>
                <AlertDialogDescription>{t("history.clearAllDescription")}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t("history.cancel")}</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={() => clear.mutate()}
                  disabled={clear.isPending}
                >
                  {t("history.clearAllConfirm")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </Box>
      ) : null}
    </Flex>
  );
}

function HistoryRow({
  row,
  locale,
  renaming,
  busy,
  onOpen,
  onStartRename,
  onCancelRename,
  onRename,
  onDelete,
}: {
  row: ConversationSummary;
  locale: string;
  renaming: boolean;
  busy: boolean;
  onOpen: () => void;
  onStartRename: () => void;
  onCancelRename: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  const t = useTranslations("aiChatPanel");

  if (renaming) {
    return <RenameEditor row={row} busy={busy} onRename={onRename} onCancel={onCancelRename} />;
  }

  const meta = `${formatRelativeTime(row.updated_at, locale)} · ${t("history.messageCount", { count: row.message_count })}`;
  return (
    <Flex align="center" gap="1" className="group rounded-md hover:bg-accent/60">
      <Button
        type="button"
        variant="ghost"
        className="h-auto min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left hover:bg-transparent"
        onClick={onOpen}
        aria-label={t("history.open", { title: row.title })}
      >
        <Text as="span" size="sm" weight="medium" className="w-full truncate">
          {row.title}
        </Text>
        <Text as="span" size="xs" tone="muted" className="w-full truncate font-normal">
          {meta}
        </Text>
      </Button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-7 w-7 shrink-0 opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
        onClick={onStartRename}
        disabled={busy}
        aria-label={t("history.renameAriaLabel", { title: row.title })}
        title={t("history.rename")}
      >
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-7 w-7 shrink-0 opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
        onClick={onDelete}
        disabled={busy}
        aria-label={t("history.deleteAriaLabel", { title: row.title })}
        title={t("history.delete")}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </Flex>
  );
}

/**
 * The inline title editor. Its own component so the draft is seeded from
 * the row's title every time editing starts — a cancelled or failed rename
 * leaves nothing behind for the next one.
 */
function RenameEditor({
  row,
  busy,
  onRename,
  onCancel,
}: {
  row: ConversationSummary;
  busy: boolean;
  onRename: (title: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("aiChatPanel");
  const [draft, setDraft] = useState(row.title);
  const submit = () => {
    const next = draft.trim();
    if (!next || next === row.title) {
      onCancel();
      return;
    }
    onRename(next);
  };
  return (
    <Flex align="center" gap="1" className="rounded-md border px-2 py-1.5">
      <Label htmlFor={`ai-history-rename-${row.id}`} className="sr-only">
        {t("history.renameLabel")}
      </Label>
      <Input
        id={`ai-history-rename-${row.id}`}
        value={draft}
        maxLength={80}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          } else if (e.key === "Escape") {
            // Escape cancels the rename and goes no further: the drawer
            // closes on Escape too, and the user meant the field.
            e.preventDefault();
            e.stopPropagation();
            onCancel();
          }
        }}
        className="h-7 min-w-0 flex-1 text-sm"
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-7 w-7"
        onClick={submit}
        disabled={busy}
        aria-label={t("history.saveTitle")}
        title={t("history.saveTitle")}
      >
        <Check className="h-3.5 w-3.5" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-7 w-7"
        onClick={onCancel}
        aria-label={t("history.cancel")}
        title={t("history.cancel")}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </Flex>
  );
}

/**
 * One saved conversation, read-only. `onContinue` is the hook's
 * `loadConversation`; the panel switches back to the live chat when it
 * resolves with the conversation.
 */
export function AiConversationReview({
  id,
  onContinue,
  onTitle,
}: {
  id: string;
  onContinue: (id: string) => void;
  /** The conversation's title once loaded, for the panel header. */
  onTitle?: (title: string) => void;
}) {
  const t = useTranslations("aiChatPanel");
  const conversation = useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, "one", id],
    queryFn: async () => {
      const loaded = await api.getConversation(id);
      onTitle?.(loaded.title);
      return loaded;
    },
  });

  if (conversation.isPending) {
    return (
      <Flex justify="center" className="py-6">
        <Spinner size="sm" label={null} />
      </Flex>
    );
  }
  if (conversation.isError) {
    return (
      <Box className="px-4 py-4">
        <Alert variant="destructive" className="text-xs">
          <AlertCircle className="h-3.5 w-3.5" />
          <AlertDescription>{t("history.loadFailed")}</AlertDescription>
        </Alert>
      </Box>
    );
  }

  return (
    <Flex direction="col" className="min-h-0 flex-1">
      <ScrollArea className="min-h-0 flex-1">
        <Stack gap="2" className="px-4 py-4">
          <ReadOnlyTranscript messages={settleSavedTranscript(conversation.data.messages)} />
        </Stack>
      </ScrollArea>
      <Box className="flex-shrink-0 border-t bg-card px-3 py-3">
        <Text size="xs" tone="muted" className="mb-2">
          {t("history.readOnly")}
        </Text>
        <Flex align="center" justify="between" gap="2">
          <TextLink
            href={api.exportConversationUrl(id)}
            download={`fiestabot-conversation-${id}.json`}
            className="inline-flex items-center gap-1 text-xs"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            {t("history.export")}
          </TextLink>
          <Button type="button" size="sm" className="h-8" onClick={() => onContinue(id)}>
            <Play className="mr-1 h-3.5 w-3.5" />
            {t("history.continue")}
          </Button>
        </Flex>
      </Box>
    </Flex>
  );
}
