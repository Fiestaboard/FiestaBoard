import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  PageSection,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useBeforeUnload, useBlocker } from "react-router";
import { toast } from "sonner";

import { CollectionForm } from "@/components/collection-form";
import { CollectionPreview } from "@/components/collection-preview";
import { CollectionShowNow } from "@/components/collection-show-now";
import { queryKeys, useCollections, usePages } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import type { Collection, CollectionCreate, CollectionUpdate } from "@/lib/api";
import { api } from "@/lib/api";

export function CollectionEditor({ collectionId }: { collectionId?: string }) {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const { push } = useViewTransition();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useCollections();
  const { data: pagesData, isLoading: pagesLoading, isError: pagesError } = usePages();
  const loadedCollection = data?.collections.find((item) => item.id === collectionId);
  // A background query refresh must not replace the original generation
  // while the form still contains the draft initialized from that generation.
  const [original, setOriginal] = useState<{ id?: string; value?: Collection }>({ id: collectionId });
  if (original.id !== collectionId || (loadedCollection && !original.value)) {
    setOriginal({ id: collectionId, value: loadedCollection });
  }
  const collection = original.id === collectionId ? (original.value ?? loadedCollection) : loadedCollection;
  const expectedRevision = collection?.edit_protocol === "collection-revision-v1" ? collection.revision : undefined;
  const dirty = useRef(false);
  const leavingAfterSave = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [showNowOpen, setShowNowOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testInput, setTestInput] = useState("");
  const [testAt, setTestAt] = useState<string | undefined>();
  const sameSavedGeneration = JSON.stringify(collection) === JSON.stringify(loadedCollection);
  const evaluation = useQuery({
    queryKey: ["collectionEvaluation", collectionId, loadedCollection?.revision, loadedCollection?.updated_at, testAt],
    queryFn: () => api.evaluateCollection(collectionId!, testAt),
    enabled: !!collectionId && !!collection,
    retry: false,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const onDirtyChange = useCallback((value: boolean) => {
    dirty.current = value;
  }, []);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      currentLocation.pathname !== nextLocation.pathname && dirty.current && !leavingAfterSave.current,
  );
  useBeforeUnload(
    useCallback((event) => {
      if (dirty.current && !leavingAfterSave.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    }, []),
  );
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.collections });
    void queryClient.invalidateQueries({ queryKey: queryKeys.activePage() });
  };
  const save = useMutation({
    mutationFn: (value: CollectionCreate | CollectionUpdate) =>
      collectionId
        ? api.updateCollection(collectionId, {
            ...value,
            ...(expectedRevision && { expected_revision: expectedRevision }),
          })
        : api.createCollection(value as CollectionCreate),
    onSuccess: () => {
      leavingAfterSave.current = true;
      refresh();
      toast.success(t(collectionId ? "toastUpdated" : "toastCreated"));
      push("/collections");
    },
    onError: (cause: Error) => {
      setError(cause.message || t(collectionId ? "toastUpdateFailed" : "toastCreateFailed"));
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      expectedRevision ? api.deleteCollection(collectionId!, expectedRevision) : api.deleteCollection(collectionId!),
    onSuccess: () => {
      leavingAfterSave.current = true;
      refresh();
      toast.success(t("toastDeleted"));
      push("/collections");
    },
    onError: (cause: Error) => {
      setError(cause.message || t("toastDeleteFailed"));
      setDeleteOpen(false);
    },
  });
  return (
    <PageSection>
      {isLoading || pagesLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : isError || pagesError || (collectionId && !collection) ? (
        <Stack gap="3">
          <Text role="alert">{t(isError || pagesError ? "loadFailed" : "notFound")}</Text>
          <Button variant="outline" onClick={() => push("/collections")}>
            {t("backToCollections")}
          </Button>
        </Stack>
      ) : (
        <Stack gap="4" className="w-full min-w-0">
          {error && (
            <Text
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-destructive"
            >
              {error}
            </Text>
          )}
          <CollectionForm
            key={collectionId ?? "new"}
            collection={collection}
            pages={pagesData?.pages ?? []}
            onDirtyChange={onDirtyChange}
            onShowNow={collection ? () => setShowNowOpen(true) : undefined}
            onTestAtTime={collection ? () => setTestOpen(true) : undefined}
            ruleResults={sameSavedGeneration && !evaluation.isError ? (evaluation.data?.rules ?? undefined) : undefined}
            preview={
              collection
                ? (dirty) => (
                    <CollectionPreview
                      evaluation={evaluation.data}
                      pages={pagesData?.pages ?? []}
                      mode={collection.selection_mode}
                      dirty={dirty}
                      loading={evaluation.isLoading}
                      failed={evaluation.isError || !sameSavedGeneration}
                    />
                  )
                : undefined
            }
            onSubmit={async (value) => {
              setError(null);
              await save.mutateAsync(value);
            }}
            onCancel={() => push("/collections")}
            onDelete={
              collection
                ? () => {
                    setError(null);
                    setDeleteOpen(true);
                  }
                : undefined
            }
          />
        </Stack>
      )}
      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("testAtTime")}</DialogTitle>
            <DialogDescription>{t("testSavedDescription")}</DialogDescription>
          </DialogHeader>
          <Label htmlFor="collection-test-at">{t("testAtTime")}</Label>
          <Input
            id="collection-test-at"
            type="datetime-local"
            value={testInput}
            onChange={(event) => setTestInput(event.target.value)}
          />
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setTestAt(undefined);
                setTestOpen(false);
              }}
            >
              {tc("cancel")}
            </Button>
            <Button
              disabled={!testInput || !Number.isFinite(new Date(testInput).getTime())}
              onClick={() => {
                setTestAt(new Date(testInput).toISOString());
                setTestOpen(false);
              }}
            >
              {tc("preview")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {showNowOpen && collection && <CollectionShowNow collection={collection} onClose={() => setShowNowOpen(false)} />}
      <AlertDialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (!remove.isPending) setDeleteOpen(open);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteCollection")}</AlertDialogTitle>
            <AlertDialogDescription>{t("deleteConfirmation")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>{tc("cancel")}</AlertDialogCancel>
            <Button variant="destructive" loading={remove.isPending} onClick={() => remove.mutate()}>
              {tc("delete")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("discardChangesTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("discardChangesDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepEditing")}</AlertDialogCancel>
            <Button
              onClick={() => {
                if (blocker.state === "blocked") blocker.proceed();
              }}
            >
              {t("discardAndLeave")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageSection>
  );
}
