"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BoardDisplay } from "@/components/board-display";
import { PlainTextEditor } from "@/components/plain-text-editor";

// Direct import – bypasses next/dynamic chunk caching issues in dev mode.
// TipTap's useEditor({ immediatelyRender: false }) handles SSR safely.
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { queryKeys } from "@/hooks/use-board";
import {
  ArrowLeft,
  Save,
  Trash2,
  Radio,
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
import { api, PageCreate, PageUpdate, PageType, DeviceType, BoardInstance, LineAlignment, LineMetadata } from "@/lib/api";
import { useBoardSettings, getEffectiveBoardColor } from "@/hooks/use-board";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";
import { DEVICE_DIMENSIONS } from "@/components/tiptap-template-editor/utils/constants";
import { writeLiveOutputMessage, onLiveOutputMessageChange } from "@/lib/live-output-channel";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";



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

const EDITOR_MODE_KEY = "fiestaboard_editor_mode";

function getStoredEditorMode(): "rich" | "plain" {
  if (typeof window === "undefined") return "rich";
  try {
    const stored = localStorage.getItem(EDITOR_MODE_KEY);
    if (stored === "rich" || stored === "plain") return stored;
  } catch {}
  return "rich";
}

interface DraftData {
  name: string;
  templateLines: string[];
  lineAlignments: LineAlignment[];
  lineWrapEnabled?: boolean[]; // Optional for backward compatibility
  timestamp: number;
}

export function PageBuilder({ pageId, deviceType: deviceTypeProp = "flagship", onClose, onSave }: PageBuilderProps) {
  const t = useTranslations("pageBuilder");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();

  // Device type: from prop (new pages) or from existing page (editing)
  const [deviceType, setDeviceType] = useState<DeviceType>(deviceTypeProp);
  const dims = DEVICE_DIMENSIONS[deviceType] || DEVICE_DIMENSIONS.flagship;
  const numLines = dims.rows;

  // Preview board color - defaults to the user's configured board color
  const defaultBoardColor = getEffectiveBoardColor(boardSettings);
  const [previewBoardColor, setPreviewBoardColor] = useState<"black" | "white" | null>(null);
  const effectiveBoardColor = previewBoardColor ?? defaultBoardColor;

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
  const [_pendingPreview, setPendingPreview] = useState<string | null>(null); // Preview waiting to be shown after transition
  const [draftRestored, setDraftRestored] = useState(false);
  const [editorMode, setEditorMode] = useState<"rich" | "plain">(getStoredEditorMode);

  const handleEditorModeChange = useCallback((mode: "rich" | "plain") => {
    setEditorMode(mode);
    try {
      localStorage.setItem(EDITOR_MODE_KEY, mode);
    } catch {}
  }, []);

  // Derive line count from templateLines — single source of truth avoids
  // desync when switching between Rich and Plain Text editors.
  const lineCount = templateLines.length;

  // Live output mode state
  const [liveOutputEnabled, setLiveOutputEnabled] = useState(false);
  const [selectedBoardId, setSelectedBoardId] = useState<string>("");
  const lastLiveSentPreview = useRef<string | null>(null);
  // Ref-tracked copy of lastPreview so the liveOutputEnabled effect can read it
  // synchronously without a stale closure (avoids adding lastPreview as a dep).
  const lastPreviewRef = useRef<string | null>(null);
  const liveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const liveOutputEnabledRef = useRef(false);
  const liveAbortRef = useRef<AbortController | null>(null);
  const liveDebounceRef = useRef<NodeJS.Timeout | null>(null);

  const LIVE_OUTPUT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

  const disableLiveOutput = useCallback(() => {
    setLiveOutputEnabled(false);
    lastLiveSentPreview.current = null;
    toast.info(t("toastLiveOutputOff"));
  }, []);

  // Debounced state (for expensive operations)
  const [debouncedTemplateLines, setDebouncedTemplateLines] = useState<string[]>(emptyLines());
  const [debouncedLineAlignments, setDebouncedLineAlignments] = useState<LineAlignment[]>(defaultAlignments());
  const [debouncedLineWrapEnabled, setDebouncedLineWrapEnabled] = useState<boolean[]>(defaultWraps());

  // Auto-timeout: disable live mode after inactivity
  useEffect(() => {
    if (!liveOutputEnabled) {
      if (liveTimeoutRef.current) {
        clearTimeout(liveTimeoutRef.current);
        liveTimeoutRef.current = null;
      }
      return;
    }

    if (liveTimeoutRef.current) {
      clearTimeout(liveTimeoutRef.current);
    }
    liveTimeoutRef.current = setTimeout(disableLiveOutput, LIVE_OUTPUT_TIMEOUT_MS);

    return () => {
      if (liveTimeoutRef.current) {
        clearTimeout(liveTimeoutRef.current);
        liveTimeoutRef.current = null;
      }
    };
  }, [liveOutputEnabled, debouncedTemplateLines, debouncedLineAlignments, debouncedLineWrapEnabled, disableLiveOutput]);

  // Keep lastPreviewRef in sync so the transition effect below can read the
  // current preview without creating a stale closure.
  useEffect(() => {
    lastPreviewRef.current = lastPreview;
  }, [lastPreview]);

  // Keep ref in sync with state so cleanup can access latest value.
  // On enable → prime the shared cache immediately so the Home page shows the
  // current page content even if the user navigates before the first async
  // live-render completes (100 ms debounce + API round-trip).
  // On disable → clear the cache and restore the board to its scheduled page.
  useEffect(() => {
    if (!liveOutputEnabledRef.current && liveOutputEnabled) {
      // Live output just enabled — prime the Home page cache with the current
      // page preview so there is no gap between enabling and first live render.
      if (lastPreviewRef.current) {
        queryClient.setQueryData(["liveOutputMessage"], lastPreviewRef.current);
        writeLiveOutputMessage(lastPreviewRef.current);
      }
    } else if (liveOutputEnabledRef.current && !liveOutputEnabled) {
      // Live output disabled — clear the cache and restore the board.
      queryClient.setQueryData(["liveOutputMessage"], null);
      writeLiveOutputMessage(null);
      api.forceRefresh().catch(() => {
        // Silently ignore errors during cleanup
      });
    }
    liveOutputEnabledRef.current = liveOutputEnabled;
  }, [liveOutputEnabled]);

  // Restore board display when component unmounts if live output was active.
  // Also clear the shared live-output cache + localStorage so the Home page
  // does not stay stuck on a pulsing "Live Mode" badge after navigation.
  // Without this, the inactivity timeout (which is bound to this component's
  // lifetime) never gets a chance to fire after unmount, leaving the live
  // state set indefinitely.
  useEffect(() => {
    return () => {
      if (liveOutputEnabledRef.current) {
        queryClient.setQueryData(["liveOutputMessage"], null);
        writeLiveOutputMessage(null);
        api.forceRefresh().catch(() => {
          // Silently ignore errors during cleanup
        });
      }
    };
  }, [queryClient]);

  // Listen for cross-tab kill signals: when another tab (e.g. the Home page's
  // "Turn off Live Mode" button) clears the live-output channel, also turn off
  // this tab's live toggle. Without this, a different tab with the editor
  // still open would keep firing /templates/render/live and immediately
  // re-establish live mode, defeating the home-page kill switch.
  useEffect(() => {
    return onLiveOutputMessageChange((msg) => {
      if (msg === null && liveOutputEnabledRef.current) {
        setLiveOutputEnabled(false);
      }
    });
  }, []);

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
      
      const rawLines = existingPage.template || emptyLines();
      const meta = existingPage.line_metadata;

      const alignments: LineAlignment[] = [];
      const wrapStates: boolean[] = [];
      const contents: string[] = [];
      for (let i = 0; i < rawLines.length; i++) {
        contents.push(rawLines[i] || "");
        if (meta && i < meta.length) {
          alignments.push(meta[i].alignment);
          wrapStates.push(meta[i].wrap);
        } else {
          alignments.push("left");
          wrapStates.push(false);
        }
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
              const restoredLines = draft.templateLines || ["", "", "", "", "", ""];
              setName(draft.name || "");
              setTemplateLines(restoredLines);
              setLineAlignments(draft.lineAlignments || ["left", "left", "left", "left", "left", "left"]);
              setLineWrapEnabled(draft.lineWrapEnabled || [false, false, false, false, false, false]);
              setDebouncedTemplateLines(restoredLines);
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
    }, 150);
    return () => clearTimeout(timeoutId);
  }, [templateLines]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedLineAlignments(lineAlignments);
    }, 150);
    return () => clearTimeout(timeoutId);
  }, [lineAlignments]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedLineWrapEnabled(lineWrapEnabled);
    }, 150);
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

  /**
   * Parse inline {wrap} and {left}/{center}/{right} prefixes from template
   * lines, strip them from content, and merge with the UI alignment/wrap
   * state.  Inline prefixes (used in the plain-text editor) take precedence.
   */
  const processLinesWithPrefixes = (
    lines: string[],
    alignments: LineAlignment[],
    wraps: boolean[],
  ): { cleanedLines: string[]; metadata: LineMetadata[] } => {
    const ALIGN_RE = /^\{(left|center|right)\}/i;
    const cleanedLines: string[] = [];
    const metadata: LineMetadata[] = [];

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      let alignment: LineAlignment = alignments[i] || "left";
      let wrap = wraps[i] || false;

      if (line.startsWith("{wrap}")) {
        wrap = true;
        line = line.substring(6);
      }

      const m = line.match(ALIGN_RE);
      if (m) {
        alignment = m[1].toLowerCase() as LineAlignment;
        line = line.substring(m[0].length);
      }

      cleanedLines.push(line);
      metadata.push({ alignment, wrap });
    }

    return { cleanedLines, metadata };
  };

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      const { cleanedLines, metadata } = processLinesWithPrefixes(templateLines, lineAlignments, lineWrapEnabled);
      if (pageId) {
        const payload: PageUpdate = {
          name,
          template: cleanedLines,
          line_metadata: metadata,
        };
        return api.updatePage(pageId, payload);
      } else {
        const payload: PageCreate = {
          name,
          type: "template" as PageType,
          device_type: deviceType,
          template: cleanedLines,
          line_metadata: metadata,
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
      
      toast.success(pageId ? t("toastPageUpdated") : t("toastPageCreated"));
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
        toast.success(t("toastDeletedDefaultCreated"));
      } else if (data.active_page_updated) {
        toast.success(t("toastDeletedActiveUpdated"));
      } else {
        toast.success(t("toastPageDeleted"));
      }
      onClose();
    },
    onError: () => {
      toast.error(t("toastDeleteFailed"));
    },
  });

  // Sync from current board display mutation (new pages only)
  const syncFromBoardMutation = useMutation({
    mutationFn: () => api.getCurrentDisplay(),
    retry: false, // No-active-page (404) is not a transient error; don't retry
    onSuccess: (data) => {
      const lines = data.template || [];
      setTemplateLines(lines);
      setDebouncedTemplateLines(lines);

      if (data.line_metadata) {
        const alignments = data.line_metadata.map((m) => m.alignment);
        const wraps = data.line_metadata.map((m) => m.wrap);
        setLineAlignments(alignments);
        setLineWrapEnabled(wraps);
        setDebouncedLineAlignments(alignments);
        setDebouncedLineWrapEnabled(wraps);
      } else {
        const defaults = lines.map(() => "left" as LineAlignment);
        const defaultWraps = lines.map(() => false);
        setLineAlignments(defaults);
        setLineWrapEnabled(defaultWraps);
        setDebouncedLineAlignments(defaults);
        setDebouncedLineWrapEnabled(defaultWraps);
      }

      if (data.device_type) {
        setDeviceType(data.device_type);
      }

      toast.success(t("toastSyncedFrom", { name: data.page_name }));
    },
    onError: () => {
      toast.error(t("toastNoActiveDisplay"));
    },
  });

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: async () => {
      const { cleanedLines, metadata } = processLinesWithPrefixes(debouncedTemplateLines, debouncedLineAlignments, debouncedLineWrapEnabled);

      const hasContent = cleanedLines.some(line => line.trim().length > 0);
      
      if (!hasContent) {
        const emptyCount = dims.rows;
        return { 
          rendered: "\n".repeat(emptyCount - 1),
          lines: Array.from({ length: emptyCount }, () => ""), 
          line_count: emptyCount 
        };
      }
      
      return api.renderTemplate(cleanedLines, metadata, deviceType);
    },
    onSuccess: (data) => {
      if (shouldIgnoreNextResponse.current) {
        shouldIgnoreNextResponse.current = false;
        return;
      }
      
      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
      if (!hasContent) {
        setPreview(null);
        return;
      }
      
      const renderedHasContent = data.rendered && data.rendered.trim().length > 0;
      if (!renderedHasContent) {
        setPreview(null);
        return;
      }
      
      if (preview !== null && preview !== data.rendered) {
        setLastPreview(preview);
        setIsTransitioning(true);
        setPendingPreview(data.rendered);
        
        setTimeout(() => {
          setPreview(data.rendered);
          setIsTransitioning(false);
          setPendingPreview(null);
          if (data.rendered) {
            setLastPreview(data.rendered);
          }
        }, 100);
      } else {
        setPreview(data.rendered);
        if (data.rendered) {
          setLastPreview(data.rendered);
        }
      }
      
      if (needsRePreview.current) {
        needsRePreview.current = false;
        previewMutation.mutate();
      }
    },
    onError: () => {
      setPreview(null);
      needsRePreview.current = false;
    },
  });

  // Auto-preview when debounced template lines or alignments change (debounced)
  // Skipped when live mode is on — the live fast path handles preview updates directly.
  useEffect(() => {
    if (liveOutputEnabled) {
      needsRePreview.current = false;
      if (previewMutation.isPending) {
        shouldIgnoreNextResponse.current = true;
        previewMutation.reset();
      }
      return;
    }

    const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
    
    if (!hasContent) {
      setPreview(null);
      needsRePreview.current = false;
      if (previewMutation.isPending) {
        shouldIgnoreNextResponse.current = true;
        previewMutation.reset();
      }
      return;
    }
    
    shouldIgnoreNextResponse.current = false;

    const timeoutId = setTimeout(() => {
      const stillHasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
      
      if (!stillHasContent) {
        setPreview(null);
        shouldIgnoreNextResponse.current = false;
        if (previewMutation.isPending) {
          shouldIgnoreNextResponse.current = true;
          previewMutation.reset();
        }
        return;
      }
      
      if (!previewMutation.isPending) {
        previewMutation.mutate();
      } else {
        needsRePreview.current = true;
      }
    }, 200);

    return () => {
      clearTimeout(timeoutId);
      // Also clear transition timeout on cleanup
      if (transitionTimeoutRef.current) {
        clearTimeout(transitionTimeoutRef.current);
        transitionTimeoutRef.current = null;
      }
    };
  }, [debouncedTemplateLines, debouncedLineAlignments, debouncedLineWrapEnabled, liveOutputEnabled]);

  // Live output mutation - sends rendered preview to the board
  const liveSendMutation = useMutation({
    mutationFn: async (_rendered: string) => {
      const { cleanedLines, metadata } = processLinesWithPrefixes(debouncedTemplateLines, debouncedLineAlignments, debouncedLineWrapEnabled);
      return api.renderTemplateLive(cleanedLines, selectedBoardId || undefined, metadata, deviceType);
    },
    onSuccess: (data) => {
      if (data.sent_to_board) {
        lastLiveSentPreview.current = preview;
        // Broadcast to the Home page so its virtual board reflects the live content.
        queryClient.setQueryData(["liveOutputMessage"], data.rendered);
        writeLiveOutputMessage(data.rendered);
      }
    },
    onError: (error: Error) => {
      console.error('[LiveOutput] Send failed:', error.message);
      toast.error(t("toastLiveSendFailed"));
    },
  });

  // Legacy live send path — only used as fallback when fast path hasn't handled the update.
  // The fast path sets lastLiveSentPreview to match preview, so this is effectively a no-op
  // when live mode is active. Kept for safety if the fast path request fails.
  useEffect(() => {
    if (!liveOutputEnabled || !preview || preview === lastLiveSentPreview.current) {
      return;
    }

    const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
    if (!hasContent) return;

    if (!liveSendMutation.isPending) {
      liveSendMutation.mutate(preview);
    }
  }, [preview, liveOutputEnabled]);

  // Live edit fast path: single 100ms debounce → single API call → preview + board update.
  // Bypasses the normal double-debounce (150ms + 200ms) and double API call chain.
  // Uses IMMEDIATE state (not debounced) and AbortController to cancel stale requests.
  useEffect(() => {
    if (!liveOutputEnabled) {
      if (liveDebounceRef.current) {
        clearTimeout(liveDebounceRef.current);
        liveDebounceRef.current = null;
      }
      if (liveAbortRef.current) {
        liveAbortRef.current.abort();
        liveAbortRef.current = null;
      }
      return;
    }

    const hasContent = templateLines.some(line => line.trim().length > 0);
    if (!hasContent) {
      if (liveAbortRef.current) {
        liveAbortRef.current.abort();
        liveAbortRef.current = null;
      }
      setPreview(null);
      lastLiveSentPreview.current = null;
      return;
    }

    if (liveDebounceRef.current) {
      clearTimeout(liveDebounceRef.current);
    }

    liveDebounceRef.current = setTimeout(async () => {
      if (liveAbortRef.current) {
        liveAbortRef.current.abort();
      }

      const controller = new AbortController();
      liveAbortRef.current = controller;

      try {
        const { cleanedLines, metadata } = processLinesWithPrefixes(
          templateLines, lineAlignments, lineWrapEnabled
        );

        const data = await api.renderTemplateLive(
          cleanedLines,
          selectedBoardId || undefined,
          metadata,
          deviceType,
          controller.signal
        );

        if (controller.signal.aborted) return;

        setPreview(data.rendered);
        if (data.rendered) {
          setLastPreview(data.rendered);
        }
        lastLiveSentPreview.current = data.rendered;
        // Broadcast to the Home page (same tab and other tabs) so navigating there shows this content.
        queryClient.setQueryData(["liveOutputMessage"], data.rendered);
        writeLiveOutputMessage(data.rendered);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        console.error('[LiveFastPath] Error:', error);
      }
    }, 100);

    return () => {
      if (liveDebounceRef.current) {
        clearTimeout(liveDebounceRef.current);
      }
      if (liveAbortRef.current) {
        liveAbortRef.current.abort();
        liveAbortRef.current = null;
      }
    };
  }, [liveOutputEnabled, templateLines, lineAlignments, lineWrapEnabled, selectedBoardId]);

  // Initialize selected board to first board when settings load
  useEffect(() => {
    if (boardSettings?.boards?.length && !selectedBoardId) {
      setSelectedBoardId(boardSettings.boards[0].id);
    }
  }, [boardSettings?.boards, selectedBoardId]);


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
              <div className="flex items-center gap-2 min-w-0">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={onClose}
                  aria-label={t("backToPages")}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <CardTitle className="text-base sm:text-lg truncate">
                  {pageId ? t("editPage") : t("createPage")}
                </CardTitle>
              </div>
              <TooltipProvider>
              <div className="flex items-center gap-1.5">
                {/* Editor mode toggle */}
                <div className="flex items-center border rounded-md" role="group" aria-label={t("editorModeAriaLabel")}>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleEditorModeChange("rich")}
                    className={`h-7 px-2 text-[11px] rounded-r-none ${editorMode === "rich" ? "bg-brand-emphasis text-brand-foreground hover:bg-brand-emphasis/85 hover:text-brand-foreground" : ""}`}
                    aria-label={t("richEditorAriaLabel")}
                    aria-pressed={editorMode === "rich"}
                  >
                    {t("richEditor")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleEditorModeChange("plain")}
                    className={`h-7 px-2 text-[11px] rounded-l-none ${editorMode === "plain" ? "bg-brand-emphasis text-brand-foreground hover:bg-brand-emphasis/85 hover:text-brand-foreground" : ""}`}
                    aria-label={t("plainTextAriaLabel")}
                    aria-pressed={editorMode === "plain"}
                  >
                    {t("plainEditor")}
                  </Button>
                </div>
                {/* Delete button - only show when editing */}
                {pageId && (
                  <AlertDialog>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 text-destructive hover:text-destructive hover:bg-destructive/10"
                            aria-label={t("deletePageTooltip")}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </AlertDialogTrigger>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{t("deletePageTooltip")}</p>
                      </TooltipContent>
                    </Tooltip>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>{t("deletePageTitle")}</AlertDialogTitle>
                        <AlertDialogDescription>
                          {name
                            ? t("deletePageConfirmation", { pageName: name })
                            : t("deletePageConfirmationGeneric")}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate()}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {deleteMutation.isPending ? tCommon("deleting") : tCommon("delete")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
                {/* Save button */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="brand"
                      size="sm"
                      className="h-8 gap-1.5 px-3"
                      onClick={() => saveMutation.mutate()}
                      disabled={!name.trim() || saveMutation.isPending}
                      aria-label={t("savePageAriaLabel")}
                    >
                      <Save className="h-3.5 w-3.5" />
                      <span className="text-xs">{saveMutation.isPending ? tCommon("saving") : t("savePage")}</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{t("savePageTooltip")}</p>
                  </TooltipContent>
                </Tooltip>
              </div>
              </TooltipProvider>
            </div>
          </CardHeader>

          <CardContent className="flex flex-col flex-1 min-h-0 px-3 sm:px-4 md:px-6 pt-2">
            <ScrollArea className="flex-1 min-h-0 space-y-4">
            {/* Draft restored notification */}
            {draftRestored && (
              <Alert className="bg-info/10 border-info/20">
                <AlertDescription className="text-sm">
                  {t("draftRestored")}
                </AlertDescription>
              </Alert>
            )}

            {/* Page name */}
            <div className="space-y-1.5">
              <label className="text-xs sm:text-sm font-medium">{t("pageNameLabel")}</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("pageNamePlaceholder")}
                className="w-full h-10 sm:h-9 px-3 text-sm rounded-md border bg-background"
              />
            </div>

            {/* Template line editors */}
            <div className="space-y-3">
              {editorMode === "rich" ? (
                <div>
                  {/* Template editor with device-specific dimensions */}
                  <TipTapTemplateEditor
                    value={templateLines.join('\n')}
                    onChange={(newValue) => {
                      if (isUpdatingWrap.current) {
                        return;
                      }
                      const lines = newValue.split('\n');
                      setTemplateLines(lines);

                      const oldLen = templateLines.length;
                      const newLen = lines.length;
                      if (newLen !== oldLen) {
                        let prefixMatch = 0;
                        while (prefixMatch < Math.min(newLen, oldLen) && lines[prefixMatch] === templateLines[prefixMatch]) {
                          prefixMatch++;
                        }
                        let suffixMatch = 0;
                        while (suffixMatch < Math.min(newLen, oldLen) - prefixMatch &&
                               lines[newLen - 1 - suffixMatch] === templateLines[oldLen - 1 - suffixMatch]) {
                          suffixMatch++;
                        }

                        const updatedAlignments = [...lineAlignments];
                        const updatedWrap = [...lineWrapEnabled];

                        if (newLen < oldLen) {
                          const deleteCount = oldLen - newLen;
                          const deleteStart = prefixMatch + (newLen - prefixMatch - suffixMatch);
                          updatedAlignments.splice(deleteStart, deleteCount);
                          updatedWrap.splice(deleteStart, deleteCount);
                        } else {
                          const insertCount = newLen - oldLen;
                          const insertStart = prefixMatch + (oldLen - prefixMatch - suffixMatch);
                          for (let i = 0; i < insertCount; i++) {
                            updatedAlignments.splice(insertStart + i, 0, "left");
                            updatedWrap.splice(insertStart + i, 0, false);
                          }
                        }

                        while (updatedAlignments.length < newLen) updatedAlignments.push("left");
                        while (updatedWrap.length < newLen) updatedWrap.push(false);
                        updatedAlignments.length = newLen;
                        updatedWrap.length = newLen;

                        setLineAlignments(updatedAlignments);
                        setLineWrapEnabled(updatedWrap);
                      }
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
                    placeholder={t("richEditorPlaceholder")}
                    showAlignmentControls={true}
                    showToolbar={true}
                    boardWidth={dims.cols}
                    boardLines={numLines}
                    deviceType={deviceType}
                    onSyncFromBoard={!pageId ? () => syncFromBoardMutation.mutate() : undefined}
                    syncFromBoardPending={syncFromBoardMutation.isPending}
                  />
                </div>
              ) : (
                <div>
                  <PlainTextEditor
                    value={templateLines.join('\n')}
                    onChange={(newValue) => {
                      setTemplateLines(newValue.split('\n'));
                    }}
                    placeholder={t("plainEditorPlaceholder")}
                    boardLines={numLines}
                    boardWidth={dims.cols}
                  />
                </div>
              )}

              {/* Line count validation warning */}
              {lineCount > numLines && (
                <div className="flex items-start gap-2 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-warning">
                  <span className="font-medium shrink-0">{t("warningLabel")}</span>
                  <span>
                    {t("lineCountWarning", { lineCount, maxLines: numLines })}
                  </span>
                </div>
              )}

              {/* Live preview */}
              <div className="mt-4">
                <div className="flex flex-wrap items-center justify-between gap-y-1 mb-2">
                  <label className="text-xs sm:text-sm font-medium">{t("previewLabel")}</label>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-muted-foreground mr-0.5">{t("boardColorLabel")}</span>
                    <button
                      onClick={() => setPreviewBoardColor("black")}
                      aria-label={t("previewAsBlack")}
                      className={`h-5 w-5 rounded-full border-2 bg-board-surface-dark transition-colors ${
                        effectiveBoardColor === "black"
                          ? "border-primary ring-1 ring-primary/30"
                          : "border-border hover:border-muted-foreground"
                      }`}
                    />
                    <button
                      onClick={() => setPreviewBoardColor("white")}
                      aria-label={t("previewAsWhite")}
                      className={`h-5 w-5 rounded-full border-2 bg-board-surface-light transition-colors ${
                        effectiveBoardColor === "white"
                          ? "border-primary ring-1 ring-primary/30"
                          : "border-border hover:border-muted-foreground"
                      }`}
                    />
                  </div>
                </div>
                <div className="flex justify-center">
                  <BoardDisplay 
                    message={(() => {
                      // Use new loading pattern: keep previous message visible during loading/transition
                      // This allows tiles to cycle through characters (like real FiestaBoard)
                      // instead of showing legacy FlipTiles
                      
                      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
                      const isPending = previewMutation.isPending;
                      const shouldIgnore = shouldIgnoreNextResponse.current;
                      
                      if (isTransitioning && lastPreview) return lastPreview;
                      if (preview !== null) return preview;
                      if (!hasContent && !isPending && !shouldIgnore) return "";
                      if (isPending && hasContent && !shouldIgnore && lastPreview) return lastPreview;
                      if (isPending && hasContent && !shouldIgnore) return "";
                      return null;
                    })()}
                    isLoading={(() => {
                      const hasContent = debouncedTemplateLines.some(line => line.trim().length > 0);
                      const isPending = previewMutation.isPending;
                      const shouldIgnore = shouldIgnoreNextResponse.current;
                      
                      if (isTransitioning) return true;
                      if (preview !== null && !isTransitioning) return false;
                      if (!hasContent) return false;
                      if (shouldIgnore) return false;
                      return isPending && hasContent;
                    })()}
                    size="md"
                    boardType={effectiveBoardColor}
                    deviceType={deviceType}
                  />
                </div>

                {/* Live output controls */}
                <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Switch
                      id="live-output-toggle"
                      checked={liveOutputEnabled}
                      onCheckedChange={setLiveOutputEnabled}
                      aria-label={t("liveOutputAriaLabel")}
                    />
                    <label
                      htmlFor="live-output-toggle"
                      className="flex items-center gap-1.5 text-xs sm:text-sm font-medium cursor-pointer select-none"
                    >
                      <Radio className={`h-3.5 w-3.5 ${liveOutputEnabled ? "text-destructive animate-pulse" : "text-muted-foreground"}`} />
                      {t("liveOutput")}
                    </label>
                    {liveSendMutation.isPending && (
                      <span className="text-[10px] text-muted-foreground">{tCommon("sending")}</span>
                    )}
                  </div>

                  {boardSettings?.boards && boardSettings.boards.length > 1 && (
                    <Select
                      value={selectedBoardId}
                      onValueChange={setSelectedBoardId}
                    >
                      <SelectTrigger className="h-7 w-[140px] text-xs" aria-label={t("selectBoardAriaLabel")}>
                        <SelectValue placeholder={t("selectBoardPlaceholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {boardSettings.boards.map((board: BoardInstance) => (
                          <SelectItem key={board.id} value={board.id} className="text-xs">
                            {board.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              </div>

            </div>
            </ScrollArea>
          </CardContent>
        </Card>

      </div>
    </>
  );
}

