"use client";

import { useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BoardDisplay } from "@/components/board-display";
import { PlainTextEditor } from "@/components/plain-text-editor";

// Lazy load TipTapTemplateEditor to reduce initial bundle size
const TipTapTemplateEditor = dynamic(
  () => import("@/components/tiptap-template-editor/TipTapTemplateEditor").then(mod => ({ default: mod.TipTapTemplateEditor })),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    ),
  }
);
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { queryKeys } from "@/hooks/use-board";
import {
  Wand2,
  X,
  Save,
  Trash2,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { api, PageCreate, PageUpdate, PageType, DeviceType } from "@/lib/api";
import { useBoardSettings } from "@/hooks/use-board";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";
import { DEVICE_DIMENSIONS } from "@/components/tiptap-template-editor/utils/constants";

// Alignment type for template lines
type LineAlignment = "left" | "center" | "right";

// Extract alignment prefix from a template line
function extractAlignment(line: string): { alignment: LineAlignment; wrapEnabled: boolean; content: string } {
  let remaining = line;
  let alignment: LineAlignment = "left";
  let wrapEnabled = false;
  
  // Extract wrap prefix
  if (remaining.startsWith("{wrap}")) {
    wrapEnabled = true;
    remaining = remaining.slice(6);
  }
  
  // Extract alignment prefix (can come after wrap)
  if (remaining.startsWith("{center}")) {
    alignment = "center";
    remaining = remaining.slice(8);
  } else if (remaining.startsWith("{right}")) {
    alignment = "right";
    remaining = remaining.slice(7);
  } else if (remaining.startsWith("{left}")) {
    alignment = "left";
    remaining = remaining.slice(6);
  }
  
  return { alignment, wrapEnabled, content: remaining };
}

// Apply alignment and wrap prefixes to content
function applyAlignment(alignment: LineAlignment, wrapEnabled: boolean, content: string): string {
  // Remove any existing prefixes first
  let cleanContent = content;
  if (cleanContent.startsWith("{wrap}")) cleanContent = cleanContent.slice(6);
  if (cleanContent.startsWith("{center}")) cleanContent = cleanContent.slice(8);
  else if (cleanContent.startsWith("{right}")) cleanContent = cleanContent.slice(7);
  else if (cleanContent.startsWith("{left}")) cleanContent = cleanContent.slice(6);
  
  // Don't add prefixes to empty lines - they need to stay empty for wrap to work
  if (cleanContent === "") {
    return "";
  }
  
  const prefixes: string[] = [];
  
  // Add wrap prefix first
  if (wrapEnabled) {
    prefixes.push("{wrap}");
  }
  
  // Add alignment prefix
  switch (alignment) {
    case "center":
      prefixes.push("{center}");
      break;
    case "right":
      prefixes.push("{right}");
      break;
    // left is default, no prefix needed
  }
  
  return prefixes.join("") + cleanContent;
}



interface PageBuilderProps {
  pageId?: string; // If provided, edit existing page
  deviceType?: DeviceType; // Device type for new pages
  onClose: () => void;
  onSave?: () => void;
}

// Draft storage key helper
function getDraftKey(pageId?: string): string {
  return `fiestaboard-page-draft-${pageId || 'new'}`;
}

interface DraftData {
  name: string;
  templateLines: string[];
  lineAlignments: LineAlignment[];
  lineWrapEnabled?: boolean[]; // Optional for backward compatibility
  timestamp: number;
}

export function PageBuilder({ pageId, deviceType: deviceTypeProp = "flagship", onClose, onSave }: PageBuilderProps) {
  const queryClient = useQueryClient();

  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();

  // Device type: from prop (new pages) or from existing page (editing)
  const [deviceType, setDeviceType] = useState<DeviceType>(deviceTypeProp);
  const dims = DEVICE_DIMENSIONS[deviceType] || DEVICE_DIMENSIONS.flagship;
  const numLines = dims.rows;

  // Helper to create arrays of the correct length
  const emptyLines = () => Array.from({ length: numLines }, () => "");
  const defaultAlignments = () => Array.from({ length: numLines }, () => "left" as LineAlignment);
  const defaultWraps = () => Array.from({ length: numLines }, () => false);

  // Form state (immediate - for UI responsiveness)
  const [name, setName] = useState("");
  const [templateLines, setTemplateLines] = useState<string[]>(emptyLines());
  const [lineAlignments, setLineAlignments] = useState<LineAlignment[]>(defaultAlignments());
  const [lineWrapEnabled, setLineWrapEnabled] = useState<boolean[]>(defaultWraps());
  const [preview, setPreview] = useState<string | null>(null);
  const [lastPreview, setLastPreview] = useState<string | null>(null); // Track last preview for smooth transitions
  const [isTransitioning, setIsTransitioning] = useState(false); // Track if we're transitioning between previews
  const [pendingPreview, setPendingPreview] = useState<string | null>(null); // Preview waiting to be shown after transition
  const [draftRestored, setDraftRestored] = useState(false);
  const [editorMode, setEditorMode] = useState<"rich" | "plain">("rich");

  // Debounced state (for expensive operations)
  const [debouncedTemplateLines, setDebouncedTemplateLines] = useState<string[]>(emptyLines());
  const [debouncedLineAlignments, setDebouncedLineAlignments] = useState<LineAlignment[]>(defaultAlignments());
  const [debouncedLineWrapEnabled, setDebouncedLineWrapEnabled] = useState<boolean[]>(defaultWraps());

  // Track if we need to re-preview after current mutation completes
  const needsRePreview = useRef(false);
  
  // Track if we're manually updating wrap to prevent onChange from overwriting state
  const isUpdatingWrap = useRef(false);
  
  // Track if content was cleared while a mutation is in flight (to ignore stale responses)
  const shouldIgnoreNextResponse = useRef(false);
  const transitionTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch existing page if editing
  const { data: existingPage, isLoading: loadingPage } = useQuery({
    queryKey: ["page", pageId],
    queryFn: () => api.getPage(pageId!),
    enabled: !!pageId,
  });


  // Load draft or existing page data
  useEffect(() => {
    if (existingPage) {
      // Clear draft when loading existing page
      const draftKey = getDraftKey(pageId);
      localStorage.removeItem(draftKey);
      
      // Set device type from existing page
      if (existingPage.device_type) {
        setDeviceType(existingPage.device_type);
      }
      
      const pageName = existingPage.name;
      setName(pageName);
      
      const existingDims = DEVICE_DIMENSIONS[existingPage.device_type || "flagship"] || DEVICE_DIMENSIONS.flagship;
      const existingNumLines = existingDims.rows;
      const rawLines = existingPage.template || emptyLines();
      // Extract alignments, wrap state, and clean content from stored lines
      const alignments: LineAlignment[] = [];
      const wrapStates: boolean[] = [];
      const contents: string[] = [];
      for (let i = 0; i < existingNumLines; i++) {
        const { alignment, wrapEnabled, content } = extractAlignment(rawLines[i] || "");
        alignments.push(alignment);
        wrapStates.push(wrapEnabled);
        contents.push(content);
      }
      setLineAlignments(alignments);
      setLineWrapEnabled(wrapStates);
      setTemplateLines(contents);
      // Initialize debounced state immediately when loading
      setDebouncedLineAlignments(alignments);
      setDebouncedLineWrapEnabled(wrapStates);
      setDebouncedTemplateLines(contents);
    } else if (!pageId && !loadingPage) {
      // Try to load draft for new page
      const draftKey = getDraftKey();
      try {
        const draftJson = localStorage.getItem(draftKey);
        if (draftJson) {
          const draft: DraftData = JSON.parse(draftJson);
            // Only restore if draft is less than 7 days old
            const draftAge = Date.now() - draft.timestamp;
            const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days
            
            if (draftAge < maxAge) {
              setName(draft.name || "");
              setTemplateLines(draft.templateLines || ["", "", "", "", "", ""]);
              setLineAlignments(draft.lineAlignments || ["left", "left", "left", "left", "left", "left"]);
              setLineWrapEnabled(draft.lineWrapEnabled || [false, false, false, false, false, false]);
              setDebouncedTemplateLines(draft.templateLines || ["", "", "", "", "", ""]);
              setDebouncedLineAlignments(draft.lineAlignments || ["left", "left", "left", "left", "left", "left"]);
              setDebouncedLineWrapEnabled(draft.lineWrapEnabled || [false, false, false, false, false, false]);
              setDraftRestored(true);
              
              // Auto-dismiss the alert after 5 seconds
              setTimeout(() => setDraftRestored(false), 5000);
          } else {
            // Draft too old, remove it
            localStorage.removeItem(draftKey);
          }
        }
      } catch {
        // Invalid draft data, remove it
        localStorage.removeItem(draftKey);
      }
    }
  }, [existingPage, pageId, loadingPage]);


  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedTemplateLines(templateLines);
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [templateLines]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedLineAlignments(lineAlignments);
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [lineAlignments]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedLineWrapEnabled(lineWrapEnabled);
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [lineWrapEnabled]);

  // Auto-save draft to localStorage (debounced)
  useEffect(() => {
    const draftKey = getDraftKey(pageId);
    
    // Don't save draft if we just loaded an existing page
    if (existingPage) {
      return;
    }
    
    // Debounce draft saving
    const timeoutId = setTimeout(() => {
      try {
        const draft: DraftData = {
          name,
          templateLines,
          lineAlignments,
          lineWrapEnabled,
          timestamp: Date.now(),
        };
        localStorage.setItem(draftKey, JSON.stringify(draft));
      } catch (error) {
        // Ignore localStorage errors (quota exceeded, etc.)
        console.warn("Failed to save draft:", error);
      }
    }, 1000); // Save draft 1 second after last change
    
    return () => clearTimeout(timeoutId);
  }, [name, templateLines, lineAlignments, lineWrapEnabled, pageId, existingPage]);


  // Auto-resize textareas when content changes
  useEffect(() => {
    // Wait for DOM to update, then resize all textareas
    const timer = setTimeout(() => {
      const textareas = document.querySelectorAll<HTMLTextAreaElement>('textarea[placeholder*="Use {{variable}} syntax"]');
      textareas.forEach(textarea => {
        textarea.style.height = 'auto';
        textarea.style.height = `${textarea.scrollHeight}px`;
      });
    }, 0);
    return () => clearTimeout(timer);
  }, [templateLines]);

  // Build template lines with alignment and wrap prefixes applied
  const getTemplateWithAlignments = (): string[] => {
    return templateLines.map((content, i) => applyAlignment(lineAlignments[i], lineWrapEnabled[i], content));
  };

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      const linesWithAlignments = getTemplateWithAlignments();
      if (pageId) {
        // Update existing page
        const payload: PageUpdate = {
          name,
          template: linesWithAlignments,
        };
        return api.updatePage(pageId, payload);
      } else {
        // Create new page
        const payload: PageCreate = {
          name,
          type: "template" as PageType,
          device_type: deviceType,
          template: linesWithAlignments,
        };
        return api.createPage(payload);
      }
    },
    onSuccess: (data) => {
      // Clear draft on successful save
      const draftKey = getDraftKey(pageId || data.id);
      localStorage.removeItem(draftKey);
      // Also clear the 'new' draft if this was a new page
      if (!pageId) {
        localStorage.removeItem(getDraftKey());
      }
      
      // Clear preview cache for this page
      const targetPageId = pageId || data.id;
      if (targetPageId) {
        clearPreviewCacheForPage(targetPageId);
      }
      
      // Invalidate pages list with active refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: 'active' });
      
      // Invalidate the specific page and its preview to bust the cache
      if (targetPageId) {
        queryClient.invalidateQueries({ queryKey: ["page", targetPageId], refetchType: 'active' });
        queryClient.invalidateQueries({ queryKey: queryKeys.pagePreview(targetPageId), refetchType: 'active' });
      }
      
      // Invalidate all page previews since they may have changed
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: 'active' });
      
      // If this page is currently active, refresh the active page data
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: 'active' });
      
      toast.success(pageId ? "Page updated" : "Page created");
      onSave?.();
      onClose();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => api.deletePage(pageId!),
    onSuccess: (data) => {
      // Clear preview cache for deleted page
      if (pageId) {
        clearPreviewCacheForPage(pageId);
      }
      
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: 'active' });
      
      // Invalidate the specific page and its preview to bust the cache
      if (pageId) {
        queryClient.invalidateQueries({ queryKey: ["page", pageId], refetchType: 'active' });
        queryClient.invalidateQueries({ queryKey: queryKeys.pagePreview(pageId), refetchType: 'active' });
      }
      
      // Invalidate all page previews
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: 'active' });
      
      // Also invalidate active page if it was updated
      if (data.active_page_updated) {
        queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
        queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: 'active' });
      }
      
      // Show appropriate message
      if (data.default_page_created) {
        toast.success("Page deleted. A default welcome page was created.");
      } else if (data.active_page_updated) {
        toast.success("Page deleted. Active display updated.");
      } else {
        toast.success("Page deleted");
      }
      onClose();
    },
    onError: () => {
      toast.error("Failed to delete page");
    },
  });

  // Build template lines with alignment prefixes applied (using debounced state for preview)
  const getDebouncedTemplateWithAlignments = (): string[] => {
    return debouncedTemplateLines.map((content, i) => applyAlignment(debouncedLineAlignments[i], debouncedLineWrapEnabled[i], content));
  };

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: async () => {
      const template = getDebouncedTemplateWithAlignments();
      console.log('[Preview] mutationFn called');
      console.log('[Preview] Template lines (raw):', debouncedTemplateLines);
      console.log('[Preview] Template with alignments:', template);
      console.log('[Preview] Wrap states:', debouncedLineWrapEnabled);
      
      // Validate template has content before sending to API
      // Check if all lines are empty (after removing alignment prefixes and trimming)
      const hasContent = template.some(line => {
        // Remove alignment/wrap prefixes to check actual content
        let content = line;
        // Remove wrap prefix first
        if (content.startsWith("{wrap}")) {
          content = content.slice(6);
        }
        // Remove alignment prefix
        if (content.startsWith("{center}")) {
          content = content.slice(8);
        } else if (content.startsWith("{right}")) {
          content = content.slice(7);
        } else if (content.startsWith("{left}")) {
          content = content.slice(6);
        }
        // Now check if there's actual content (not just whitespace)
        const hasLineContent = content.trim().length > 0;
        console.log(`[Preview] Line "${line}" -> content "${content}" -> hasContent: ${hasLineContent}`);
        return hasLineContent;
      });
      
      console.log('[Preview] Has content check result:', hasContent);
      
      if (!hasContent) {
        // Return empty response immediately without API call
        console.log('[Preview] Template is empty, returning empty response immediately');
        return { 
          rendered: "\n".repeat(5), // 6 empty lines (5 newlines)
          lines: ["", "", "", "", "", ""], 
          line_count: 6 
        };
      }
      
      console.log('[Preview] Calling API with template');
      return api.renderTemplate(template);
    },
    onSuccess: (data) => {
      console.log('[Preview] onSuccess called');
      console.log('[Preview] Response data:', data);
      console.log('[Preview] shouldIgnoreNextResponse:', shouldIgnoreNextResponse.current);
      console.log('[Preview] Current preview state:', preview);
      console.log('[Preview] Current debouncedTemplateLines:', debouncedTemplateLines);
      
      // Ignore response if content was cleared while request was in flight
      if (shouldIgnoreNextResponse.current) {
        console.log('[Preview] Ignoring response (content was cleared)');
        shouldIgnoreNextResponse.current = false;
        return;
      }
      
      // Double-check that we still have content before setting preview
      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
      console.log('[Preview] Has content check in onSuccess:', hasContent);
      if (!hasContent) {
        console.log('[Preview] No content, setting preview to null');
        setPreview(null);
        return;
      }
      
      // Also check if the API returned empty content (all blank lines)
      // This handles the case where API correctly identifies 6 blank lines as empty
      const renderedHasContent = data.rendered && data.rendered.trim().length > 0;
      console.log('[Preview] Rendered has content:', renderedHasContent, 'rendered length:', data.rendered?.length);
      if (!renderedHasContent) {
        console.log('[Preview] Rendered content is empty, setting preview to null');
        setPreview(null);
        return;
      }
      
      console.log('[Preview] Setting preview to:', data.rendered);
      
      // If we have a current preview, trigger transition: show loading, then new preview
      if (preview !== null && preview !== data.rendered) {
        console.log('[Preview] Preview changed, triggering transition');
        // Keep current preview visible, set loading state
        setLastPreview(preview);
        setIsTransitioning(true);
        setPendingPreview(data.rendered);
        
        // After a brief moment, show new preview (triggers transition)
        setTimeout(() => {
          setPreview(data.rendered);
          setIsTransitioning(false);
          setPendingPreview(null);
          if (data.rendered) {
            setLastPreview(data.rendered);
          }
        }, 100); // Brief delay to ensure loading state is visible
      } else {
        // No previous preview or same preview - set directly
        setPreview(data.rendered);
        if (data.rendered) {
          setLastPreview(data.rendered);
        }
      }
      
      // If changes occurred while this preview was rendering, trigger another preview
      if (needsRePreview.current) {
        console.log('[Preview] Needs re-preview, triggering another mutation');
        needsRePreview.current = false;
        previewMutation.mutate();
      }
    },
    onError: (error) => {
      console.log('[Preview] onError called:', error);
      setPreview(null);
      
      // Reset the flag on error too
      needsRePreview.current = false;
    },
  });

  // Auto-preview when debounced template lines or alignments change (debounced)
  useEffect(() => {
    console.log('[Preview] useEffect triggered');
    console.log('[Preview] debouncedTemplateLines:', debouncedTemplateLines);
    console.log('[Preview] previewMutation.isPending:', previewMutation.isPending);
    console.log('[Preview] Current preview:', preview);
    
    // Only preview if at least one line has content
    const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
    console.log('[Preview] Has content:', hasContent);
    
    if (!hasContent) {
      console.log('[Preview] No content detected, clearing preview');
      setPreview(null);
      // Reset re-preview flag when content becomes empty
      needsRePreview.current = false;
      // Mark that we should ignore any pending mutation responses
      if (previewMutation.isPending) {
        console.log('[Preview] Mutation is pending, setting ignore flag and resetting');
        shouldIgnoreNextResponse.current = true;
        previewMutation.reset();
      }
      return;
    }
    
    // Clear the ignore flag when we have content again
    shouldIgnoreNextResponse.current = false;

    // Debounce the preview (500ms after debounced state stabilizes)
    const timeoutId = setTimeout(() => {
      console.log('[Preview] Debounce timeout fired');
      // Double-check content again after debounce (in case it was cleared during debounce)
      const stillHasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
      console.log('[Preview] Still has content after debounce:', stillHasContent);
      
      if (!stillHasContent) {
        console.log('[Preview] Content cleared during debounce, clearing preview');
        setPreview(null);
        shouldIgnoreNextResponse.current = false;
        if (previewMutation.isPending) {
          console.log('[Preview] Mutation still pending, setting ignore flag');
          shouldIgnoreNextResponse.current = true;
          previewMutation.reset();
        }
        return;
      }
      
      // Only start a new preview if there isn't one already pending
      // If one is pending, set a flag so it re-runs after completion
      if (!previewMutation.isPending) {
        console.log('[Preview] Starting new mutation');
        previewMutation.mutate();
      } else {
        console.log('[Preview] Mutation already pending, setting needsRePreview flag');
        // Mark that we need to re-preview after the current mutation completes
        needsRePreview.current = true;
      }
    }, 500); // 500ms debounce

    return () => {
      console.log('[Preview] useEffect cleanup (timeout cleared)');
      clearTimeout(timeoutId);
      // Also clear transition timeout on cleanup
      if (transitionTimeoutRef.current) {
        clearTimeout(transitionTimeoutRef.current);
        transitionTimeoutRef.current = null;
      }
    };
  }, [debouncedTemplateLines, debouncedLineAlignments, debouncedLineWrapEnabled]);


  if (pageId && loadingPage) {
    return (
      <Card>
        <CardContent className="p-4 sm:p-6">
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="flex-1 min-h-0 w-full max-w-full overflow-x-hidden">
        {/* Main Editor */}
        <Card className="flex flex-col min-h-0 w-full max-w-full overflow-x-hidden">
          <CardHeader className="pb-1 flex-shrink-0 px-4 sm:px-6">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                <Wand2 className="h-4 w-4" />
                {pageId ? "Edit Page" : "Create Page"}
              </CardTitle>
              <div className="flex items-center gap-1">
                {/* Save button */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9"
                  onClick={() => saveMutation.mutate()}
                  disabled={!name.trim() || saveMutation.isPending}
                  title={saveMutation.isPending ? "Saving..." : "Save Page"}
                >
                  <Save className="h-4 w-4" />
                </Button>
                
                {/* Delete button - only show when editing */}
                {pageId && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-9 w-9 text-destructive hover:text-destructive hover:bg-destructive/10"
                        title="Delete Page"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Page</AlertDialogTitle>
                        <AlertDialogDescription>
                          Are you sure you want to delete &quot;{name || "this page"}&quot;? This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate()}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {deleteMutation.isPending ? "Deleting..." : "Delete"}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="h-9 w-9" 
                  onClick={onClose}
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex flex-col flex-1 min-h-0 space-y-4 overflow-y-auto overflow-x-hidden px-3 sm:px-4 md:px-6 pt-2">
            {/* Draft restored notification */}
            {draftRestored && (
              <Alert className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
                <AlertDescription className="text-sm text-blue-900 dark:text-blue-100">
                  Draft restored from your previous session. Your work has been automatically saved.
                </AlertDescription>
              </Alert>
            )}
            
            {/* Page name */}
            <div className="space-y-1.5">
              <label className="text-xs sm:text-sm font-medium">Page Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Custom Page"
                className="w-full h-10 sm:h-9 px-3 text-sm rounded-md border bg-background"
              />
            </div>

            {/* Template line editors */}
            <div className="space-y-3">
              <Tabs value={editorMode} onValueChange={(value) => setEditorMode(value as "rich" | "plain")}>
                <TabsList className="grid w-full max-w-md grid-cols-2">
                  <TabsTrigger value="rich">Rich Editor</TabsTrigger>
                  <TabsTrigger value="plain">Plain Text</TabsTrigger>
                </TabsList>
                
                <TabsContent value="rich" className="mt-4">
                  {/* Template editor with device-specific dimensions */}
                  <TipTapTemplateEditor
                    value={(() => {
                      // Always ensure clean content without alignment prefixes for rich editor
                      return templateLines.map(line => {
                        const { content } = extractAlignment(line);
                        return content;
                      }).join('\n');
                    })()}
                    onChange={(newValue) => {
                      // Skip parsing if we're manually updating wrap (to prevent state overwrite)
                      if (isUpdatingWrap.current) {
                        return;
                      }
                      
                      // Parse the plain text back into lines and strip any alignment prefixes
                      const lines = newValue.split('\n').slice(0, numLines);
                      const newLines: string[] = [];
                      
                      for (let i = 0; i < numLines; i++) {
                        // Strip any alignment prefixes that might have been typed
                        const { content } = extractAlignment(lines[i] || '');
                        newLines.push(content);
                      }
                      
                      setTemplateLines(newLines);
                    }}
                    lineAlignments={lineAlignments}
                    lineWrapEnabled={lineWrapEnabled}
                    onLineAlignmentChange={(lineIndex, alignment) => {
                      const newAlignments = [...lineAlignments];
                      newAlignments[lineIndex] = alignment;
                      setLineAlignments(newAlignments);
                    }}
                    onLineWrapChange={(lineIndex, wrapEnabled) => {
                      const newWrapStates = [...lineWrapEnabled];
                      newWrapStates[lineIndex] = wrapEnabled;
                      setLineWrapEnabled(newWrapStates);
                    }}
                    placeholder="Type template syntax like {{weather.temp}} or {{red}} for color tiles"
                    showAlignmentControls={true}
                    showToolbar={true}
                    boardWidth={dims.cols}
                    boardLines={numLines}
                  />
                </TabsContent>
                
                <TabsContent value="plain" className="mt-4">
                  <PlainTextEditor
                    value={getTemplateWithAlignments().join('\n')}
                    onChange={(newValue) => {
                      // Parse raw text back into template lines and alignments
                      const lines = newValue.split('\n');
                      const newContents: string[] = [];
                      const newAlignments: LineAlignment[] = [];
                      const newWrapStates: boolean[] = [];
                      
                      for (let i = 0; i < numLines; i++) {
                        const line = lines[i] || "";
                        const { alignment, wrapEnabled, content } = extractAlignment(line);
                        newAlignments.push(alignment);
                        newWrapStates.push(wrapEnabled);
                        newContents.push(content);
                      }
                      
                      setTemplateLines(newContents);
                      setLineAlignments(newAlignments);
                      setLineWrapEnabled(newWrapStates);
                    }}
                    placeholder="Type your template text with alignment prefixes like {center}, {right}, {wrap}"
                  />
                </TabsContent>
              </Tabs>

              {/* Live preview */}
              <div className="mt-4">
                <label className="text-xs sm:text-sm font-medium mb-2 block">Preview</label>
                <div className="flex justify-center">
                  <BoardDisplay 
                    message={(() => {
                      // Use new loading pattern: keep previous message visible during loading/transition
                      // This allows tiles to cycle through characters (like real FiestaBoard)
                      // instead of showing legacy FlipTiles
                      
                      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
                      const isPending = previewMutation.isPending;
                      const shouldIgnore = shouldIgnoreNextResponse.current;
                      
                      // If we're transitioning, show the last preview (old message) so tiles can transition to new one
                      if (isTransitioning && lastPreview) {
                        console.log('[Preview] Message: transitioning, showing last preview for smooth transition');
                        return lastPreview;
                      }
                      
                      // If we have a preview, use it (new message)
                      if (preview !== null) {
                        console.log('[Preview] Message: using preview value:', preview);
                        return preview;
                      }
                      
                      // If no content and not loading, show blank grid
                      if (!hasContent && !isPending && !shouldIgnore) {
                        console.log('[Preview] Message: returning empty string for blank grid');
                        return "";
                      }
                      
                      // If we're loading and have previous content, keep showing the last preview
                      // This allows tiles to cycle during loading instead of showing FlipTiles
                      // The isLoading prop will handle the cycling animation on actual CharTiles
                      if (isPending && hasContent && !shouldIgnore && lastPreview) {
                        console.log('[Preview] Message: loading with content, keeping last preview for tile cycling');
                        return lastPreview;
                      }
                      
                      // If we're loading but no last preview, show blank grid (tiles will cycle)
                      if (isPending && hasContent && !shouldIgnore) {
                        console.log('[Preview] Message: loading with content but no last preview, showing blank');
                        return "";
                      }
                      
                      // Default: return null (shows FlipTiles - only for initial state with no content)
                      console.log('[Preview] Message: returning null (will show FlipTiles)');
                      return null;
                    })()}
                    isLoading={(() => {
                      // Use new loading pattern: show loading when fetching new preview OR transitioning
                      // This triggers tile cycling animation on actual CharTiles
                      
                      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
                      const isPending = previewMutation.isPending;
                      const shouldIgnore = shouldIgnoreNextResponse.current;
                      
                      console.log('[Preview] Loading state calculation:');
                      console.log('  - hasContent:', hasContent);
                      console.log('  - preview:', preview);
                      console.log('  - isPending:', isPending);
                      console.log('  - isTransitioning:', isTransitioning);
                      console.log('  - shouldIgnore:', shouldIgnore);
                      
                      // If we're transitioning between previews, show loading
                      if (isTransitioning) {
                        console.log('[Preview] Transitioning between previews, isLoading = true');
                        return true;
                      }
                      
                      // If we have a preview value and not transitioning, not loading (mutation completed)
                      if (preview !== null && !isTransitioning) {
                        console.log('[Preview] Has preview, isLoading = false');
                        return false;
                      }
                      
                      // If no content, show blank (not loading)
                      if (!hasContent) {
                        console.log('[Preview] No content, isLoading = false');
                        return false;
                      }
                      
                      // Don't show loading if we're ignoring the next response (content was cleared)
                      if (shouldIgnore) {
                        console.log('[Preview] Ignoring response, isLoading = false');
                        return false;
                      }
                      
                      // Show loading if we're fetching and have content
                      // This will trigger tile cycling on the current/last message
                      const result = isPending && hasContent;
                      console.log('[Preview] Final isLoading:', result);
                      return result;
                    })()}
                    size="md"
                    boardType={boardSettings?.board_type ?? "black"}
                    deviceType={deviceType}
                  />
                </div>
              </div>

            </div>
          </CardContent>
        </Card>

      </div>
    </>
  );
}

