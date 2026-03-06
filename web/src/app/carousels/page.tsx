"use client";

import { useState, useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, GalleryHorizontalEnd, Trash2, GripVertical, Clock, FileText, Loader2, Pencil } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Carousel, CarouselCreate, CarouselUpdate, Page } from "@/lib/api";
import { queryKeys } from "@/hooks/use-board";

const INTERVAL_PRESETS = [
  { label: "5 seconds", value: 5 },
  { label: "10 seconds", value: 10 },
  { label: "15 seconds", value: 15 },
  { label: "30 seconds", value: 30 },
  { label: "1 minute", value: 60 },
  { label: "2 minutes", value: 120 },
  { label: "5 minutes", value: 300 },
  { label: "10 minutes", value: 600 },
  { label: "15 minutes", value: 900 },
  { label: "30 minutes", value: 1800 },
];

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

interface CarouselFormProps {
  carousel?: Carousel;
  pages: Page[];
  onSubmit: (data: CarouselCreate | CarouselUpdate) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
}

function CarouselForm({ carousel, pages, onSubmit, onCancel, onDelete }: CarouselFormProps) {
  const isEdit = Boolean(carousel);
  const [name, setName] = useState(carousel?.name || "");
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>(carousel?.page_ids || []);
  const [intervalSeconds, setIntervalSeconds] = useState(carousel?.interval_seconds || 30);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const availablePages = useMemo(
    () => pages.filter((p) => !selectedPageIds.includes(p.id)),
    [pages, selectedPageIds]
  );

  const handleAddPage = useCallback(
    (pageId: string) => {
      if (!selectedPageIds.includes(pageId)) {
        setSelectedPageIds((prev) => [...prev, pageId]);
      }
    },
    [selectedPageIds]
  );

  const handleRemovePage = useCallback((index: number) => {
    setSelectedPageIds((prev) => prev.filter((_, i) => i !== index));
  }, []);

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
    [dragIndex]
  );

  const handleDragEnd = useCallback(() => {
    setDragIndex(null);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || selectedPageIds.length === 0) return;
    setIsSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        page_ids: selectedPageIds,
        interval_seconds: intervalSeconds,
      });
    } catch {
      setIsSubmitting(false);
    }
  };

  const canSubmit = name.trim().length > 0 && selectedPageIds.length >= 1;

  return (
    <form onSubmit={handleSubmit} className="space-y-6 mt-4">
      {/* Name */}
      <div className="space-y-2">
        <Label htmlFor="carousel-name">Name</Label>
        <Input
          id="carousel-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My Carousel"
          maxLength={100}
        />
      </div>

      {/* Interval */}
      <div className="space-y-2">
        <Label>Page Duration</Label>
        <p className="text-xs text-muted-foreground">How long each page displays before cycling</p>
        <Select
          value={String(intervalSeconds)}
          onValueChange={(v) => setIntervalSeconds(Number(v))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {INTERVAL_PRESETS.map((p) => (
              <SelectItem key={p.value} value={String(p.value)}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Selected Pages (reorderable) */}
      <div className="space-y-2">
        <Label>Pages in Carousel</Label>
        <p className="text-xs text-muted-foreground">
          Drag to reorder. Pages cycle in this order.
        </p>

        {selectedPageIds.length === 0 ? (
          <div className="border border-dashed rounded-lg p-4 text-center text-sm text-muted-foreground">
            No pages added yet
          </div>
        ) : (
          <div className="space-y-1">
            {selectedPageIds.map((pid, index) => {
              const page = pages.find((p) => p.id === pid);
              return (
                <div
                  key={pid}
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDragEnd={handleDragEnd}
                  className={`flex items-center gap-2 rounded-lg border p-2.5 bg-background cursor-grab active:cursor-grabbing ${
                    dragIndex === index ? "opacity-50" : ""
                  }`}
                >
                  <GripVertical className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <Badge variant="outline" className="text-xs tabular-nums flex-shrink-0">
                    {index + 1}
                  </Badge>
                  <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <span className="text-sm truncate flex-1">
                    {page?.name || pid}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 flex-shrink-0"
                    onClick={() => handleRemovePage(index)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </div>
              );
            })}
          </div>
        )}

        {/* Add page dropdown */}
        {availablePages.length > 0 && (
          <Select onValueChange={handleAddPage} value="">
            <SelectTrigger className="mt-2">
              <SelectValue placeholder="Add a page..." />
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
      </div>

      {/* Actions */}
      <div className="flex justify-between gap-2 pt-2">
        <div>
          {isEdit && onDelete && (
            <Button type="button" variant="destructive" onClick={onDelete} disabled={isSubmitting}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={!canSubmit || isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? "Update" : "Create"} Carousel
          </Button>
        </div>
      </div>
    </form>
  );
}

export default function CarouselsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingCarousel, setEditingCarousel] = useState<Carousel | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data: carouselsData, isLoading: isLoadingCarousels } = useQuery({
    queryKey: queryKeys.carousels,
    queryFn: api.getCarousels,
  });

  const { data: pagesData } = useQuery({
    queryKey: queryKeys.pages,
    queryFn: api.getPages,
  });

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.carousels });
    queryClient.invalidateQueries({ queryKey: queryKeys.activePage });
  }, [queryClient]);

  const createMutation = useMutation({
    mutationFn: (data: CarouselCreate) => api.createCarousel(data),
    onSuccess: () => {
      invalidateAll();
      toast.success("Carousel created");
      setShowForm(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to create carousel");
      throw err;
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: CarouselUpdate }) =>
      api.updateCarousel(id, data),
    onSuccess: () => {
      invalidateAll();
      toast.success("Carousel updated");
      setShowForm(false);
      setEditingCarousel(null);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to update carousel");
      throw err;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteCarousel(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("Carousel deleted");
      setDeleteId(null);
    },
    onError: () => toast.error("Failed to delete carousel"),
  });

  const handleSubmit = async (data: CarouselCreate | CarouselUpdate) => {
    if (editingCarousel) {
      await updateMutation.mutateAsync({ id: editingCarousel.id, data });
    } else {
      await createMutation.mutateAsync(data as CarouselCreate);
    }
  };

  const handleEdit = useCallback((carousel: Carousel) => {
    setEditingCarousel(carousel);
    setShowForm(true);
  }, []);

  const handleCloseForm = () => {
    setShowForm(false);
    setEditingCarousel(null);
  };

  const carousels = carouselsData?.carousels || [];
  const pages = pagesData?.pages || [];

  const getPageName = (pageId: string) =>
    pages.find((p) => p.id === pageId)?.name || pageId.slice(0, 8);

  if (isLoadingCarousels) {
    return (
      <div className="min-h-screen bg-background overflow-x-hidden">
        <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
          <Skeleton className="h-10 w-48 mb-4" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        {/* Header */}
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <GalleryHorizontalEnd className="h-7 w-7 text-brand-emphasis" />
                Carousels
              </h1>
              <p className="page-description">
                Create collections of pages that cycle automatically
              </p>
            </div>
            <Button
              variant="brand"
              size="sm"
              onClick={() => {
                setEditingCarousel(null);
                setShowForm(true);
              }}
              className="btn-lift"
            >
              <Plus className="h-4 w-4 mr-1" />
              New Carousel
            </Button>
          </div>
        </div>

        {/* Carousels list */}
        {carousels.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <GalleryHorizontalEnd className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground mb-2">No carousels yet</p>
              <p className="text-sm text-muted-foreground mb-4">
                Carousels automatically cycle through a collection of pages.
              </p>
              <Button
                variant="brand"
                onClick={() => {
                  setEditingCarousel(null);
                  setShowForm(true);
                }}
                className="btn-lift"
              >
                <Plus className="h-4 w-4 mr-1" />
                Create Your First Carousel
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {carousels.map((carousel, idx) => (
              <Card
                key={carousel.id}
                className="animate-card-fade-in card-interactive"
                style={{ animationDelay: `${idx * 50}ms` }}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <GalleryHorizontalEnd className="h-5 w-5 text-primary flex-shrink-0" />
                      <div className="min-w-0">
                        <CardTitle className="text-base truncate">{carousel.name}</CardTitle>
                        <CardDescription className="text-xs">
                          {carousel.page_ids.length} page{carousel.page_ids.length !== 1 ? "s" : ""}{" "}
                          &middot; {formatInterval(carousel.interval_seconds)} per page
                        </CardDescription>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="flex-shrink-0"
                      onClick={() => handleEdit(carousel)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-wrap gap-1.5">
                    {carousel.page_ids.map((pid, i) => (
                      <Badge key={pid} variant="secondary" className="text-xs">
                        <span className="text-muted-foreground mr-1">{i + 1}.</span>
                        {getPageName(pid)}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Form Sheet */}
        <Sheet open={showForm} onOpenChange={(open) => { if (!open) handleCloseForm(); }}>
          <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
            <SheetHeader>
              <SheetTitle>
                {editingCarousel ? "Edit" : "New"} Carousel
              </SheetTitle>
              <SheetDescription>
                {editingCarousel
                  ? "Update carousel settings and page order"
                  : "Create a collection of pages that cycle automatically"}
              </SheetDescription>
            </SheetHeader>
            <CarouselForm
              carousel={editingCarousel || undefined}
              pages={pages}
              onSubmit={handleSubmit}
              onCancel={handleCloseForm}
              onDelete={
                editingCarousel
                  ? () => {
                      const id = editingCarousel.id;
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
              <AlertDialogTitle>Delete Carousel</AlertDialogTitle>
              <AlertDialogDescription>
                Are you sure? This cannot be undone. If this carousel is currently active, the
                display will stop cycling.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => deleteId && deleteMutation.mutate(deleteId)}>
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
