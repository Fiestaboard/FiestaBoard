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
  AlertDialogTrigger,
  type BoardPreviewMode,
  BoardPreviewModeToggle,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CopyButton,
  DEFAULT_EDITOR_PREVIEW_LABELS,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  EditorPreview,
  EmptyState,
  Flex,
  readStoredBoardPreviewMode,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  Switch,
  Text,
  Textarea,
  TextLink,
  toast as kitToast,
  ToolbarDropdown,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  writeStoredBoardPreviewMode,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  Ellipsis,
  FileQuestion,
  Save,
  Send,
  Sparkles,
  Trash2,
  Upload,
  Variable,
  Zap,
} from "lucide-react";
import {
  forwardRef,
  lazy,
  type ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { CanvasesPanel, type CanvasesPanelHandle } from "@/components/canvas-editor/canvases-panel";
import { LineOverflowWarnings } from "@/components/complex-editing/line-overflow-warnings";
import { PreviewCutMarkers } from "@/components/complex-editing/preview-cut-markers";
import { useComplexEditing } from "@/components/complex-editing/use-complex-editing";
import { useCurrentBoard } from "@/components/current-board-context";
import { DevicePreview } from "@/components/device-preview";
import type { StrokeCell } from "@/components/drawable-board-preview";
import { DrawableBoardPreview } from "@/components/drawable-board-preview";
import { EditorShortcutList, useEditorShortcutList } from "@/components/editor-shortcut-list";
import { EditorAnchoredTool } from "@/components/editor-tablet-tools";
import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { useBoardDetail } from "@/components/home/use-home-data";
import { LiveOutputSilenceStrip } from "@/components/live-output-silence-strip";
import { PanelFitNote } from "@/components/panel-fit-note";
import { PlainTemplateToolbar, PlainTemplateVariablePicker } from "@/components/plain-template-toolbar";
import { PlainTextEditor, type PlainTextEditorHandle } from "@/components/plain-text-editor";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import type {
  DrawHistoryEvent,
  TipTapTemplateEditorHandle,
} from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import type { CellPaint, DrawBrush } from "@/components/tiptap-template-editor/utils/draw-mode";
import {
  brushToCell,
  isPositionalLine,
  paintLine,
  renderPositionalLine,
} from "@/components/tiptap-template-editor/utils/draw-mode";
import {
  getEffectiveBoardColor,
  getEffectiveCode62Glyph,
  queryKeys,
  resolveCode62Glyph,
  useBoardSettings,
  useStatus,
} from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useEditorScrollMargin } from "@/hooks/use-editor-scroll-margin";
import { useEditorViewportDock } from "@/hooks/use-editor-viewport-dock";
import { useLineOverflow } from "@/hooks/use-line-overflow";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useDisplayTargets } from "@/hooks/use-panel-targets";
import { usePluginSettings } from "@/hooks/use-plugin-settings";
import { useSilence } from "@/hooks/use-silence";
import { useTransitionPlugins } from "@/hooks/use-transition-plugins";
import { useTranslations } from "@/i18n/translations";
import type { CurrentPageSnapshot, EditorToolCall } from "@/lib/ai-chat-types";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type {
  BoardInstance,
  Canvas,
  CanvasIssue,
  CanvasLayerJson,
  CharsetIssue,
  DeviceType,
  GridSize,
  LineAlignment,
  LineMetadata,
  Page,
  PageCreate,
  PageType,
  PageUpdate,
  PageUpdateResponse,
  TemplateRenderResponse,
} from "@/lib/api";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/core";
import type { RenderDiagnostics } from "@/lib/api/formula-debug";
import { appUrl } from "@/lib/base-path";
import { MAX_NOTES_PER_AXIS, resolveDimensions } from "@/lib/board-dimensions";
import { canvasMarkers, pixelBoardOf } from "@/lib/canvas-editing";
import { charsetTokenText, drawnDifferently } from "@/lib/charset-issues";
import { seamStraddles, usedLineCount } from "@/lib/complex-editing";
import { focusTemplateCell } from "@/lib/complex-editing-dom";
import { boardForShape, isLedModel, ledEditorCharacterSet, resolveBoardModel } from "@/lib/device-preview";
import {
  EDITOR_SHORTCUTS,
  isTypingTarget,
  matchesShortcut,
  previewBindsBoardViewportKeys,
} from "@/lib/editor-shortcuts";
import { templateHasFormula } from "@/lib/formula-ide/hints";
import { applyLineOpInPlace } from "@/lib/line-ops";
import { onLiveOutputMessageChange, writeLiveOutputMessage } from "@/lib/live-output-channel";
import { getDraftKey } from "@/lib/page-draft";
import { panelsFittingGrid, targetValue } from "@/lib/panel-page-fit";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";
import { isDisplayOffline } from "@/lib/status-banners";
import { cn } from "@/lib/utils";

import { FormulaIdeContext } from "./formula-ide/formula-ide-context";
import { useFormulaIde } from "./formula-ide/use-formula-ide";

// Lazy-loaded — TipTap + ProseMirror + CodeMirror + the lucide-react icon
// barrel push this module past 500 kB minified on their own (see #1575).
// It's route-split from the surrounding page-builder chunk so "plain" text
// editor mode (below) never pays for it, and "rich" mode streams it in
// behind a Suspense fallback instead of blocking the whole page-builder
// chunk's parse/eval. TipTap's useEditor({ immediatelyRender: false })
// handles SSR safely, so deferring the import is safe under RR7 SPA mode.
const TipTapTemplateEditor = lazy(() =>
  import("@/components/tiptap-template-editor/TipTapTemplateEditor").then((m) => ({
    default: m.TipTapTemplateEditor,
  })),
);

// The rich editor for a board whose character set draws more than flaps (an
// LED matrix): colour/block spans, icons, mixed case. Split out the same way,
// and only ever loaded when such a board is the target.
const CharsetTemplateEditor = lazy(() =>
  import("@/components/charset-template-editor").then((m) => ({ default: m.CharsetTemplateEditor })),
);

// Web 2.9 (04b) lenses load only for big boards and note arrays on the
// desktop pane, keeping their kit composites off every other editor load.
const previewTools = () => import("@/components/complex-editing/complex-preview-tools");
const templateTools = () => import("@/components/complex-editing/complex-template-tools");
const BigBoardZoom = lazy(() => previewTools().then((m) => ({ default: m.BigBoardZoom })));
const ComplexPreviewRuler = lazy(() => previewTools().then((m) => ({ default: m.ComplexPreviewRuler })));
const ComplexPreviewSeams = lazy(() => previewTools().then((m) => ({ default: m.ComplexPreviewSeams })));
const ComplexPreviewOverview = lazy(() => previewTools().then((m) => ({ default: m.ComplexPreviewOverview })));
const ComplexTemplateHeader = lazy(() => templateTools().then((m) => ({ default: m.ComplexTemplateHeader })));
const NoteSeamSummary = lazy(() => templateTools().then((m) => ({ default: m.NoteSeamSummary })));
const RowBandGutter = lazy(() => templateTools().then((m) => ({ default: m.RowBandGutter })));

interface PageBuilderProps {
  pageId?: string; // If provided, edit existing page
  deviceType?: DeviceType; // Device type for new pages
  /** Explicit display chosen in the Pages filter; takes precedence over the sidebar for new pages. */
  targetBoardId?: string;
  skipDraft?: boolean; // If true, ignore and clear any saved draft
  onClose: () => void;
  onSave?: () => void;
  /**
   * A new page's first save created it: the route shows its edit URL
   * (BB-B-9). Called once.
   */
  onCreated?: (pageId: string) => void;
  /**
   * Rendered inside the Pages section (section-shell.tsx): the section's
   * breadcrumb is the way back, so the back arrow goes, and the editor sits
   * in the section's card as a block instead of a second card inside it.
   */
  embedded?: boolean;
  /**
   * Creator IDE seam (web 2.11): replaces the header's Save and Show now while
   * a display shows the page (04d decision 4: Save draft / Save & update
   * board). `save` runs the header Save exactly as its button does.
   */
  saveActions?: (actions: PageBuilderSaveActions) => ReactNode;
}

export interface PageBuilderSaveActions {
  save: () => void;
  saving: boolean;
  disabled: boolean;
  size: "touch" | "sm";
  /** The header Save's AI-walkthrough anchor; spread it on the button that publishes. */
  anchor: Record<string, string>;
}

/**
 * Imperative API exposed to the editor host so the AI chat panel can
 * read the page being edited and apply mutations the model returns.
 */
export interface PageBuilderHandle {
  getCurrentPage: () => CurrentPageSnapshot | undefined;
  getPageId: () => string | undefined;
  getDeviceType: () => DeviceType;
  applyToolCall: (call: EditorToolCall) => void;
  /** Persist the current editor content to the API without closing. */
  save: () => Promise<{ id: string } | null>;
  undo: () => void;
  canUndo: () => boolean;
  hasUnsavedChanges: () => boolean;
  /** Reveal the text surface without modifying the draft or beginning staging. */
  revealText: () => void;
  /**
   * The AI walkthrough types a page in for real while the server writes
   * it. Staging takes one snapshot, suspends the draft autosave and locks
   * Save; `discardStaging` restores the snapshot, `reloadFromServer`
   * re-seeds from the saved page. Neither leaves a "Draft restored" behind.
   */
  beginStaging: () => void;
  stageName: (value: string) => void;
  stageLine: (index: number, value: string) => void;
  stageDeviceType: (value: string) => void;
  discardStaging: () => void;
  reloadFromServer: () => Promise<void>;
  /** Mirror to board is on: a display shows these edits (the IDE's Testing state). */
  isMirroring: () => boolean;
}

interface PageSnapshot {
  name: string;
  deviceType: DeviceType;
  templateLines: string[];
  lineAlignments: LineAlignment[];
  lineWrapEnabled: boolean[];
}

/**
 * Pre-stroke alignment/wrap for the rows a paint stroke touched. Committing
 * a stroke forces those rows to left/no-wrap; since that metadata lives in
 * React state (outside ProseMirror history), undoing the stroke needs this
 * capture to restore it — see handleDrawHistoryEvent.
 */
interface StrokeMetaSnapshot {
  rows: number[];
  alignments: LineAlignment[];
  wraps: boolean[];
}

const UNDO_STACK_LIMIT = 5;

/** Charset issues listed one by one; the rest are counted. */
const MAX_CHARSET_ISSUES_SHOWN = 5;

// 1..MAX_NOTES_PER_AXIS choices for the note-array W×H selectors.
const NOTE_AXIS_OPTIONS = Array.from({ length: MAX_NOTES_PER_AXIS }, (_, i) => i + 1);

const EDITOR_MODE_KEY = "fiestaboard_editor_mode";

function getStoredEditorMode(): "rich" | "plain" {
  if (typeof window === "undefined") return "rich";
  try {
    const stored = localStorage.getItem(EDITOR_MODE_KEY);
    if (stored === "rich" || stored === "plain") return stored;
  } catch {}
  return "rich";
}

/**
 * Sentinel used as the radio-group value for "no per-page override". The menu
 * needs a non-empty string; the saved value is `null`.
 */
const TRANSITION_INHERIT = "__inherit__";

/**
 * Built-in transition strategies, paired with their key under the shared
 * `transitionSettings.strategies.*` namespace so the per-page picker and the
 * global settings card always read the same labels.
 */
const BUILT_IN_TRANSITIONS: { value: string; labelKey: string }[] = [
  { value: "column", labelKey: "column" },
  { value: "reverse-column", labelKey: "reverseColumn" },
  { value: "edges-to-center", labelKey: "edgesToCenter" },
  { value: "row", labelKey: "row" },
  { value: "diagonal", labelKey: "diagonal" },
  { value: "random", labelKey: "random" },
];

const PLUGIN_STRATEGY_PREFIX = "plugin:";

/**
 * The geometry fields a page save carries beyond device_type: notes for a
 * note array, the character grid for a panel (required — the API refuses a
 * panel page without it), nothing for a flagship or Note.
 */
function geometryFields(
  deviceType: DeviceType,
  notesWide: number,
  notesTall: number,
  panelGrid: GridSize | null,
): Pick<PageCreate, "notes_wide" | "notes_tall" | "grid_rows" | "grid_cols"> {
  if (deviceType === "note_array") return { notes_wide: notesWide, notes_tall: notesTall };
  if (deviceType === "panel" && panelGrid) return { grid_rows: panelGrid.rows, grid_cols: panelGrid.cols };
  return {};
}

interface DraftData {
  name: string;
  templateLines: string[];
  lineAlignments: LineAlignment[];
  lineWrapEnabled?: boolean[]; // Optional for backward compatibility
  canvases?: Canvas[];
  timestamp: number;
}

export const PageBuilder = forwardRef<PageBuilderHandle, PageBuilderProps>(function PageBuilder(
  {
    pageId: initialPageId,
    deviceType: deviceTypeProp,
    targetBoardId: targetBoardIdProp,
    skipDraft = false,
    onClose,
    onSave,
    onCreated,
    embedded = false,
    saveActions,
  },
  ref,
) {
  const [createdPageId, setCreatedPageId] = useState<string>();
  const pageId = initialPageId ?? createdPageId;
  const [toolbarContainer, setToolbarContainer] = useState<Element | null>(null);
  const tTouch = useTranslations("editorTouch");
  const tToolbar = useTranslations("templateEditor");
  const tBoardDisplay = useTranslations("boardDisplay");
  const tShortcuts = useTranslations("editorShortcuts");
  const dockedPreview = useMediaQuery("(max-width: 1023px)");
  const sheetPickers = useMediaQuery("(max-width: 639px)");
  const useTouchToolbar = useMediaQuery("(max-width: 767px), (pointer: coarse)");
  // Under 390px Save is its icon, so the page name keeps two readable lines (BB-B-3).
  const narrowHeader = useMediaQuery("(max-width: 389px)");
  const editorContentRef = useRef<HTMLDivElement>(null);
  const dockPreviewRef = useRef<HTMLElement>(null);
  const viewportBottom = useEditorViewportDock(dockedPreview && useTouchToolbar, editorContentRef, dockPreviewRef);
  const [previewMode, setPreviewMode] = useState<BoardPreviewMode>(() => readStoredBoardPreviewMode() ?? "actual");
  const changePreviewMode = (mode: BoardPreviewMode) => {
    setPreviewMode(mode);
    writeStoredBoardPreviewMode(mode);
  };
  const [showPageId, setShowPageId] = useState<string | null>(null);
  // Report a created page once, so its route can show its own URL (BB-B-9).
  const reportedCreatedRef = useRef(false);
  useEffect(() => {
    if (!createdPageId || initialPageId || reportedCreatedRef.current) return;
    reportedCreatedRef.current = true;
    onCreated?.(createdPageId);
  }, [createdPageId, initialPageId, onCreated]);
  const showAfterSaveRef = useRef(false);
  const requestShowNowRef = useRef<(savedId?: string) => void>(() => {});
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const t = useTranslations("pageBuilder");
  const tCommon = useTranslations("common");
  const tNav = useTranslations("navigation");
  const tCanvas = useTranslations("canvasEditor");
  const tDisplaySettings = useTranslations("displaySettings");
  const tPanels = useTranslations("fiestaPanels");
  // Shared with the global transition settings card so both surfaces label the
  // built-in strategies identically.
  const tTransitions = useTranslations("transitionSettings");
  const queryClient = useQueryClient();

  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();
  const { data: status } = useStatus();
  const { currentBoardId, currentBoard, setCurrentBoardId } = useCurrentBoard();

  // Device type: from prop (new pages), the requested or sidebar board (a new
  // page that asked for no device — see below), or the existing page (editing)
  const [deviceType, setDeviceType] = useState<DeviceType>(deviceTypeProp ?? "flagship");
  // Note-array grid dimensions. Only meaningful when deviceType === "note_array";
  // flagship/note always stay 1×1 so they resolve to their fixed device sizes.
  // Sourced from the existing page (editing), the configured note_array board
  // (new page), or an AI sync — see the effects below.
  const [notesWide, setNotesWide] = useState(1);
  const [notesTall, setNotesTall] = useState(1);
  // Character grid of a "panel" page (a FiestaPanel, fit per character — any
  // rows × cols, not a multiple of a Note). Only meaningful when
  // deviceType === "panel"; sourced from the existing page, the chosen panel,
  // or the configured panel board (new page).
  const [gridRows, setGridRows] = useState<number | null>(null);
  const [gridCols, setGridCols] = useState<number | null>(null);
  // Set when the user picks a FiestaPanel by name in the size picker: the
  // panel's grid is the explicit choice, so the board-seeding effect below
  // must not overwrite it with the selected board's shape. Cleared again when
  // a generic device is chosen, so the seed is back in charge.
  const [panelSizedGrid, setPanelSizedGrid] = useState(false);
  // Every display a page can be sized to by name: FiestaPanels, then any other
  // board with a custom grid (an output plugin's LED matrix, ...).
  const panelTargets = useDisplayTargets();
  const fiestaPanelTargets = useMemo(() => panelTargets.filter((p) => p.kind !== "display"), [panelTargets]);
  const otherDisplayTargets = useMemo(() => panelTargets.filter((p) => p.kind === "display"), [panelTargets]);
  // The board the page is being authored for, when that is known: the display
  // picked by name in the size picker, or — for a new page — the display
  // requested by the Pages filter or selected in the sidebar. Not stored on the page (the grid is the whole
  // relationship); it only decides which of several same-shaped boards the
  // editor previews and checks against, and which name the picker shows.
  const [targetBoardId, setTargetBoardId] = useState<string | null>(null);

  // A NEW page that asked for no particular device (`/pages/new`) starts on
  // the explicitly requested display, else the sidebar's selection — with one display,
  // that display: its device type and its exact geometry (an LED matrix's
  // custom grid included), so it previews and checks as that board from the
  // first keystroke. Taken once; the user can still retarget, and an
  // existing page keeps its own shape. Adjusted during render rather than in
  // an effect so the editor never paints a flagship first (issue #1568).
  const [adoptedCurrentBoard, setAdoptedCurrentBoard] = useState(false);
  const initialTargetBoard = targetBoardIdProp
    ? (boardSettings?.boards?.find((board) => board.id === targetBoardIdProp) ??
      (boardSettings ? currentBoard : undefined))
    : currentBoard;
  const adoptingBoard = !pageId && !deviceTypeProp && !adoptedCurrentBoard ? initialTargetBoard : undefined;
  if (adoptingBoard) {
    setAdoptedCurrentBoard(true);
    setDeviceType(adoptingBoard.device_type);
    if (adoptingBoard.device_type === "note_array") {
      setNotesWide(adoptingBoard.notes_wide ?? 1);
      setNotesTall(adoptingBoard.notes_tall ?? 1);
    } else if (adoptingBoard.device_type === "panel" && adoptingBoard.grid_rows && adoptingBoard.grid_cols) {
      setGridRows(adoptingBoard.grid_rows);
      setGridCols(adoptingBoard.grid_cols);
    }
    setTargetBoardId(adoptingBoard.id);
    // The board's own shape is the choice: the generic seeding below must not
    // replace it with another board's.
    setPanelSizedGrid(true);
  }
  const dims = resolveDimensions(deviceType, notesWide, notesTall, gridRows, gridCols);
  const numLines = dims.rows;
  // The grid a panel render/save needs (the API refuses a panel without one).
  const panelGrid = useMemo<GridSize | null>(
    () => (deviceType === "panel" && gridRows && gridCols ? { rows: gridRows, cols: gridCols } : null),
    [deviceType, gridRows, gridCols],
  );
  // Latest numLines for effects that need it without becoming reactive to it
  // (the load-draft effect below intentionally excludes notesWide/notesTall
  // changes so resizing a note-array grid doesn't reset in-progress edits).
  const numLinesRef = useRef(numLines);
  numLinesRef.current = numLines;

  // Preview board color - defaults to the user's configured board color
  const defaultBoardColor = getEffectiveBoardColor(boardSettings);
  const [previewBoardColor, setPreviewBoardColor] = useState<"black" | "white" | null>(null);
  const effectiveBoardColor = previewBoardColor ?? defaultBoardColor;

  // Which glyph code 62 draws in this preview (issue #1657). A page belongs to
  // a device shape rather than to one board, so this reads the same first board
  // `defaultBoardColor` does; a Note-shaped page always draws the heart.
  const effectiveCode62Glyph = resolveCode62Glyph(deviceType, getEffectiveCode62Glyph(boardSettings));

  // Helper to create arrays of the correct length
  const emptyLines = () => Array.from({ length: numLines }, () => "");
  const defaultAlignments = () => Array.from({ length: numLines }, () => "left" as LineAlignment);
  const defaultWraps = () => Array.from({ length: numLines }, () => false);

  // Form state (immediate - for UI responsiveness)
  const [name, setName] = useState("");
  const [templateLines, setTemplateLines] = useState<string[]>(emptyLines());
  const [templateInputStarted, setTemplateInputStarted] = useState(false);
  const [lineAlignments, setLineAlignments] = useState<LineAlignment[]>(defaultAlignments());
  const [lineWrapEnabled, setLineWrapEnabled] = useState<boolean[]>(defaultWraps());
  const [preview, setPreview] = useState<string | null>(null);
  const [lastPreview, setLastPreview] = useState<string | null>(null); // Track last preview for smooth transitions
  const [isTransitioning, setIsTransitioning] = useState(false); // Track if we're transitioning between previews
  const [_pendingPreview, setPendingPreview] = useState<string | null>(null); // Preview waiting to be shown after transition
  const [draftRestored, setDraftRestored] = useState(false);
  const [hasRestoredDraft, setHasRestoredDraft] = useState(false);
  // Settings can arrive after the initial six-row form has mounted. Seed its
  // untouched blank document together with the adopted geometry; user content
  // and restored drafts retain their own rows, including overflow.
  if (
    adoptingBoard &&
    !hasRestoredDraft &&
    !templateInputStarted &&
    templateLines.every((line) => line === "") &&
    lineAlignments.every((alignment) => alignment === "left") &&
    lineWrapEnabled.every((wrap) => !wrap)
  ) {
    const rows = resolveDimensions(
      adoptingBoard.device_type,
      adoptingBoard.notes_wide ?? 1,
      adoptingBoard.notes_tall ?? 1,
      adoptingBoard.grid_rows,
      adoptingBoard.grid_cols,
    ).rows;
    setTemplateLines(Array.from({ length: rows }, () => ""));
    setLineAlignments(Array.from({ length: rows }, () => "left"));
    setLineWrapEnabled(Array.from({ length: rows }, () => false));
  }
  const [editorMode, setEditorMode] = useState<"rich" | "plain">(getStoredEditorMode);
  const [editingSurface, setEditingSurface] = useState<"text" | "canvases">("text");

  // Per-page transition override. `null` means "inherit the display's transition"
  // — the backend clears a stored override only when it is sent an explicit
  // null, so this always goes out on the wire (see the save mutation).
  const [transitionStrategy, setTransitionStrategy] = useState<string | null>(null);

  // Pixel canvases (design PIXEL_CANVAS.md §5): stored beside the template,
  // edited only for an LED pixel board, previewed by the server's render
  // (`layers` + `canvas_issues` for the preview board, or its refusal).
  const [canvases, setCanvases] = useState<Canvas[]>([]);
  const canvasesPanelRef = useRef<CanvasesPanelHandle>(null);
  const [debouncedCanvases, setDebouncedCanvases] = useState<Canvas[]>([]);
  const [previewLayers, setPreviewLayers] = useState<CanvasLayerJson[] | null>(null);
  const [canvasIssues, setCanvasIssues] = useState<CanvasIssue[]>([]);
  const [canvasError, setCanvasError] = useState<string | null>(null);

  // Pencil draw-mode state — see handleStrokeCommit / drawPreviewMessage
  // below for how a painted stroke flows back into templateLines.
  const [drawMode, setDrawMode] = useState(false);
  const [drawBrush, setDrawBrush] = useState<DrawBrush>({ kind: "color", color: "red" });

  const [strokePreviewCells, setStrokePreviewCells] = useState<StrokeCell[]>([]);

  /**
   * The size picker offers two kinds of choice: a generic device type, and a
   * display by name — a FiestaPanel (``panel:<id>``) or any other board with a
   * custom grid, such as an output plugin's LED matrix (``display:<board id>``).
   * Either resolves to a ``panel`` page plus that display's character grid
   * (``grid_rows`` × ``grid_cols``) — nothing is stored on the page to say
   * which display it was made for. The grid is the whole relationship. (A
   * legacy panel whose board is still a Note-block array resolves to a
   * note_array page of its grid, as before.)
   */
  const handleSizeChange = useCallback(
    (value: string) => {
      const panel = panelTargets.find((p) => targetValue(p) === value);
      if (panel) {
        setTargetBoardId(panel.boardId ?? null);
        if (panel.deviceType === "panel") {
          setDeviceType("panel");
          setGridRows(panel.rows);
          setGridCols(panel.cols);
        } else {
          setDeviceType("note_array");
          setNotesWide(panel.notesWide);
          setNotesTall(panel.notesTall);
        }
        setPanelSizedGrid(true);
      } else {
        setDeviceType(value as DeviceType);
        setTargetBoardId(null);
        setPanelSizedGrid(false);
      }
      setDrawMode(false);
    },
    [panelTargets],
  );

  /**
   * What the size picker's trigger shows, and which row is highlighted when it
   * reopens. Derived from the geometry rather than held as its own state: a
   * panel choice resolves to a device type + a grid, so a picker controlled by
   * ``deviceType`` alone would forget which panel had been chosen. Naming the
   * panel whose board this grid matches is also simply truer — that IS the
   * page's shape. A panel page no panel matches any more (its TV was resized
   * or the panel deleted) shows as the bare "panel" option at its own grid.
   * Of several displays with the same grid, the one the page is being
   * authored for wins, then the board selected in the sidebar.
   */
  const sizeSelectValue = useMemo(() => {
    const fits = panelsFittingGrid(panelTargets, deviceType, notesWide, notesTall, gridRows, gridCols);
    const fit =
      (targetBoardId ? fits.find((p) => p.boardId === targetBoardId) : undefined) ??
      fits.find((p) => !!p.boardId && p.boardId === currentBoardId) ??
      fits[0];
    return fit ? targetValue(fit) : deviceType;
  }, [panelTargets, deviceType, notesWide, notesTall, gridRows, gridCols, targetBoardId, currentBoardId]);
  const tipTapRef = useRef<TipTapTemplateEditorHandle>(null);
  const plainTextRef = useRef<PlainTextEditorHandle>(null);
  const [plainHistory, setPlainHistory] = useState({ canUndo: false, canRedo: false });
  const richTemplateContainerRef = useRef<HTMLDivElement>(null);
  const plainTemplateContainerRef = useRef<HTMLDivElement>(null);
  // Metadata history keyed to stroke boundaries: done/undone mirror the
  // editor's stroke undo/redo stacks (reported via onDrawHistoryEvent).
  const strokeMetaHistoryRef = useRef<{ done: StrokeMetaSnapshot[]; undone: StrokeMetaSnapshot[] }>({
    done: [],
    undone: [],
  });

  // Snapshot of the page state as loaded from the server, used to detect unsaved changes.
  const [savedSnapshot, setSavedSnapshot] = useState<{
    name: string;
    deviceType: DeviceType;
    geometry: string;
    templateLines: string[];
    lineAlignments: LineAlignment[];
    lineWrapEnabled: boolean[];
    transitionStrategy: string | null;
    canvases: Canvas[];
  } | null>(null);

  // Export dialog
  const [exportOpen, setExportOpen] = useState(false);
  const [exportShareString, setExportShareString] = useState("");

  // Shrinking-retarget confirmation (issue #1250). Converting a saved page
  // to a smaller geometry is lossy, so the save is gated behind a confirm.
  const [confirmRetargetOpen, setConfirmRetargetOpen] = useState(false);

  // Snapshot stack so the AI chat panel can offer a one-click Undo
  // after the model applies a change. Bounded to keep the editor
  // memory footprint small even on long sessions.
  const undoStackRef = useRef<PageSnapshot[]>([]);
  const [undoVersion, setUndoVersion] = useState(0);

  // When the AI applies a tool call we bypass the human-typing debounce
  // on the preview render so the board updates immediately. The
  // preview effect checks this ref and resets it after one run.
  const skipNextPreviewDebounceRef = useRef(false);

  // Refs that mirror the editor form state so imperative handlers
  // (called from the AI chat panel) can read it synchronously without
  // closure staleness across React renders.
  const nameRef = useRef(name);
  // Bind edits to the generation that seeded this draft. A background query
  // refetch must not silently authorize overwriting another editor's save.
  const seededRevisionRef = useRef<string | null | undefined>(undefined);
  const seededProtocolsRef = useRef<Pick<Page, "edit_protocol" | "document_protocol">>({});
  const templateLinesRef = useRef(templateLines);
  const lineAlignmentsRef = useRef(lineAlignments);
  const lineWrapEnabledRef = useRef(lineWrapEnabled);
  const deviceTypeRef = useRef(deviceType);
  const notesWideRef = useRef(notesWide);
  const notesTallRef = useRef(notesTall);
  const panelGridRef = useRef(panelGrid);
  const durationRef = useRef(300);
  const draftDisplayRef = useRef({ canvases, transitionStrategy, targetBoardId });
  useEffect(() => {
    draftDisplayRef.current = { canvases, transitionStrategy, targetBoardId };
  }, [canvases, transitionStrategy, targetBoardId]);
  useEffect(() => {
    nameRef.current = name;
  }, [name]);
  useEffect(() => {
    templateLinesRef.current = templateLines;
  }, [templateLines]);
  useEffect(() => {
    lineAlignmentsRef.current = lineAlignments;
  }, [lineAlignments]);
  useEffect(() => {
    lineWrapEnabledRef.current = lineWrapEnabled;
  }, [lineWrapEnabled]);
  useEffect(() => {
    deviceTypeRef.current = deviceType;
  }, [deviceType]);
  useEffect(() => {
    notesWideRef.current = notesWide;
  }, [notesWide]);
  useEffect(() => {
    notesTallRef.current = notesTall;
  }, [notesTall]);
  useEffect(() => {
    panelGridRef.current = panelGrid;
  }, [panelGrid]);

  const hasUnsavedChanges = useMemo(() => {
    if (!savedSnapshot)
      return (
        !pageId &&
        (name.trim().length > 0 || templateLines.some((line) => line.trim().length > 0) || canvases.length > 0)
      );
    return (
      name !== savedSnapshot.name ||
      deviceType !== savedSnapshot.deviceType ||
      JSON.stringify(geometryFields(deviceType, notesWide, notesTall, panelGrid)) !== savedSnapshot.geometry ||
      JSON.stringify(templateLines) !== JSON.stringify(savedSnapshot.templateLines) ||
      JSON.stringify(lineAlignments) !== JSON.stringify(savedSnapshot.lineAlignments) ||
      JSON.stringify(lineWrapEnabled) !== JSON.stringify(savedSnapshot.lineWrapEnabled) ||
      transitionStrategy !== savedSnapshot.transitionStrategy ||
      JSON.stringify(canvases) !== JSON.stringify(savedSnapshot.canvases)
    );
  }, [
    savedSnapshot,
    pageId,
    name,
    deviceType,
    notesWide,
    notesTall,
    panelGrid,
    templateLines,
    lineAlignments,
    lineWrapEnabled,
    transitionStrategy,
    canvases,
  ]);

  const pushUndoSnapshot = useCallback(() => {
    const snap: PageSnapshot = {
      name: nameRef.current,
      deviceType: deviceTypeRef.current,
      templateLines: templateLinesRef.current.slice(),
      lineAlignments: lineAlignmentsRef.current.slice(),
      lineWrapEnabled: lineWrapEnabledRef.current.slice(),
    };
    undoStackRef.current = [snap, ...undoStackRef.current].slice(0, UNDO_STACK_LIMIT);
    setUndoVersion((v) => v + 1);
  }, []);

  const applySnapshot = useCallback((snap: PageSnapshot) => {
    if (snap.deviceType !== deviceTypeRef.current) {
      setDeviceType(snap.deviceType);
    }
    setName(snap.name);
    setTemplateLines(snap.templateLines);
    setLineAlignments(snap.lineAlignments);
    setLineWrapEnabled(snap.lineWrapEnabled);
    setDebouncedTemplateLines(snap.templateLines);
    setDebouncedLineAlignments(snap.lineAlignments);
    setDebouncedLineWrapEnabled(snap.lineWrapEnabled);
  }, []);

  /**
   * Apply one editor-local edit to the draft. The AI chat no longer drives
   * this directly (its tools write through the server); it stays as the
   * editor bridge's apply path until the staged-typing work replaces it.
   */
  const applyToolCall = useCallback(
    (call: EditorToolCall) => {
      // Only the two editor-local ops are applied here; anything else must
      // never fall through to the apply_patch branch below, which would
      // read `.changes` off the wrong args shape.
      if (call.op !== "replace_page" && call.op !== "apply_patch") {
        return;
      }
      pushUndoSnapshot();
      // Skip the 200ms preview debounce for the next render — the user
      // expects an AI mutation to show on the board immediately, not
      // after a typing-debounce window.
      skipNextPreviewDebounceRef.current = true;
      if (call.op === "replace_page") {
        const { name: newName, template, line_metadata } = call.args;
        setName(newName);
        const lines = template;
        const alignments = lines.map((_, i) => (line_metadata[i]?.alignment as LineAlignment) ?? "left");
        const wraps = lines.map((_, i) => Boolean(line_metadata[i]?.wrap));
        setTemplateLines(lines);
        setLineAlignments(alignments);
        setLineWrapEnabled(wraps);
        setDebouncedTemplateLines(lines);
        setDebouncedLineAlignments(alignments);
        setDebouncedLineWrapEnabled(wraps);
        toast.success("AI replaced the page");
        return;
      }
      // apply_patch
      const lines = templateLinesRef.current.slice();
      const alignments = lineAlignmentsRef.current.slice();
      const wraps = lineWrapEnabledRef.current.slice();
      for (const change of call.args.changes) {
        applyLineOpInPlace(change, lines, alignments, wraps);
      }
      setTemplateLines(lines);
      setLineAlignments(alignments);
      setLineWrapEnabled(wraps);
      setDebouncedTemplateLines(lines);
      setDebouncedLineAlignments(alignments);
      setDebouncedLineWrapEnabled(wraps);
      if (call.args.rename) {
        setName(call.args.rename);
      }
      toast.success(`AI applied ${call.args.changes.length} change${call.args.changes.length === 1 ? "" : "s"}`);
    },
    [pushUndoSnapshot],
  );

  const handleUndoAi = useCallback(() => {
    const [head, ...rest] = undoStackRef.current;
    if (!head) return;
    undoStackRef.current = rest;
    applySnapshot(head);
    setUndoVersion((v) => v + 1);
    toast.info("Undid last AI change");
  }, [applySnapshot]);

  const getCurrentPageSnapshot = useCallback((): CurrentPageSnapshot | undefined => {
    const lines = templateLinesRef.current;
    const draft = draftDisplayRef.current;
    if (!nameRef.current && !lines.some((l) => l) && !draft.canvases.length) return undefined;
    return {
      // The id tells the assistant whether update_page can target this
      // page; an unsaved draft has none and is created instead.
      ...(pageId ? { id: pageId, revision: seededRevisionRef.current, ...seededProtocolsRef.current } : {}),
      name: nameRef.current,
      device_type: deviceTypeRef.current,
      ...geometryFields(deviceTypeRef.current, notesWideRef.current, notesTallRef.current, panelGridRef.current),
      ...(draft.targetBoardId ? { board_id: draft.targetBoardId } : {}),
      canvases: structuredClone(draft.canvases),
      duration_seconds: durationRef.current,
      transition_strategy: draft.transitionStrategy,
      template: [...lines],
      line_metadata: lines.map((_, i) => ({
        alignment: (lineAlignmentsRef.current[i] ?? "left") as LineMetadata["alignment"],
        wrap: lineWrapEnabledRef.current[i] ?? false,
      })),
    };
  }, [pageId]);

  const takeSnapshot = useCallback(
    (): PageSnapshot => ({
      name: nameRef.current,
      deviceType: deviceTypeRef.current,
      templateLines: [...templateLinesRef.current],
      lineAlignments: [...lineAlignmentsRef.current],
      lineWrapEnabled: [...lineWrapEnabledRef.current],
    }),
    [],
  );

  const revealText = useCallback(() => setEditingSurface("text"), []);

  const beginStaging = useCallback(() => {
    if (stagingSnapshotRef.current) return;
    stagingSnapshotRef.current = takeSnapshot();
    stagingDirtyRef.current = hasUnsavedChangesRef.current;
    setStagingActive(true);
  }, [takeSnapshot]);

  const stageName = useCallback((value: string) => {
    setName(value);
  }, []);

  const stageLine = useCallback((index: number, value: string) => {
    skipNextPreviewDebounceRef.current = true;
    setTemplateLines((prev) => {
      const next = [...prev];
      while (next.length <= index) next.push("");
      next[index] = value;
      return next;
    });
  }, []);

  const stageDeviceType = useCallback((value: string) => {
    setDeviceType(value as DeviceType);
    setDrawMode(false);
  }, []);

  const discardStaging = useCallback(() => {
    const snap = stagingSnapshotRef.current;
    const wasDirty = stagingDirtyRef.current;
    stagingSnapshotRef.current = null;
    stagingDirtyRef.current = null;
    setStagingActive(false);
    if (snap) {
      applySnapshot(snap);
      // create_page settles by discarding staging and navigating in one tick.
      // Restore the pre-staging guard synchronously, before React commits the
      // restored fields, while preserving a user's original dirty draft.
      hasUnsavedChangesRef.current = wasDirty ?? hasUnsavedChangesRef.current;
    }
    try {
      localStorage.removeItem(getDraftKey(pageId));
    } catch {
      /* storage may be unavailable */
    }
  }, [applySnapshot, pageId]);

  const reloadFromServer = useCallback(async () => {
    // A dirty editor never entered staging: the walkthrough only showed a
    // notice. Its successful server update must not replace this local draft.
    if (!stagingSnapshotRef.current && hasUnsavedChangesRef.current) return;
    stagingSnapshotRef.current = null;
    stagingDirtyRef.current = null;
    setStagingActive(false);
    if (!pageId) return;
    forceReseedRef.current = true;
    await queryClient.invalidateQueries({ queryKey: ["page", pageId] });
  }, [pageId, queryClient]);

  // Read by the Creator IDE (Testing state); kept current where the state is declared.
  const ideMirroringRef = useRef(false);
  useImperativeHandle(
    ref,
    (): PageBuilderHandle => ({
      hasUnsavedChanges: () => hasUnsavedChangesRef.current,
      revealText,
      beginStaging,
      stageName,
      stageLine,
      stageDeviceType,
      discardStaging,
      reloadFromServer,
      getCurrentPage: getCurrentPageSnapshot,
      getPageId: () => pageId,
      getDeviceType: () => deviceTypeRef.current,
      applyToolCall,
      save: async () => {
        try {
          const { cleanedLines, metadata } = processLinesWithPrefixes(
            templateLinesRef.current,
            lineAlignmentsRef.current,
            lineWrapEnabledRef.current,
          );
          const noteArrayDims = geometryFields(
            deviceTypeRef.current,
            notesWideRef.current,
            notesTallRef.current,
            panelGridRef.current,
          );
          // The two endpoints no longer share a shape: PUT answers
          // { page, incompatible_references }, POST answers the bare page at
          // 201. Narrow to the saved page here so everything below reads one
          // thing.
          const saved: Page = pageId
            ? (
                await api.updatePage(pageId, {
                  expected_revision: seededRevisionRef.current,
                  name: nameRef.current,
                  device_type: deviceTypeRef.current,
                  template: cleanedLines,
                  line_metadata: metadata,
                  ...noteArrayDims,
                  canvases: draftDisplayRef.current.canvases.length ? draftDisplayRef.current.canvases : null,
                  transition_strategy: draftDisplayRef.current.transitionStrategy,
                })
              ).page
            : await api.createPage({
                name: nameRef.current,
                type: "template" as PageType,
                device_type: deviceTypeRef.current,
                template: cleanedLines,
                line_metadata: metadata,
                ...noteArrayDims,
                canvases: draftDisplayRef.current.canvases,
                transition_strategy: draftDisplayRef.current.transitionStrategy,
              });
          seededRevisionRef.current = saved.revision;
          seededProtocolsRef.current = {
            edit_protocol: saved.edit_protocol,
            document_protocol: saved.document_protocol,
          };
          // Invalidate the pages list and this page's preview, but don't close.
          queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });
          queryClient.invalidateQueries({
            queryKey: queryKeys.pagePreview(saved.id),
            refetchType: "active",
          });
          return { id: saved.id };
        } catch {
          return null;
        }
      },
      undo: handleUndoAi,
      canUndo: () => undoStackRef.current.length > 0,
      isMirroring: () => ideMirroringRef.current,
    }),
    // undoVersion is intentionally a dep so the host re-reads canUndo()
    // when the stack changes (the function returned by canUndo always
    // sees the latest ref, but consumers may render gates off it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      getCurrentPageSnapshot,
      applyToolCall,
      handleUndoAi,
      undoVersion,
      pageId,
      queryClient,
      revealText,
      beginStaging,
      stageName,
      stageLine,
      stageDeviceType,
      discardStaging,
      reloadFromServer,
    ],
  );

  const handleEditorModeChange = useCallback((mode: "rich" | "plain") => {
    setEditorMode(mode);
    setDrawMode(false);
    try {
      localStorage.setItem(EDITOR_MODE_KEY, mode);
    } catch {}
  }, []);

  // Derive line count from templateLines — single source of truth avoids
  // desync when switching between Rich and Plain Text editors. Blank rows
  // after the last line with content are a smaller board's padding (BB-E-18).
  const lineCount = usedLineCount(templateLines);

  // Live output mode state
  const [liveOutputEnabled, setLiveOutputEnabled] = useState(false);
  useEffect(() => {
    ideMirroringRef.current = liveOutputEnabled;
  }, [liveOutputEnabled]);
  const [chosenLiveBoardId, setChosenLiveBoardId] = useState<string>("");
  // The board this page is previewed as: the live-output target, else the
  // board in context, when the page fits it; else any board it fits. Its
  // model draws the preview (an LED board as an LED matrix) and its
  // character set is what the render is checked against.
  const previewBoard = useMemo(
    () =>
      boardForShape(boardSettings?.boards, [chosenLiveBoardId, targetBoardId, currentBoardId], {
        device_type: deviceType,
        notes_wide: notesWide,
        notes_tall: notesTall,
        grid_rows: panelGrid?.rows ?? null,
        grid_cols: panelGrid?.cols ?? null,
      }),
    [
      boardSettings?.boards,
      targetBoardId,
      chosenLiveBoardId,
      currentBoardId,
      deviceType,
      notesWide,
      notesTall,
      panelGrid,
    ],
  );
  const previewBoardId = previewBoard?.id ?? null;
  // Follow the compatible preview until the user chooses a live target or
  // starts sending. Deriving this during render also handles late settings
  // and sidebar context without first selecting the primary board.
  const selectedBoardId = chosenLiveBoardId || previewBoardId || "";
  const liveTargetPaused = boardSettings?.boards?.find((board) => board.id === selectedBoardId)?.paused === true;
  const { data: targetDetail } = useBoardDetail(selectedBoardId || undefined);
  const baselineDisplay = targetDetail?.drawing?.source === "baseline";
  // The initial board-sized blank rows are padding. Once the user enters
  // text, authored blank lines are document content and must survive editing.
  const initialBlankTemplate = !templateInputStarted && !hasRestoredDraft && templateLines.every((line) => line === "");
  const newPageEmpty = !pageId && canvases.length === 0 && (initialBlankTemplate || templateLines.join("\n") === "");
  const mirrorDisabled = !selectedBoardId || liveTargetPaused || targetDetail?.paused === true;
  const previewModel = useMemo(() => resolveBoardModel(previewBoard), [previewBoard]);
  // An LED target's character set: the rich editor then reads and offers that
  // set's extended markup and keeps its case. null for a split-flap target.
  const editorCharset = useMemo(() => ledEditorCharacterSet(previewBoard, previewModel), [previewBoard, previewModel]);
  // The preview board as a pixel matrix (its size and face), when it is one:
  // only then are the page's canvases drawn, and so edited.
  const pixelBoard = useMemo(
    () => (baselineDisplay ? null : pixelBoardOf(previewModel, previewBoard?.led_layout)),
    [previewModel, previewBoard?.led_layout, baselineDisplay],
  );
  // Cells of the last render that board's character set draws differently
  // (POST /templates/render with board_id); [] when none or no board.
  const [charsetIssues, setCharsetIssues] = useState<CharsetIssue[]>([]);
  // H5 values from the preview render (web 2.10 formula chips and line report).
  const [previewDiagnostics, setPreviewDiagnostics] = useState<RenderDiagnostics | null>(null);
  const lastLiveSentPreview = useRef<string | null>(null);
  // Ref-tracked copy of lastPreview so the liveOutputEnabled effect can read it
  // synchronously without a stale closure (avoids adding lastPreview as a dep).
  const lastPreviewRef = useRef<string | null>(null);
  const liveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const liveOutputEnabledRef = useRef(false);
  const liveAbortRef = useRef<AbortController | null>(null);
  const liveCanvasAttemptedRef = useRef(false);
  const liveDebounceRef = useRef<NodeJS.Timeout | null>(null);

  const LIVE_OUTPUT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

  // Silence (#1943): live renders leave a silenced board alone unless the
  // user explicitly chose "Send to board anyway" for this Live Output session.
  const liveSilence = useSilence(selectedBoardId || undefined);
  const mirrorUnavailable =
    mirrorDisabled ||
    liveSilence.active ||
    previewBoard?.enabled === false ||
    isDisplayOffline(status?.boards?.[selectedBoardId]?.health);
  const changeMirroring = (enabled: boolean) => {
    if (enabled && mirrorUnavailable) return;
    if (enabled) setChosenLiveBoardId(selectedBoardId);
    setLiveOutputEnabled(enabled);
  };
  const mirrorControl = (
    <Stack gap="2">
      <Flex align="center" justify="between" gap="3">
        <label htmlFor="editor-more-mirror">{tTouch("mirror") || DEFAULT_EDITOR_PREVIEW_LABELS.liveLabel}</label>
        <Switch
          id="editor-more-mirror"
          checked={liveOutputEnabled}
          disabled={mirrorUnavailable && !liveOutputEnabled}
          onCheckedChange={changeMirroring}
          aria-describedby="editor-more-mirror-hint"
        />
      </Flex>
      <Text id="editor-more-mirror-hint" size="xs" tone="muted">
        {mirrorUnavailable ? tTouch("targetUnavailable") : tTouch("mirrorHint")}
      </Text>
    </Stack>
  );
  const [liveOverrideSilence, setLiveOverrideSilence] = useState(false);
  // The last live render came back `silenced: true` (the board was left alone).
  const [liveSilenced, setLiveSilenced] = useState(false);
  const liveOverrideSilenceRef = useRef(false);
  liveOverrideSilenceRef.current = liveOverrideSilence;
  const liveSilenceActiveRef = useRef(false);
  liveSilenceActiveRef.current = liveSilence.active;

  const disableLiveOutput = useCallback(() => {
    setLiveOutputEnabled(false);
    setLiveOverrideSilence(false);
    lastLiveSentPreview.current = null;
    toast.info(t("toastLiveOutputOff"));
  }, [t]);

  // Turning Live Output off — from any path: the switch, the timeout, another
  // tab's kill switch — ends the override too, so the next session starts
  // honouring silence again. A render-phase reset (react-hooks/set-state-in-effect).
  if (useDepsChanged([liveOutputEnabled]) && !liveOutputEnabled) {
    setLiveOverrideSilence(false);
    setLiveSilenced(false);
  }

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
  }, [
    liveOutputEnabled,
    canvases,
    debouncedTemplateLines,
    debouncedLineAlignments,
    debouncedLineWrapEnabled,
    disableLiveOutput,
    LIVE_OUTPUT_TIMEOUT_MS,
  ]);

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
      // Not while the board is silenced: Home's Live Mode badge must never
      // claim a frame the board does not show (#1943).
      if (lastPreviewRef.current && (!liveSilenceActiveRef.current || liveOverrideSilenceRef.current)) {
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
  }, [liveOutputEnabled, queryClient]);

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

  // The rich editor's change handler (either editor): new lines, plus the
  // per-line alignment and wrap arrays kept in step when lines are added or
  // removed in the middle.
  const handleRichEditorChange = (newValue: string) => {
    if (isUpdatingWrap.current) {
      return;
    }
    const lines = newValue.split("\n");
    setTemplateInputStarted(true);
    setTemplateLines(lines);

    const oldLen = templateLines.length;
    const newLen = lines.length;
    if (newLen !== oldLen) {
      let prefixMatch = 0;
      while (prefixMatch < Math.min(newLen, oldLen) && lines[prefixMatch] === templateLines[prefixMatch]) {
        prefixMatch++;
      }
      let suffixMatch = 0;
      while (
        suffixMatch < Math.min(newLen, oldLen) - prefixMatch &&
        lines[newLen - 1 - suffixMatch] === templateLines[oldLen - 1 - suffixMatch]
      ) {
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
  };

  // Track if content was cleared while a mutation is in flight (to ignore stale responses)
  const shouldIgnoreNextResponse = useRef(false);
  const transitionTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch existing page if editing
  // Set once the page is deleted: nothing may fetch it again (BB-B-27).
  const [pageDeleted, setPageDeleted] = useState(false);
  const {
    data: existingPage,
    isLoading: loadingPage,
    error: pageLoadError,
  } = useQuery({
    queryKey: ["page", pageId],
    queryFn: () => api.getPage(pageId!),
    enabled: !!pageId && !pageDeleted,
    // A page that isn't there won't appear on a retry: show the missing state
    // at once instead of after the app's retries (BB-B-16).
    retry: (failures, error) => !(error instanceof ApiError && error.status === 404) && failures < 2,
  });
  const caretScrollMargin = useEditorScrollMargin(
    dockedPreview && !(pageId && loadingPage),
    editorContentRef,
    viewportBottom,
  );

  // Transition plugins (beta, deprecated): offered only while the flag is on,
  // since the backend refuses a `plugin:` strategy otherwise. The installed
  // ones come from the plugin listing, filtered to plugin_type "transition".
  const { data: pluginSettings } = usePluginSettings();
  const transitionPluginsEnabled = pluginSettings?.transition_plugins_enabled ?? false;
  const transitionPlugins = useTransitionPlugins(transitionPluginsEnabled);

  // A `plugin:<id>` override whose plugin isn't in the list — the beta is off,
  // or the plugin was uninstalled. Surface it under its raw id rather than
  // silently showing "Use the display's transition"; the user's setting is never cleared
  // behind their back.
  const unknownPluginStrategy = useMemo(() => {
    if (!transitionStrategy?.startsWith(PLUGIN_STRATEGY_PREFIX)) return null;
    const id = transitionStrategy.slice(PLUGIN_STRATEGY_PREFIX.length);
    return transitionPlugins.some((p) => p.id === id) ? null : id;
  }, [transitionStrategy, transitionPlugins]);

  // Human-readable name for the currently selected transition, for the tooltip.
  const transitionLabel = useMemo(() => {
    if (!transitionStrategy) return t("transitionUseDisplayTransition");
    if (unknownPluginStrategy) return unknownPluginStrategy;
    if (transitionStrategy.startsWith(PLUGIN_STRATEGY_PREFIX)) {
      const id = transitionStrategy.slice(PLUGIN_STRATEGY_PREFIX.length);
      return transitionPlugins.find((p) => p.id === id)?.name ?? id;
    }
    const builtIn = BUILT_IN_TRANSITIONS.find((s) => s.value === transitionStrategy);
    return builtIn ? tTransitions(`strategies.${builtIn.labelKey}.label`) : transitionStrategy;
  }, [transitionStrategy, unknownPluginStrategy, transitionPlugins, t, tTransitions]);

  // Device/size retarget (issue #1250): compare the saved geometry with the
  // editor's current one. A shrink on either axis is lossy (content that
  // doesn't fit is cut off), so the save asks for confirmation first.
  const originalDims = existingPage
    ? resolveDimensions(
        existingPage.device_type,
        existingPage.notes_wide ?? 1,
        existingPage.notes_tall ?? 1,
        existingPage.grid_rows,
        existingPage.grid_cols,
      )
    : null;
  const isShrinkingRetarget =
    !!pageId && !!originalDims && (dims.rows < originalDims.rows || dims.cols < originalDims.cols);

  // Refetches of the page (the AI drawer invalidates ["page"] after an
  // update_page) must not overwrite what the user is typing: seed once per
  // page, and re-seed later only while the editor is clean. Read through a
  // ref so the effect does not re-run on every keystroke.
  const hasUnsavedChangesRef = useRef(false);
  useEffect(() => {
    hasUnsavedChangesRef.current = hasUnsavedChanges;
  }, [hasUnsavedChanges]);
  const seededPageIdRef = useRef<string | null>(null);
  // A reload the walkthrough asked for re-seeds even though staging left
  // the editor looking dirty.
  const forceReseedRef = useRef(false);
  // While the walkthrough stages values: the snapshot to restore, and a
  // flag the autosave and Save button read.
  const stagingSnapshotRef = useRef<PageSnapshot | null>(null);
  const stagingDirtyRef = useRef<boolean | null>(null);
  const [stagingActive, setStagingActive] = useState(false);

  // Load draft or existing page data
  useEffect(() => {
    if (existingPage) {
      if (seededPageIdRef.current === existingPage.id && hasUnsavedChangesRef.current && !forceReseedRef.current) {
        return;
      }
      forceReseedRef.current = false;
      seededPageIdRef.current = existingPage.id;
      seededRevisionRef.current = existingPage.revision;
      seededProtocolsRef.current = {
        edit_protocol: existingPage.edit_protocol,
        document_protocol: existingPage.document_protocol,
      };
      durationRef.current = existingPage.duration_seconds;
      // Clear draft when loading existing page
      const draftKey = getDraftKey(pageId);
      localStorage.removeItem(draftKey);

      // Set device type from existing page
      if (existingPage.device_type) {
        setDeviceType(existingPage.device_type);
      }
      // Seed note-array grid dimensions so the preview renders at the page's
      // real size. Non-note_array pages persist no grid fields → fall back to 1×1.
      setNotesWide(existingPage.notes_wide ?? 1);
      setNotesTall(existingPage.notes_tall ?? 1);
      // A panel page's character grid; null for every other device type.
      setGridRows(existingPage.grid_rows ?? null);
      setGridCols(existingPage.grid_cols ?? null);

      const pageName = existingPage.name;
      setName(pageName);

      const rawLines = existingPage.template || Array.from({ length: numLinesRef.current }, () => "");
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
      // Per-page transition override (null = inherit the display's transition).
      const savedTransition = existingPage.transition_strategy ?? null;
      setTransitionStrategy(savedTransition);
      const savedCanvases = existingPage.canvases ?? [];
      setCanvases(savedCanvases);
      setDebouncedCanvases(savedCanvases);
      setSavedSnapshot({
        name: pageName,
        deviceType: existingPage.device_type ?? "flagship",
        geometry: JSON.stringify(
          geometryFields(
            existingPage.device_type ?? "flagship",
            existingPage.notes_wide ?? 1,
            existingPage.notes_tall ?? 1,
            existingPage.grid_rows && existingPage.grid_cols
              ? { rows: existingPage.grid_rows, cols: existingPage.grid_cols }
              : null,
          ),
        ),
        templateLines: contents,
        lineAlignments: alignments,
        lineWrapEnabled: wrapStates,
        transitionStrategy: savedTransition,
        canvases: savedCanvases,
      });
    } else if (!pageId && !loadingPage) {
      const draftKey = getDraftKey();
      if (skipDraft) {
        localStorage.removeItem(draftKey);
      } else {
        // Try to load draft for new page
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
              setCanvases(draft.canvases ?? []);
              setDebouncedCanvases(draft.canvases ?? []);
              setDraftRestored(true);
              setHasRestoredDraft(true);

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
    }
  }, [existingPage, pageId, loadingPage, skipDraft]);

  // Seed note-array grid dimensions for a NEW note_array page from the
  // configured note_array board, so the editor previews at the board's real
  // size before the page has ever been saved. Skipped once the user has picked
  // a FiestaPanel by name (``panelSizedGrid``): that grid was chosen, not
  // inferred. The currently selected board wins when it IS a note array —
  // with several note-array boards (e.g. a
  // physical array plus a FiestaPanel's virtual board), seeding from the
  // first match would author a page sized for a different board than the
  // one the user is looking at. Existing pages source their dims from the
  // load effect above; flagship/note pages never run this branch and stay
  // 1×1 (which resolves to their fixed device size).
  useEffect(() => {
    if (pageId || panelSizedGrid || deviceType !== "note_array" || !boardSettings?.boards) return;
    const boards = boardSettings.boards;
    const board =
      boards.find((b) => b.id === currentBoardId && b.device_type === "note_array") ??
      boards.find((b) => b.device_type === "note_array");
    if (!board) return;
    setNotesWide(board.notes_wide ?? 1);
    setNotesTall(board.notes_tall ?? 1);
  }, [pageId, panelSizedGrid, deviceType, boardSettings?.boards, currentBoardId]);

  // Same seeding for a NEW panel page (e.g. "New Page" on the Panel tab): a
  // panel has no implied size, so take the grid of the selected panel board,
  // else the first panel board, else the first panel the API lists.
  useEffect(() => {
    if (pageId || panelSizedGrid || deviceType !== "panel" || (gridRows && gridCols)) return;
    const boards = boardSettings?.boards ?? [];
    const sized = (b: (typeof boards)[number]) => b.device_type === "panel" && !!b.grid_rows && !!b.grid_cols;
    const board = boards.find((b) => b.id === currentBoardId && sized(b)) ?? boards.find(sized);
    if (board?.grid_rows && board.grid_cols) {
      setGridRows(board.grid_rows);
      setGridCols(board.grid_cols);
      setTargetBoardId(board.id);
      return;
    }
    const target = panelTargets.find((p) => p.deviceType === "panel");
    if (target) {
      setGridRows(target.rows);
      setGridCols(target.cols);
    }
  }, [pageId, panelSizedGrid, deviceType, gridRows, gridCols, boardSettings?.boards, currentBoardId, panelTargets]);

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

  // Canvases preview a little later than text: a paint stroke sends many edits.
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedCanvases(canvases);
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [canvases]);

  // Auto-save draft to localStorage (debounced)
  useEffect(() => {
    const draftKey = getDraftKey(pageId);

    // Don't save draft if we just loaded an existing page
    if (existingPage) {
      return;
    }
    // A staged reveal is not the user's draft.
    if (stagingActive) {
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
          ...(canvases.length > 0 && { canvases }),
          timestamp: Date.now(),
        };
        localStorage.setItem(draftKey, JSON.stringify(draft));
      } catch (error) {
        // Ignore localStorage errors (quota exceeded, etc.)
        console.warn("Failed to save draft:", error);
      }
    }, 1000); // Save draft 1 second after last change

    return () => clearTimeout(timeoutId);
  }, [name, templateLines, lineAlignments, lineWrapEnabled, canvases, pageId, existingPage, stagingActive]);

  // Auto-resize textareas when content changes
  useEffect(() => {
    // Wait for DOM to update, then resize all textareas
    const timer = setTimeout(() => {
      const textareas = document.querySelectorAll<HTMLTextAreaElement>(
        'textarea[placeholder*="Use {{variable}} syntax"]',
      );
      textareas.forEach((textarea) => {
        textarea.style.height = "auto";
        textarea.style.height = `${textarea.scrollHeight}px`;
      });
    }, 0);
    return () => clearTimeout(timer);
  }, [templateLines]);

  /**
   * Lines whose wrap budget is "stuck" at 1 row — wrap is enabled but no
   * empty/wrap-enabled line follows, so long content can't flow downward.
   * Mirrors the cheap server-side checks in render_lines (literal-empty +
   * wrap-flag); skips the rendered-empty check, which would require running
   * the template engine in the browser. Conservative client-side estimate.
   */
  const wrapBudgetWarnings = useMemo<number[]>(() => {
    const warnings: number[] = [];
    const previewRows = preview ? preview.split("\n") : [];
    for (let i = 0; i < lineWrapEnabled.length; i++) {
      if (!lineWrapEnabled[i]) continue;
      // Skip wrap lines whose template content is empty — nothing to warn about.
      const ownLine = (templateLines[i] || "").replace(/^\{wrap\}/, "").replace(/^\{(left|center|right)\}/i, "");
      if (ownLine.trim() === "") continue;

      let budget = 1;
      for (let j = i + 1; j < templateLines.length; j++) {
        const raw = templateLines[j] || "";
        const stripped = raw.replace(/^\{wrap\}/, "").replace(/^\{(left|center|right)\}/i, "");
        if (stripped.trim() === "") {
          budget++;
          continue;
        }
        if (lineWrapEnabled[j] || raw.startsWith("{wrap}")) {
          budget++;
          continue;
        }
        break;
      }
      if (budget !== 1) continue;

      // Only warn if the rendered preview row at position i looks saturated:
      // its trimmed length reaches the board width, suggesting the wrap
      // engine had to truncate. This avoids false positives when the user's
      // value happens to fit comfortably in one row.
      const trimmed = (previewRows[i] || "").trimEnd();
      if (trimmed.length >= dims.cols) {
        warnings.push(i + 1); // 1-indexed for user-facing message
      }
    }
    return warnings;
  }, [lineWrapEnabled, templateLines, preview, dims.cols]);

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

  type SubmittedForm = NonNullable<typeof savedSnapshot>;
  const snapshotForm = (): SubmittedForm => ({
    name,
    deviceType,
    geometry: JSON.stringify(geometryFields(deviceType, notesWide, notesTall, panelGrid)),
    templateLines: [...templateLines],
    lineAlignments: [...lineAlignments],
    lineWrapEnabled: [...lineWrapEnabled],
    transitionStrategy,
    canvases: structuredClone(canvases),
  });

  // Save mutation
  const saveMutation = useMutation({
    // Since the Phase 2 conventions pass the two endpoints answer differently:
    // PUT gives `{ page, incompatible_references }`, POST gives the bare page
    // at 201. Both are normalized to PageUpdateResponse here so `onSuccess`
    // reads one shape — a create simply reports no stale references, which is
    // true: a brand-new page cannot have any.
    mutationFn: async (
      intent: { showRequested: boolean } | void,
    ): Promise<PageUpdateResponse & { submitted: SubmittedForm; showRequested: boolean }> => {
      const submitted = snapshotForm();
      const showRequested = intent?.showRequested ?? false;
      showAfterSaveRef.current = false;
      const { cleanedLines, metadata } = processLinesWithPrefixes(templateLines, lineAlignments, lineWrapEnabled);
      if (pageId) {
        const payload: PageUpdate = {
          expected_revision: seededRevisionRef.current,
          name,
          device_type: deviceType,
          template: cleanedLines,
          line_metadata: metadata,
          // Always sent, even when null: the API clears a stored override only
          // for keys it actually receives, so omitting this would silently keep
          // a previous per-page transition after the user chose "Use the display's transition".
          transition_strategy: transitionStrategy,
          ...geometryFields(deviceType, notesWide, notesTall, panelGrid),
          // Always sent: null clears canvases the user deleted.
          canvases: canvases.length > 0 ? canvases : null,
        };
        return { ...(await api.updatePage(pageId, payload)), submitted, showRequested };
      } else {
        const payload: PageCreate = {
          name,
          type: "template" as PageType,
          device_type: deviceType,
          template: cleanedLines,
          line_metadata: metadata,
          transition_strategy: transitionStrategy,
          ...geometryFields(deviceType, notesWide, notesTall, panelGrid),
          ...(canvases.length > 0 && { canvases }),
        };
        const created = await api.createPage(payload);
        return { page: created, incompatible_references: [], submitted, showRequested };
      }
    },
    onSuccess: (data) => {
      // The saved page is always `data.page` after the normalization in
      // mutationFn — reading `data.id` here was undefined and silently skipped
      // every id-keyed cleanup below when creating a new page (issue #1586).
      const targetPageId = data.page.id;
      const newerEdits = JSON.stringify(snapshotForm()) !== JSON.stringify(data.submitted);
      hasUnsavedChangesRef.current = newerEdits;

      // Clear draft on successful save
      const draftKey = getDraftKey(targetPageId);
      if (!newerEdits) {
        localStorage.removeItem(draftKey);
        if (!pageId) localStorage.removeItem(getDraftKey());
      }

      // Clear preview cache for this page
      if (targetPageId) {
        clearPreviewCacheForPage(targetPageId);
      }

      // Invalidate pages list with active refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });

      // The mutation response is authoritative for the editor. Refetching its
      // detail here can race the committed snapshot with an older response.
      if (targetPageId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.pagePreview(targetPageId), refetchType: "active" });
      }

      // Invalidate all page previews since they may have changed
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: "active" });

      // If this page is currently active, refresh the active page data
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: "active" });

      if (!pageId) {
        kitToast.success(tTouch("savedToPages"), {
          description: tTouch("savedToPagesDescription", { name: data.page.name }),
          closeButton: true,
          duration: 6000,
          position: dockedPreview ? "bottom-center" : "top-right",
          style: dockedPreview ? { bottom: "calc(64px + env(safe-area-inset-bottom))" } : { width: "380px" },
          action: { label: tTouch("showNow"), onClick: () => requestShowNowRef.current(data.page.id) },
          cancel: {
            label: tTouch("addToSchedule"),
            onClick: () => {
              // The Schedule owns the globally selected display. Carry the
              // explicit editor target into that destination before loading it.
              if (selectedBoardId) setCurrentBoardId(selectedBoardId);
              window.location.assign(appUrl(`/schedule?prefill_page_id=${encodeURIComponent(data.page.id)}`));
            },
          },
        });
      }
      seededRevisionRef.current = data.page.revision;
      seededProtocolsRef.current = {
        edit_protocol: data.page.edit_protocol,
        document_protocol: data.page.document_protocol,
      };
      queryClient.setQueryData(["page", data.page.id], data.page);
      if (!pageId) {
        seededPageIdRef.current = data.page.id;
        setCreatedPageId(data.page.id);
      }
      setSavedAt(new Date());
      setSavedSnapshot(data.submitted);
      if (newerEdits) {
        toast.info(tTouch("newerChangesUnsaved"));
      } else if (data.showRequested) {
        setShowPageId(data.page.id);
      }

      // Stale-reference warning after a device/size retarget (issue #1250):
      // list the schedules / active pages now pointing this page at a board
      // it no longer fits. Non-blocking — the save already succeeded and
      // nothing is auto-removed.
      const incompatibleRefs = data.incompatible_references;
      if (incompatibleRefs.length > 0) {
        const list = incompatibleRefs
          .map(
            (ref) =>
              `${ref.board_name} (${ref.surface === "schedule" ? t("retargetSurfaceSchedule") : t("retargetSurfaceActivePage")})`,
          )
          .join(", ");
        toast.warning(t("retargetIncompatibleWarning", { list }), { duration: 10000 });
      }

      onSave?.();
    },
    onError: (error: Error) => {
      showAfterSaveRef.current = false;
      toast.error(error.message);
    },
  });

  requestShowNowRef.current = (savedId) => {
    if (!name.trim()) {
      document.getElementById("page-name")?.focus();
      return;
    }
    if (saveMutation.isPending || stagingActive) return;
    if (hasUnsavedChangesRef.current || !(pageId ?? savedId)) {
      showAfterSaveRef.current = true;
      if (isShrinkingRetarget) setConfirmRetargetOpen(true);
      else saveMutation.mutate({ showRequested: true });
    } else setShowPageId(pageId ?? savedId ?? null);
  };

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (hasUnsavedChangesRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (!name.trim()) {
          document.getElementById("page-name")?.focus();
          return;
        }
        if (!saveMutation.isPending && !stagingActive) {
          if (isShrinkingRetarget) setConfirmRetargetOpen(true);
          else saveMutation.mutate();
        }
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("keydown", onKey);
    };
  }, [name, saveMutation, stagingActive, isShrinkingRetarget]);

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => api.deletePage(pageId!, seededRevisionRef.current),
    onSuccess: (data) => {
      // Clear preview cache for deleted page
      if (pageId) {
        clearPreviewCacheForPage(pageId);
      }

      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });

      // Drop the deleted page and its preview from the cache. Invalidating
      // them refetched a page that no longer exists: a 404 after every
      // delete (BB-B-27).
      if (pageId) {
        setPageDeleted(true);
        queryClient.removeQueries({ queryKey: ["page", pageId] });
        queryClient.removeQueries({ queryKey: queryKeys.pagePreview(pageId) });
      }

      // Invalidate all page previews
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: "active" });

      // Also invalidate active page if it was updated
      if (data.active_page_updated) {
        queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
        queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: "active" });
      }

      // Show appropriate message
      if (data.default_page_created) {
        toast.success(t("toastDeletedDefaultCreated"));
      } else if (data.active_page_updated) {
        toast.success(t("toastDeletedActiveUpdated"));
      } else {
        toast.success(t("toastPageDeleted"));
      }
      hasUnsavedChangesRef.current = false;
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
      // Mirror the synced page's note-array / panel geometry so the preview
      // matches the source board.
      if (data.notes_wide != null) setNotesWide(data.notes_wide);
      if (data.notes_tall != null) setNotesTall(data.notes_tall);
      if (data.grid_rows != null) setGridRows(data.grid_rows);
      if (data.grid_cols != null) setGridCols(data.grid_cols);

      toast.success(t("toastSyncedFrom", { name: data.page_name }));
    },
    onError: () => {
      toast.error(t("toastNoActiveDisplay"));
    },
  });

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: async () => {
      const { cleanedLines, metadata } = processLinesWithPrefixes(
        debouncedTemplateLines,
        debouncedLineAlignments,
        debouncedLineWrapEnabled,
      );

      const hasCanvases = debouncedCanvases.length > 0;
      const hasContent = hasCanvases || cleanedLines.some((line) => line.trim().length > 0);

      if (!hasContent) {
        const emptyCount = dims.rows;
        return {
          rendered: "\n".repeat(emptyCount - 1),
          lines: Array.from({ length: emptyCount }, () => ""),
          line_count: emptyCount,
        };
      }

      // Canvases ride along only when there are some: every other render's
      // request is exactly what it always was.
      if (hasCanvases) {
        return api.renderTemplate(
          cleanedLines,
          metadata,
          deviceType,
          notesWide,
          notesTall,
          panelGrid,
          previewBoardId,
          debouncedCanvases,
        );
      }
      // Web 2.10: a page with formulas asks this render for their values (H5),
      // so the formula chips cost no second render per edit. Other pages'
      // requests are exactly what they always were.
      const hasFormula = templateHasFormula(cleanedLines);
      if (hasFormula) {
        return api.renderTemplate(
          cleanedLines,
          metadata,
          deviceType,
          notesWide,
          notesTall,
          panelGrid,
          previewBoardId,
          undefined,
          { diagnostics: true },
        );
      }
      return api.renderTemplate(cleanedLines, metadata, deviceType, notesWide, notesTall, panelGrid, previewBoardId);
    },
    onSuccess: (data: TemplateRenderResponse) => {
      if (shouldIgnoreNextResponse.current) {
        shouldIgnoreNextResponse.current = false;
        return;
      }
      setCharsetIssues(drawnDifferently(data.charset_issues));
      setPreviewDiagnostics(data.diagnostics ?? null);
      setPreviewLayers(data.layers ?? null);
      setCanvasIssues(data.canvas_issues ?? []);
      setCanvasError(null);

      const hasContent = debouncedCanvases.length > 0 || debouncedTemplateLines.some((line) => line.trim().length > 0);
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
    },
    onError: (error: Error) => {
      setPreview(null);
      setCharsetIssues([]);
      setPreviewDiagnostics(null);
      setPreviewLayers(null);
      setCanvasIssues([]);
      // With canvases, a refusal is most likely theirs (a 422 naming the field).
      setCanvasError(debouncedCanvases.length > 0 ? error.message : null);
    },
    onSettled: () => {
      // Canvas-only responses have blank rendered text and return early above.
      // Drain edits on every completion, including failures, using the latest
      // mutation closure so queued canvases and board changes are not lost.
      if (needsRePreview.current) {
        needsRePreview.current = false;
        previewMutationRef.current.mutate();
      }
    },
  });

  // react-query returns a new `previewMutation` object identity on most
  // renders, so it can't be listed directly in the effect's dependency array
  // below without making the debounced-preview effect (and its 200ms
  // setTimeout) re-fire on every render instead of only when the tracked
  // template/alignment/wrap state actually changes. Read the latest mutation
  // through a ref instead — same pattern as lastPreviewRef/liveOutputEnabledRef
  // above.
  const previewMutationRef = useRef(previewMutation);
  previewMutationRef.current = previewMutation;

  // Auto-preview when debounced template lines or alignments change (debounced)
  // Skipped when live mode is on — the live fast path handles preview updates directly.
  // notesWide/notesTall are tracked too so widening a note array re-previews at
  // the new width (issue #2032): a notesTall change already resizes
  // templateLines, but a width change leaves the row count untouched.
  useEffect(() => {
    if (liveOutputEnabled) {
      needsRePreview.current = false;
      if (previewMutationRef.current.isPending) {
        shouldIgnoreNextResponse.current = true;
        previewMutationRef.current.reset();
      } else if (previewMutationRef.current.isError) {
        // A preview that failed before mirroring is not the render behind the
        // hints any more; clear it so its error cannot linger (FABLE-2541 N15).
        previewMutationRef.current.reset();
      }
      return;
    }

    const hasCanvases = debouncedCanvases.length > 0;
    const hasContent = hasCanvases || debouncedTemplateLines.some((line) => line.trim().length > 0);

    if (!hasContent) {
      setPreview(null);
      setPreviewLayers(null);
      setCanvasIssues([]);
      setCanvasError(null);
      needsRePreview.current = false;
      if (previewMutationRef.current.isPending) {
        shouldIgnoreNextResponse.current = true;
        previewMutationRef.current.reset();
      }
      return;
    }

    shouldIgnoreNextResponse.current = false;

    // AI-driven mutations skip the typing-debounce window so the board
    // updates as soon as the model finishes applying its patch.
    const debounceMs = skipNextPreviewDebounceRef.current ? 0 : 200;
    skipNextPreviewDebounceRef.current = false;
    const timeoutId = setTimeout(() => {
      const stillHasContent = hasCanvases || debouncedTemplateLines.some((line) => line.trim().length > 0);

      if (!stillHasContent) {
        setPreview(null);
        shouldIgnoreNextResponse.current = false;
        if (previewMutationRef.current.isPending) {
          shouldIgnoreNextResponse.current = true;
          previewMutationRef.current.reset();
        }
        return;
      }

      if (!previewMutationRef.current.isPending) {
        previewMutationRef.current.mutate();
      } else {
        needsRePreview.current = true;
      }
    }, debounceMs);

    return () => {
      clearTimeout(timeoutId);
      // Also clear transition timeout on cleanup
      if (transitionTimeoutRef.current) {
        clearTimeout(transitionTimeoutRef.current);
        transitionTimeoutRef.current = null;
      }
    };
  }, [
    debouncedTemplateLines,
    debouncedLineAlignments,
    debouncedLineWrapEnabled,
    debouncedCanvases,
    liveOutputEnabled,
    notesWide,
    notesTall,
    gridRows,
    gridCols,
    // Another target board is another character set to check against.
    previewBoardId,
  ]);

  // Track request status for the sending indicator; the fast path below is
  // the only trigger, so enabling Live on an existing preview sends once.
  const liveSendMutation = useMutation({
    mutationFn: (args: Parameters<typeof api.renderTemplateLive>) => api.renderTemplateLive(...args),
  });
  const liveSendMutationRef = useRef(liveSendMutation);
  liveSendMutationRef.current = liveSendMutation;

  // Live edit fast path: single 100ms debounce → single API call → preview + board update.
  // Bypasses the normal double-debounce (150ms + 200ms) and double API call chain.
  // Uses IMMEDIATE state (not debounced) and AbortController to cancel stale requests.
  useEffect(() => {
    if (!liveOutputEnabled) {
      liveCanvasAttemptedRef.current = false;
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

    // A cancelled fetch may already have written its canvas to the board.
    // Clear removed layers locally while the replacement request is pending.
    if (canvases.length === 0) {
      setPreviewLayers([]);
      setCanvasIssues([]);
      setCanvasError(null);
    }

    const hasContent =
      templateLines.some((line) => line.trim().length > 0) ||
      canvases.length > 0 ||
      lastLiveSentPreview.current !== null ||
      liveCanvasAttemptedRef.current;
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
        const { cleanedLines, metadata } = processLinesWithPrefixes(templateLines, lineAlignments, lineWrapEnabled);

        if (canvases.length > 0) liveCanvasAttemptedRef.current = true;
        const data = await liveSendMutationRef.current.mutateAsync([
          cleanedLines,
          selectedBoardId || undefined,
          metadata,
          deviceType,
          notesWide,
          notesTall,
          controller.signal,
          panelGrid,
          {
            overrideSilence: liveOverrideSilence,
            canvases,
            // Web 2.10: a page with formulas takes their values from this
            // render, the only one per edit while mirroring (FABLE-2541 M2).
            diagnostics: templateHasFormula(cleanedLines),
          },
        ]);

        if (controller.signal.aborted) return;

        setPreviewDiagnostics(data.diagnostics ?? null);
        setPreviewLayers(data.layers ?? null);
        setCanvasIssues(data.canvas_issues ?? []);
        setCanvasError(null);
        setPreview(data.rendered);
        if (data.rendered) {
          setLastPreview(data.rendered);
        }
        // Remember the rendered content even during silence, so deleting
        // the final content can still render an explicitly empty page.
        lastLiveSentPreview.current = data.rendered;
        setLiveSilenced((previous) => data.silenced === true || (liveOverrideSilence && previous));
        if (data.sent_to_board) {
          // Broadcast to the Home page (same tab and other tabs) so navigating
          // there shows this content — only a frame the board really shows.
          queryClient.setQueryData(["liveOutputMessage"], data.rendered);
          writeLiveOutputMessage(data.rendered);
        } else if (data.silenced && queryClient.getQueryData(["liveOutputMessage"]) != null) {
          // A frame primed before silence was known: take the claim back.
          queryClient.setQueryData(["liveOutputMessage"], null);
          writeLiveOutputMessage(null);
        }
      } catch (error) {
        if (
          controller.signal.aborted ||
          liveAbortRef.current !== controller ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          return;
        }
        console.error("[LiveFastPath] Error:", error);
        toast.error(t("toastLiveSendFailed"));
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
  }, [
    liveOutputEnabled,
    canvases,
    templateLines,
    lineAlignments,
    lineWrapEnabled,
    selectedBoardId,
    deviceType,
    notesWide,
    notesTall,
    panelGrid,
    queryClient,
    // Choosing "Send to board anyway" re-sends the current preview at once.
    liveOverrideSilence,
    t,
  ]);

  // Draw mode: a committed stroke is applied straight to the editor's live
  // ProseMirror doc (one undo step), which fires onChange -> setTemplateLines
  // on its own — no separate setTemplateLines call needed here. Painted rows
  // are positional, so force left alignment + wrap off so the client-side
  // preview composition below (and the server render on save) don't
  // reinterpret the painted cells.
  const handleStrokeCommit = useCallback(
    (cells: StrokeCell[]) => {
      setStrokePreviewCells([]);
      const rows = tipTapRef.current?.applyStroke(cells, drawBrush) ?? [];
      if (rows.length === 0) return;
      // Capture the pre-stroke metadata so undoing this stroke can restore
      // it; a new stroke also invalidates any redoable strokes (the editor's
      // redo stack is cleared by the new doc change).
      const hist = strokeMetaHistoryRef.current;
      hist.done.push({
        rows,
        alignments: rows.map((r) => lineAlignmentsRef.current[r] ?? "left"),
        wraps: rows.map((r) => lineWrapEnabledRef.current[r] ?? false),
      });
      hist.undone = [];
      // Painted lines are positional: force left alignment + wrap off.
      setLineAlignments((prev) => {
        const next = [...prev];
        for (const r of rows) next[r] = "left";
        return next;
      });
      setLineWrapEnabled((prev) => {
        const next = [...prev];
        for (const r of rows) next[r] = false;
        return next;
      });
    },
    [drawBrush],
  );

  // Undo/redo crossed a paint-stroke boundary in the editor's history: the
  // editor already rewound/reapplied the ProseMirror doc — mirror that onto
  // the alignment/wrap metadata the stroke commit force-overwrote.
  const handleDrawHistoryEvent = useCallback((event: DrawHistoryEvent) => {
    if (!event.stroke) return;
    const hist = strokeMetaHistoryRef.current;
    if (event.action === "undo") {
      const entry = hist.done.pop();
      if (!entry) return;
      hist.undone.push(entry);
      setLineAlignments((prev) => {
        const next = [...prev];
        entry.rows.forEach((r, i) => {
          next[r] = entry.alignments[i] ?? "left";
        });
        return next;
      });
      setLineWrapEnabled((prev) => {
        const next = [...prev];
        entry.rows.forEach((r, i) => {
          next[r] = entry.wraps[i] ?? false;
        });
        return next;
      });
    } else {
      const entry = hist.undone.pop();
      if (!entry) return;
      hist.done.push(entry);
      setLineAlignments((prev) => {
        const next = [...prev];
        for (const r of entry.rows) next[r] = "left";
        return next;
      });
      setLineWrapEnabled((prev) => {
        const next = [...prev];
        for (const r of entry.rows) next[r] = false;
        return next;
      });
    }
  }, []);

  // Draw-mode preview composition (client-side, instant — no server
  // round-trip for painted rows). Falls back to the server-rendered preview
  // for rows that aren't locally renderable (dynamic content, non-left
  // alignment, or wrap enabled).
  const drawPreviewMessage = useMemo(() => {
    if (!drawMode) return null;
    const serverLines = (preview ?? lastPreview ?? "").split("\n");
    const strokeByRow = new Map<number, CellPaint[]>();
    const strokeCell = brushToCell(drawBrush);
    for (const c of strokePreviewCells) {
      const arr = strokeByRow.get(c.row) ?? [];
      arr.push({ col: c.col, cell: strokeCell });
      strokeByRow.set(c.row, arr);
    }
    const out: string[] = [];
    for (let r = 0; r < dims.rows; r++) {
      const tpl = templateLines[r] ?? "";
      const strokePaints = strokeByRow.get(r);
      const isLocallyRenderable =
        isPositionalLine(tpl) && (lineAlignments[r] ?? "left") === "left" && !(lineWrapEnabled[r] ?? false);
      if (strokePaints) {
        // Preview exactly what committing this stroke will produce
        // (including variable stripping + left alignment).
        out.push(renderPositionalLine(paintLine(tpl, strokePaints, dims.cols)));
      } else if (isLocallyRenderable) {
        out.push(renderPositionalLine(tpl));
      } else {
        out.push(serverLines[r] ?? "");
      }
    }
    return out.join("\n");
  }, [
    drawMode,
    strokePreviewCells,
    drawBrush,
    templateLines,
    lineAlignments,
    lineWrapEnabled,
    preview,
    lastPreview,
    dims.rows,
    dims.cols,
  ]);

  // The `?` shortcut list (slice 2.7): one open state for the header button,
  // the toolbar-row hint and the `?` key. It hangs from the Template heading,
  // in the template column (07 `57:27771`; DD-W30).
  const shortcutList = useEditorShortcutList();
  const templateHeadingRef = useRef<HTMLDivElement>(null);
  const shortcutListProps = {
    state: shortcutList,
    // Hidden on a pixel board's Canvases surface: the kit then hangs the list
    // from the trigger that opened it (or its gutter on touch).
    anchorRef: pixelBoard && editingSurface !== "text" ? undefined : templateHeadingRef,
    // Only a split-flap preview can bind BoardViewport's keys; an LED board
    // previews through DevicePreview (draw mode always paints flaps).
    boardViewport: previewBindsBoardViewportKeys({ ledPreview: !drawMode && isLedModel(previewModel) }),
  };
  // 07 `57:28704` puts the hint on the toolbar row. The rich flap toolbar
  // has room from xl up; at tablet widths keep the hint above the template,
  // sharing the existing preview-toggle row below lg (DD-W59).
  const isXlUp = useMediaQuery("(min-width: 1280px)");
  const hintOnToolbar = isXlUp && editorMode === "rich" && !editorCharset;

  // Keyboard shortcuts while drawing: Esc exits; undo/redo work even though
  // the editor itself is visually hidden (and thus not focused) in draw mode.
  useEffect(() => {
    if (!drawMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return;
      // Keys come from the shortcut registry the `?` list reads (slice 2.7).
      if (matchesShortcut(e, EDITOR_SHORTCUTS.exitDrawMode)) {
        setDrawMode(false);
        return;
      }
      if (matchesShortcut(e, EDITOR_SHORTCUTS.undo)) {
        e.preventDefault();
        tipTapRef.current?.undo();
      } else if (matchesShortcut(e, EDITOR_SHORTCUTS.redo)) {
        e.preventDefault();
        tipTapRef.current?.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawMode]);

  // Compact editors keep Save and Show now in the bar. Secondary actions
  // share their original handlers/dialogs between desktop chrome and More.
  const secondaryActions = (
    <TooltipProvider skipDelayDuration={0}>
      <Flex align="center" gap="1.5" className="flex-wrap">
        {/* Per-page transition override. Null (the default) inherits
         *  the global setting; the trigger carries a dot when this
         *  page overrides it. */}
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size={dockedPreview ? "touch" : "icon"}
                  // In the phone More sheet a labelled row, not a bare icon (BB-B-24).
                  className={cn("relative", dockedPreview ? "gap-2" : "h-9 w-9")}
                  aria-label={t("transitionPickerAriaLabel")}
                >
                  <Sparkles className={`h-4 w-4 ${transitionStrategy ? "text-brand" : ""}`} />
                  {dockedPreview && t("transitionPickerAriaLabel")}
                  {transitionStrategy && (
                    <Text
                      as="span"
                      aria-hidden="true"
                      className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-brand"
                    />
                  )}
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <Text>{t("transitionPickerTooltip", { strategy: transitionLabel })}</Text>
            </TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="text-xs font-medium">{t("transitionMenuTitle")}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup
              value={transitionStrategy ?? TRANSITION_INHERIT}
              onValueChange={(value) => setTransitionStrategy(value === TRANSITION_INHERIT ? null : String(value))}
            >
              {/* Base UI's MenuRadioItem defaults closeOnClick to
               *  false; without this the menu stays open after a
               *  pick and its inert backdrop swallows clicks on
               *  Save. Picking a transition is a one-shot choice,
               *  so every item closes the menu. */}
              <DropdownMenuRadioItem value={TRANSITION_INHERIT} className="text-xs" closeOnClick>
                {t("transitionUseDisplayTransition")}
              </DropdownMenuRadioItem>
              <DropdownMenuLabel className="text-[11px] text-muted-foreground">
                {t("transitionBuiltInGroup")}
              </DropdownMenuLabel>
              {BUILT_IN_TRANSITIONS.map((strategy) => (
                <DropdownMenuRadioItem key={strategy.value} value={strategy.value} className="text-xs" closeOnClick>
                  {tTransitions(`strategies.${strategy.labelKey}.label`)}
                </DropdownMenuRadioItem>
              ))}
              {transitionPlugins.length > 0 && (
                <DropdownMenuLabel className="text-[11px] text-muted-foreground">
                  {t("transitionPluginsGroup")}
                </DropdownMenuLabel>
              )}
              {transitionPlugins.map((plugin) => (
                <DropdownMenuRadioItem
                  key={plugin.id}
                  value={`${PLUGIN_STRATEGY_PREFIX}${plugin.id}`}
                  className="text-xs"
                  closeOnClick
                >
                  {plugin.name}
                </DropdownMenuRadioItem>
              ))}
              {unknownPluginStrategy && (
                <DropdownMenuRadioItem value={transitionStrategy!} className="text-xs" closeOnClick>
                  {unknownPluginStrategy}
                </DropdownMenuRadioItem>
              )}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        {/* Delete button - only show when editing */}
        {pageId && (
          <AlertDialog>
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size={dockedPreview ? "touch" : "icon"}
                    className={cn(
                      "text-destructive hover:text-destructive hover:bg-destructive/10",
                      dockedPreview ? "gap-2" : "h-9 w-9",
                    )}
                    aria-label={t("deletePageTooltip")}
                  >
                    <Trash2 className="h-4 w-4" />
                    {dockedPreview && t("deletePageTooltip")}
                  </Button>
                </AlertDialogTrigger>
              </TooltipTrigger>
              <TooltipContent>
                <Text>{t("deletePageTooltip")}</Text>
              </TooltipContent>
            </Tooltip>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t("deletePageTitle")}</AlertDialogTitle>
                <AlertDialogDescription>
                  {name ? t("deletePageConfirmation", { pageName: name }) : t("deletePageConfirmationGeneric")}
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
        {dockedPreview && (
          <Button
            variant="secondary"
            size="sm"
            className="h-8 gap-1.5 px-3 text-xs"
            aria-keyshortcuts="?"
            onClick={() => shortcutList.setOpenFrom("header")}
          >
            <Zap className="h-3.5 w-3.5" aria-hidden />
            {tShortcuts("button")}
          </Button>
        )}
        {/* Export button — only on existing pages */}
        {pageId && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="secondary"
                size="sm"
                className="h-8 gap-1.5 px-3 text-xs"
                disabled={hasUnsavedChanges}
                onClick={async () => {
                  try {
                    const res = await api.getPageShareString(pageId);
                    setExportShareString(res.share_string);
                    setExportOpen(true);
                  } catch {
                    toast.error(t("exportFailed"));
                  }
                }}
                aria-label={t("exportPageAriaLabel")}
              >
                <Upload className="h-3.5 w-3.5" />
                {t("exportPage")}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <Text>{hasUnsavedChanges ? t("exportDisabledTooltip") : t("exportPageTooltip")}</Text>
            </TooltipContent>
          </Tooltip>
        )}
      </Flex>
    </TooltipProvider>
  );
  const mirrorMoreContent = (
    <Stack gap="3">
      {mirrorControl}
      {dockedPreview && secondaryActions}
    </Stack>
  );

  // Web 2.10 (04c): formula values, Live/Sample/Missing, Inspect and the
  // docked formula workbench. Inert for canvases and plain-text-only boards.
  const formulaIdeTarget = useMemo(() => {
    if (baselineDisplay || debouncedCanvases.length > 0) return null;
    if (!debouncedTemplateLines.some((line) => line.trim().length > 0)) return null;
    const { cleanedLines, metadata } = processLinesWithPrefixes(
      debouncedTemplateLines,
      debouncedLineAlignments,
      debouncedLineWrapEnabled,
    );
    return {
      template: cleanedLines,
      lineMetadata: metadata,
      deviceType,
      notesWide,
      notesTall,
      grid: panelGrid,
      boardId: previewBoardId,
    };
  }, [
    baselineDisplay,
    debouncedCanvases,
    debouncedTemplateLines,
    debouncedLineAlignments,
    debouncedLineWrapEnabled,
    deviceType,
    notesWide,
    notesTall,
    panelGrid,
    previewBoardId,
  ]);
  const formulaIde = useFormulaIde({
    target: formulaIdeTarget,
    live: {
      diagnostics: previewDiagnostics,
      lines: (preview ?? "").split("\n"),
      // While mirroring the live render is the one behind the hints (N15).
      failed: !liveOutputEnabled && previewMutation.isError,
    },
    available: !baselineDisplay && debouncedCanvases.length === 0,
    desktop: !dockedPreview,
    mirroring: liveOutputEnabled,
    stopMirroring: () => changeMirroring(false),
    boardCols: dims.cols,
    editTemplateLine: (index, edit) => {
      setTemplateInputStarted(true);
      setTemplateLines((lines) => lines.map((line, i) => (i === index ? edit(line) : line)));
    },
  });
  // What the live preview shows. Keeps the previous message visible during
  // loading/transition, so tiles cycle through characters (like a real board)
  // instead of flashing empty.
  const editorPreviewMessage = drawMode
    ? drawPreviewMessage
    : (() => {
        const hasContent = debouncedTemplateLines.some((line) => line.trim().length > 0);
        const isPending = previewMutation.isPending;
        const shouldIgnore = shouldIgnoreNextResponse.current;

        if (isTransitioning && lastPreview) return lastPreview;
        if (preview !== null) return preview;
        if (!hasContent && !isPending && !shouldIgnore) return "";
        if (isPending && hasContent && !shouldIgnore && lastPreview) return lastPreview;
        if (isPending && hasContent && !shouldIgnore) return "";
        return null;
      })();
  // Sample, Missing or another time render through the formula IDE (hub H6).
  const shownPreviewMessage = drawMode ? editorPreviewMessage : (formulaIde.previewOverride ?? editorPreviewMessage);

  const requestSave = () => {
    if (!name.trim()) {
      document.getElementById("page-name")?.focus();
      return;
    }
    // A shrinking retarget loses content — confirm first.
    if (isShrinkingRetarget) {
      setConfirmRetargetOpen(true);
    } else {
      saveMutation.mutate();
    }
  };

  // Web 2.9 (04b): complex-editing lenses for big boards and note arrays on
  // the desktop pane, and the hub's real-width overflow check (H4) everywhere.
  const [previewStage, setPreviewStage] = useState<HTMLElement | null>(null);
  // One stage element serves 2.9's lenses and 2.10's Inspect. The ref must be
  // stable: an inline callback runs again on every commit, and its
  // setPreviewStage(null) / (el) pair kept the whole editor re-committing.
  const formulaBoardRef = formulaIde.boardProps.ref;
  const setPreviewStageElement = useCallback(
    (el: HTMLDivElement | null) => {
      setPreviewStage(el);
      formulaBoardRef.current = el;
    },
    [formulaBoardRef],
  );
  const complexEditing = useComplexEditing({
    rows: dims.rows,
    cols: dims.cols,
    deviceType,
    notesWide,
    notesTall,
    enabled: !dockedPreview && !baselineDisplay && !drawMode && !isLedModel(previewModel),
    stage: previewStage,
    previewMode,
    onPreviewModeChange: changePreviewMode,
  });
  const complexMinimapId = useId();
  const overflowTarget = useMemo(() => {
    const { cleanedLines, metadata } = processLinesWithPrefixes(
      debouncedTemplateLines,
      debouncedLineAlignments,
      debouncedLineWrapEnabled,
    );
    return {
      template: cleanedLines,
      lineMetadata: metadata,
      boardId: previewBoardId,
      deviceType,
      notesWide,
      notesTall,
      grid: panelGrid,
    };
    // processLinesWithPrefixes is a pure, per-render helper.
  }, [
    debouncedTemplateLines,
    debouncedLineAlignments,
    debouncedLineWrapEnabled,
    previewBoardId,
    deviceType,
    notesWide,
    notesTall,
    panelGrid,
  ]);
  const lineOverflow = useLineOverflow(overflowTarget, dims.cols, !baselineDisplay && !newPageEmpty);
  // The lenses describe the board on screen, so they read the shown message
  // (a Sample/Missing/render-at override included), never the live one behind it.
  const renderedRows = useMemo(() => (shownPreviewMessage ?? "").split("\n"), [shownPreviewMessage]);
  const straddles = useMemo(
    () => (complexEditing.noteArray ? seamStraddles(renderedRows, notesWide) : []),
    [complexEditing.noteArray, renderedRows, notesWide],
  );
  const rowBandsEnabled = complexEditing.bigBoard && isXlUp;
  const applyTemplateRows = (next: { lines: string[]; alignments: LineAlignment[]; wraps: boolean[] }) => {
    setTemplateInputStarted(true);
    setTemplateLines(next.lines);
    setLineAlignments(next.alignments);
    setLineWrapEnabled(next.wraps);
  };
  const wrapTemplateLine = (line: number) => {
    setLineWrapEnabled((previous) => {
      const next = [...previous];
      next[line - 1] = true;
      return next;
    });
  };
  const goToTemplateCell = ({ row, column }: { row: number; column: number }) => {
    const root = richTemplateContainerRef.current ?? plainTemplateContainerRef.current;
    if (root) focusTemplateCell(root, row, column);
    complexEditing.scrollToColumn(column);
  };

  // An unknown or deleted page id: say so, with the way back, instead of a
  // blank editor that would save a new page under that id (BB-B-16).
  if (initialPageId && pageLoadError instanceof ApiError && pageLoadError.status === 404) {
    return (
      <EmptyState
        icon={FileQuestion}
        title={t("pageNotFoundTitle")}
        description={t("pageNotFoundBody")}
        action={
          <Button variant="outline" onClick={onClose}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            {t("backToPages")}
          </Button>
        }
      />
    );
  }

  // After every hook above (the 2.9 lenses included), so a loading render
  // calls the same hooks as a loaded one.
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
    <FormulaIdeContext.Provider value={formulaIde.bridge}>
      <Box
        ref={editorContentRef}
        className="min-w-0 w-full max-w-full overflow-x-clip transition-none"
        style={viewportBottom > 0 ? { paddingBottom: viewportBottom, flexShrink: 0 } : undefined}
      >
        {/* Main Editor */}
        <Card
          className={cn(
            "flex flex-col min-h-0 w-full max-w-full overflow-x-clip gap-0 py-0",
            embedded && "rounded-none border-0 bg-transparent shadow-none",
          )}
        >
          <CardHeader
            className={cn(
              "sticky top-0 z-20 bg-background flex-shrink-0 gap-0 px-2 lg:px-4",
              // Docked: one fixed height, so the preview docks right under it.
              dockedPreview ? "h-16 py-1" : "h-14 lg:min-h-16 py-0",
            )}
          >
            <Flex align="center" className="h-full min-w-0 flex-nowrap gap-1.5">
              {/* The editor's own way back: the section draws no breadcrumb
                around it (BB-B-4, BB-B-19). "‹ Pages" on desktop (184:159319). */}
              {dockedPreview ? (
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-11 shrink-0"
                  onClick={onClose}
                  aria-label={t("backToPages")}
                >
                  <ArrowLeft className="size-4" />
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  className="h-11 shrink-0 gap-1 px-2"
                  onClick={onClose}
                  aria-label={t("backToPages")}
                >
                  <ChevronLeft className="size-4" aria-hidden="true" />
                  {tNav("pages")}
                </Button>
              )}
              <Box className={cn("relative min-w-0 flex-1", !dockedPreview && "h-11 lg:h-12")}>
                <label htmlFor="page-name" className="sr-only">
                  {t("pageNameLabel")}
                </label>
                <CardTitle className="sr-only">{name || (pageId ? t("editPage") : t("createPage"))}</CardTitle>
                {/* One field at every width, so focus survives a resize. Docked
                  (phone, tablet) the name wraps onto a second line beside Save
                  and Show now, with the save status under it (57:64661;
                  BB-B-3). It is one line of text: Enter finishes editing. */}
                <Textarea
                  id="page-name"
                  rows={dockedPreview ? 2 : 1}
                  wrap={dockedPreview ? "soft" : "off"}
                  value={name}
                  onChange={(event) => setName(event.target.value.replace(/[\r\n]+/g, " "))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      event.currentTarget.blur();
                    }
                  }}
                  // Show the name from its start again once editing ends.
                  onBlur={(event) => {
                    event.currentTarget.scrollTop = 0;
                    event.currentTarget.scrollLeft = 0;
                  }}
                  placeholder={t("pageNamePlaceholder")}
                  enterKeyHint="done"
                  className={cn(
                    "block min-h-0 w-full min-w-0 resize-none overflow-hidden rounded-none border-transparent bg-transparent font-semibold shadow-none",
                    dockedPreview
                      ? "max-h-[2lh] p-0 text-base leading-tight [field-sizing:content]"
                      : "h-11 lg:h-12 px-0 pt-0 pb-4 text-base lg:text-2xl",
                  )}
                />
                <Text
                  size="xs"
                  tone="muted"
                  className={cn(
                    "pointer-events-none truncate font-mono",
                    dockedPreview ? "block" : "absolute bottom-0 left-0",
                  )}
                >
                  {hasUnsavedChanges
                    ? tTouch("unsaved")
                    : savedAt
                      ? `${tTouch("saved")} ${savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
                      : ""}
                </Text>
              </Box>
              {!dockedPreview && (
                <Flex align="center" gap="1.5" className="hidden lg:flex shrink-0">
                  {secondaryActions}
                </Flex>
              )}
              {/* Keep the header popup mounted while compact More is closed.
                  Only its trigger hides; the kit portals the single controlled
                  popup and anchors it to the template for hardware `?`. */}
              <Box hidden={dockedPreview} className={dockedPreview ? "hidden" : "contents"}>
                <EditorShortcutList variant="header" {...shortcutListProps} />
              </Box>
              {saveActions ? (
                <Flex align="center" gap="1.5" className="shrink-0 flex-nowrap">
                  {saveActions({
                    save: requestSave,
                    saving: saveMutation.isPending,
                    disabled: saveMutation.isPending || stagingActive,
                    size: dockedPreview ? "touch" : "sm",
                    anchor: anchorProps("page-editor.save"),
                  })}
                </Flex>
              ) : (
                <TooltipProvider skipDelayDuration={0}>
                  <Flex align="center" gap="1.5" className="shrink-0 flex-nowrap">
                    {/* Save button */}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="secondary"
                          size={narrowHeader ? "icon-touch" : dockedPreview ? "touch" : "sm"}
                          className={cn("shrink-0 text-sm", !narrowHeader && "gap-1.5 px-3")}
                          {...anchorProps("page-editor.save")}
                          onClick={requestSave}
                          disabled={saveMutation.isPending || stagingActive}
                          aria-label={t("savePageAriaLabel")}
                        >
                          <Save className="h-3.5 w-3.5" />
                          {!narrowHeader && (saveMutation.isPending ? tCommon("saving") : t("savePage"))}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <Text>{t("savePageTooltip")}</Text>
                      </TooltipContent>
                    </Tooltip>
                    <Button
                      variant="brand"
                      size={dockedPreview ? "touch" : "sm"}
                      className="shrink-0 gap-1.5 px-3 text-sm"
                      disabled={saveMutation.isPending || stagingActive || !selectedBoardId}
                      onClick={() => requestShowNowRef.current()}
                    >
                      <Send className="size-4" />
                      {tTouch("showNow")}
                    </Button>
                  </Flex>
                </TooltipProvider>
              )}
            </Flex>
          </CardHeader>

          {/* Room for the fixed touch toolbar belongs at the end of the
            editor's scroll area (page-editor-shell), not here: the IDE's
            status row and Inspector follow, and 80px of it sat between them
            at every width (BB-B-29). Standalone, the builder keeps it. */}
          <CardContent className={cn("flex flex-col flex-1 min-h-0 px-0 lg:px-4 pt-0", embedded ? "pb-4" : "pb-20")}>
            <Box className="min-w-0">
              {/* Draft restored notification */}
              {draftRestored && (
                <Alert className="bg-info/10 border-info/20">
                  <AlertDescription className="text-sm">{t("draftRestored")}</AlertDescription>
                </Alert>
              )}

              {(pixelBoard || (!hintOnToolbar && !dockedPreview)) && (
                <Flex align="center" justify="between" gap="2" className="flex-wrap">
                  {pixelBoard && (
                    <Flex role="group" aria-label={t("editingSurfaceLabel")} className="rounded-lg border p-1" gap="1">
                      <Button
                        size="sm"
                        variant={editingSurface === "text" ? "secondary" : "ghost"}
                        aria-pressed={editingSurface === "text"}
                        onClick={() => setEditingSurface("text")}
                      >
                        {t("textMode")}
                      </Button>
                      <Button
                        size="sm"
                        variant={editingSurface === "canvases" ? "secondary" : "ghost"}
                        aria-pressed={editingSurface === "canvases"}
                        onClick={() => setEditingSurface("canvases")}
                      >
                        {t("canvasesMode")}
                      </Button>
                    </Flex>
                  )}
                  {/* At tablet widths or without a web toolbar, the hint sits above
                    the template instead of wrapping onto its own toolbar line (DD-W59). */}
                  {!hintOnToolbar && !dockedPreview && (
                    <Box className="ml-auto">
                      <EditorShortcutList variant="hint" {...shortcutListProps} />
                    </Box>
                  )}
                </Flex>
              )}
              {!useTouchToolbar && <Box ref={setToolbarContainer} className="min-w-0" />}
              {baselineDisplay && (
                <PlainTemplateToolbar
                  canUndo={plainHistory.canUndo}
                  canRedo={plainHistory.canRedo}
                  onUndo={() => plainTextRef.current?.undo()}
                  onRedo={() => plainTextRef.current?.redo()}
                  onInsert={(text) => plainTextRef.current?.insert(text)}
                  moreContent={mirrorMoreContent}
                />
              )}
              {/* Two equal columns, the same as the Creator IDE's below, so the
                Console sits under the template and the Inspector under the
                preview at one width (184:159319; BB-B-19). */}
              <Box className="grid min-w-0 grid-cols-1 lg:grid-cols-2 items-start gap-0 lg:gap-6">
                {/* Keep both surfaces mounted so switching preserves selection, undo and canvas tools. */}
                <Box
                  hidden={!!pixelBoard && editingSurface !== "text"}
                  className={cn("order-1 min-w-0 px-2 lg:px-0", formulaIde.rightSlot && "lg:row-span-2")}
                >
                  <Stack gap="3" className="min-w-0">
                    <Flex ref={templateHeadingRef} align="center" justify="between" className="order-2 lg:order-none">
                      <label htmlFor="page-template-plain" className="text-xs sm:text-sm font-medium">
                        {baselineDisplay ? tTouch("plainTemplate") : t("templateLabel")}
                      </label>
                      <Flex
                        align="center"
                        role="group"
                        aria-label={t("editorModeAriaLabel")}
                        className="border rounded-md overflow-hidden"
                      >
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditorModeChange("rich")}
                          className={`h-7 pointer-coarse:h-11 px-3 text-[11px] rounded-none ${editorMode === "rich" ? "bg-primary text-primary-foreground hover:bg-primary/85 hover:text-primary-foreground" : ""}`}
                          aria-label={t("richEditorAriaLabel")}
                          disabled={baselineDisplay}
                          aria-pressed={!baselineDisplay && editorMode === "rich"}
                        >
                          {t("richEditor")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditorModeChange("plain")}
                          className={`h-7 pointer-coarse:h-11 px-3 text-[11px] rounded-none ${editorMode === "plain" ? "bg-primary text-primary-foreground hover:bg-primary/85 hover:text-primary-foreground" : ""}`}
                          aria-label={t("plainTextAriaLabel")}
                          aria-pressed={baselineDisplay || editorMode === "plain"}
                        >
                          {t("plainEditor")}
                        </Button>
                      </Flex>
                    </Flex>
                    {complexEditing.active && (
                      <Suspense fallback={null}>
                        <ComplexTemplateHeader
                          complex={complexEditing}
                          editorRootRef={
                            editorMode === "rich" && !baselineDisplay
                              ? richTemplateContainerRef
                              : plainTemplateContainerRef
                          }
                          onGo={goToTemplateCell}
                        />
                      </Suspense>
                    )}
                    {editorMode === "rich" && !baselineDisplay ? (
                      <Box
                        ref={richTemplateContainerRef}
                        {...anchorProps("page-editor.template")}
                        className={cn("relative", rowBandsEnabled && "pl-38")}
                      >
                        {rowBandsEnabled && (
                          <Suspense fallback={null}>
                            <RowBandGutter
                              enabled
                              state={{ lines: templateLines, alignments: lineAlignments, wraps: lineWrapEnabled }}
                              rows={numLines}
                              editorRootRef={richTemplateContainerRef}
                              onChange={(next) => applyTemplateRows(next as Parameters<typeof applyTemplateRows>[0])}
                            />
                          </Suspense>
                        )}
                        {newPageEmpty && (
                          <Text
                            aria-hidden
                            className="pointer-events-none absolute left-12 top-2 z-10 font-mono text-sm text-muted-foreground"
                          >
                            {tTouch("emptyPrompt", { board: previewBoard?.name ?? tTouch("thisDisplay") })}
                          </Text>
                        )}
                        {/* Template editor with device-specific dimensions */}
                        <Suspense fallback={<Skeleton className="h-48 w-full rounded-md" />}>
                          {editorCharset ? (
                            // An LED target: its own character set decides what the
                            // editor reads, offers and keeps (spans, icons, case).
                            // No draw mode — it paints flap tiles.
                            <CharsetTemplateEditor
                              canvasRegions={pixelBoard ? canvases : undefined}
                              onCanvasActivate={(id) => {
                                setEditingSurface("canvases");
                                canvasesPanelRef.current?.activateCanvas(id);
                              }}
                              moreContent={mirrorMoreContent}
                              charset={editorCharset}
                              value={newPageEmpty ? "" : templateLines.join("\n")}
                              onChange={handleRichEditorChange}
                              lineAlignments={lineAlignments}
                              lineWrapEnabled={lineWrapEnabled}
                              onLineAlignmentChange={(lineIndex, alignment) => {
                                setLineAlignments((prev) => {
                                  const next = [...prev];
                                  next[lineIndex] = alignment;
                                  return next;
                                });
                              }}
                              onLineWrapChange={(lineIndex, wrapEnabled) => {
                                setLineWrapEnabled((prev) => {
                                  const next = [...prev];
                                  next[lineIndex] = wrapEnabled;
                                  return next;
                                });
                              }}
                              placeholder={
                                newPageEmpty
                                  ? tTouch("emptyPrompt", { board: previewBoard?.name ?? tTouch("thisDisplay") })
                                  : t("richEditorPlaceholder")
                              }
                              boardWidth={dims.cols}
                              boardLines={numLines}
                              deviceType={deviceType}
                              code62Glyph={effectiveCode62Glyph}
                              onSyncFromBoard={!pageId ? () => syncFromBoardMutation.mutate() : undefined}
                              syncFromBoardPending={syncFromBoardMutation.isPending}
                            />
                          ) : (
                            <TipTapTemplateEditor
                              ref={tipTapRef}
                              scrollMargin={caretScrollMargin}
                              value={newPageEmpty ? "" : templateLines.join("\n")}
                              onChange={handleRichEditorChange}
                              lineAlignments={lineAlignments}
                              lineWrapEnabled={lineWrapEnabled}
                              onLineAlignmentChange={(lineIndex, alignment) => {
                                setLineAlignments((prev) => {
                                  const newAlignments = [...prev];
                                  newAlignments[lineIndex] = alignment;
                                  return newAlignments;
                                });
                              }}
                              onLineWrapChange={(lineIndex, wrapEnabled) => {
                                setLineWrapEnabled((prev) => {
                                  const newWrapStates = [...prev];
                                  newWrapStates[lineIndex] = wrapEnabled;
                                  return newWrapStates;
                                });
                              }}
                              placeholder={
                                newPageEmpty
                                  ? tTouch("emptyPrompt", { board: previewBoard?.name ?? tTouch("thisDisplay") })
                                  : t("richEditorPlaceholder")
                              }
                              showAlignmentControls={true}
                              showToolbar={true}
                              boardWidth={dims.cols}
                              boardLines={numLines}
                              deviceType={deviceType}
                              code62Glyph={effectiveCode62Glyph}
                              onSyncFromBoard={!pageId ? () => syncFromBoardMutation.mutate() : undefined}
                              syncFromBoardPending={syncFromBoardMutation.isPending}
                              drawMode={drawMode}
                              onDrawModeToggle={() => setDrawMode((v) => !v)}
                              drawBrush={drawBrush}
                              onDrawBrushChange={setDrawBrush}
                              onDrawHistoryEvent={handleDrawHistoryEvent}
                              toolbarContainer={toolbarContainer}
                              toolbarMoreContent={mirrorMoreContent}
                              toolbarTrailing={
                                hintOnToolbar ? <EditorShortcutList variant="hint" {...shortcutListProps} /> : undefined
                              }
                            />
                          )}
                        </Suspense>
                      </Box>
                    ) : (
                      <Box ref={plainTemplateContainerRef} {...anchorProps("page-editor.template")}>
                        <PlainTextEditor
                          ref={plainTextRef}
                          onHistoryChange={setPlainHistory}
                          id="page-template-plain"
                          lineMarkers={pixelBoard ? canvasMarkers(canvases, numLines) : undefined}
                          lineMarkerTitle={tCanvas("markerTitle")}
                          value={newPageEmpty ? "" : templateLines.join("\n")}
                          onChange={(newValue) => {
                            setTemplateInputStarted(true);
                            setTemplateLines(newValue.split("\n"));
                          }}
                          placeholder={
                            newPageEmpty
                              ? tTouch("emptyPrompt", { board: previewBoard?.name ?? tTouch("thisDisplay") })
                              : t("plainEditorPlaceholder")
                          }
                          boardLines={numLines}
                          boardWidth={dims.cols}
                          help={
                            baselineDisplay ? (
                              <Text size="xs" tone="muted">
                                {tTouch("plainTemplateHelp")}
                              </Text>
                            ) : undefined
                          }
                        />
                      </Box>
                    )}
                    {newPageEmpty && (
                      <Stack gap="2">
                        {!dockedPreview && (
                          <Text size="sm" tone="muted">
                            {tTouch("startFrom")}
                          </Text>
                        )}
                        <Flex gap="2" className="flex-col lg:flex-row lg:flex-wrap">
                          <PlainTemplateVariablePicker
                            trigger={
                              <Button variant="outline" size={dockedPreview ? "touch" : "sm"}>
                                <Variable />
                                {tTouch("insertVariable")}
                              </Button>
                            }
                            onInsert={(text) => {
                              if (baselineDisplay || editorMode === "plain") plainTextRef.current?.insert(text);
                              else {
                                setTemplateInputStarted(true);
                                setTemplateLines([text]);
                                requestAnimationFrame(() => {
                                  richTemplateContainerRef.current
                                    ?.querySelector<HTMLElement>('[contenteditable="true"]')
                                    ?.focus();
                                });
                              }
                            }}
                          />
                          <Button asChild variant="outline" size={dockedPreview ? "touch" : "sm"}>
                            <TextLink href={appUrl("/picks")} className="text-foreground no-underline">
                              <Sparkles />
                              {tTouch("browseStaffPicks")}
                            </TextLink>
                          </Button>
                        </Flex>
                      </Stack>
                    )}

                    {/* Line count warning, only where the editor's own caption is
                    replaced; elsewhere the caption already says it (BB-E-10). */}
                    {lineCount > numLines && baselineDisplay && (
                      <Flex
                        align="start"
                        gap="2"
                        className="rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-warning"
                      >
                        <Text as="span" size="xs" weight="medium" tone="warning" className="shrink-0">
                          {t("warningLabel")}
                        </Text>
                        <Text as="span" size="xs" tone="warning">
                          {t("lineCountWarning", { lineCount, maxLines: numLines })}
                        </Text>
                      </Flex>
                    )}

                    {/* Wrap budget warnings */}
                    {wrapBudgetWarnings.map((lineNumber) => (
                      <Flex
                        key={`wrap-budget-${lineNumber}`}
                        align="start"
                        gap="2"
                        className="rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-warning"
                      >
                        <Text as="span" size="xs" weight="medium" tone="warning" className="shrink-0">
                          {t("warningLabel")}
                        </Text>
                        <Text as="span" size="xs" tone="warning">
                          {t("wrapBudgetWarning", { lineNumber })}
                        </Text>
                      </Flex>
                    ))}

                    {/* Cells the target board's character set draws differently
                    (the server's charset_issues for the rendered page). */}
                    {charsetIssues.length > 0 && (
                      <Flex
                        align="start"
                        gap="2"
                        data-testid="charset-issues"
                        className="rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-warning"
                      >
                        <Text as="span" size="xs" weight="medium" tone="warning" className="shrink-0">
                          {t("warningLabel")}
                        </Text>
                        <Stack gap="1">
                          {charsetIssues.slice(0, MAX_CHARSET_ISSUES_SHOWN).map((issue) => (
                            <Text as="span" size="xs" tone="warning" key={`${issue.row}-${issue.col}`}>
                              {t("charsetIssue", {
                                line: issue.row + 1,
                                column: issue.col + 1,
                                written: charsetTokenText(issue.token),
                                shown: charsetTokenText(issue.fallback),
                              })}
                            </Text>
                          ))}
                          {charsetIssues.length > MAX_CHARSET_ISSUES_SHOWN && (
                            <Text as="span" size="xs" tone="warning">
                              {t("charsetIssuesMore", { count: charsetIssues.length - MAX_CHARSET_ISSUES_SHOWN })}
                            </Text>
                          )}
                        </Stack>
                      </Flex>
                    )}

                    {/* H4: lines the hub measured past the board's real width. */}
                    <LineOverflowWarnings
                      overflows={lineOverflow.overflows}
                      boardName={previewBoard?.name}
                      checkedAt={lineOverflow.checkedAt}
                      touch={useTouchToolbar}
                      wrapped={lineWrapEnabled}
                      onWrap={wrapTemplateLine}
                    />
                    {complexEditing.noteArray && (
                      <Suspense fallback={null}>
                        <NoteSeamSummary straddles={straddles} />
                      </Suspense>
                    )}
                    {formulaIde.leftSlot}
                  </Stack>
                </Box>

                {/* Preview is shared by both modes; the dock stays visible below 1024 px. */}
                <EditorPreview
                  ref={dockPreviewRef}
                  id="page-editor-preview"
                  variant={dockedPreview ? "docked" : "pane"}
                  className={cn(
                    "order-first lg:order-2 min-w-0",
                    dockedPreview ? "top-16 scroll-mt-16 px-0" : "top-16 scroll-mt-16",
                    // A landscape phone has no height for a docked board: it
                    // scrolls with the template instead (BB-B-4).
                    dockedPreview && "[@media(max-height:500px)]:static",
                  )}
                  title={baselineDisplay ? tTouch("plainText") : (formulaIde.previewTitle ?? tTouch("livePreview"))}
                  dotStatus={baselineDisplay ? "warning" : (formulaIde.dotStatus ?? "success")}
                  boardName={previewBoard?.name}
                  live={liveOutputEnabled}
                  onLiveChange={changeMirroring}
                  liveDisabled={(mirrorUnavailable && !liveOutputEnabled) || formulaIde.mirrorLocked}
                  liveLabel={tTouch("mirror")}
                  mirroringLabel={tTouch("mirroring")}
                  statusLine={
                    mirrorUnavailable
                      ? tTouch("targetUnavailable")
                      : liveOutputEnabled
                        ? tTouch("mirrorHint")
                        : undefined
                  }
                  headerAction={
                    <Flex align="center" gap="1" wrap className="justify-end">
                      {formulaIde.headerControls}
                      {!baselineDisplay && complexEditing.bigBoard && (
                        <Suspense fallback={null}>
                          <BigBoardZoom complex={complexEditing} minimapId={complexMinimapId} />
                        </Suspense>
                      )}
                      {!baselineDisplay && !complexEditing.bigBoard && (
                        <BoardPreviewModeToggle
                          mode={previewMode}
                          onModeChange={changePreviewMode}
                          size={dockedPreview ? "touch" : "default"}
                          labels={{
                            previewSize: tBoardDisplay("previewSizeLabel"),
                            fit: tBoardDisplay("fitMode"),
                            actual: tBoardDisplay("actualMode"),
                          }}
                        />
                      )}
                      {dockedPreview &&
                        !baselineDisplay &&
                        (editorMode === "plain" || !useTouchToolbar) &&
                        (sheetPickers ? (
                          <ToolbarDropdown
                            label={tToolbar("more")}
                            icon={<Ellipsis />}
                            size="touch"
                            presentation="sheet"
                          >
                            {mirrorMoreContent}
                          </ToolbarDropdown>
                        ) : (
                          <EditorAnchoredTool label={tToolbar("more")} icon={<Ellipsis />}>
                            {() => mirrorMoreContent}
                          </EditorAnchoredTool>
                        ))}
                    </Flex>
                  }
                >
                  {formulaIde.bodyControls}
                  {complexEditing.bigBoard && (
                    <Suspense fallback={null}>
                      <ComplexPreviewRuler complex={complexEditing} />
                    </Suspense>
                  )}
                  {/* One stage element serves 2.9's lenses (previewStage) and 2.10's Inspect (board ref). */}
                  <Flex
                    justify="center"
                    {...formulaIde.boardProps}
                    ref={setPreviewStageElement}
                    className={cn("relative min-w-0", formulaIde.boardProps.className)}
                  >
                    {formulaIde.boardOverlay}
                    {/* H4: where the board cuts a line (BB-E-10, 307:41698). */}
                    {!drawMode && !baselineDisplay && (
                      <PreviewCutMarkers
                        stage={previewStage}
                        overflows={lineOverflow.overflows}
                        rows={dims.rows}
                        cols={dims.cols}
                        wrapped={lineWrapEnabled}
                      />
                    )}
                    {baselineDisplay ? (
                      <Alert variant="warning" className="w-full">
                        <AlertDescription>
                          <Stack gap="2">
                            <Text weight="semibold">{tTouch("unknownDisplay")}</Text>
                            <Text>{tTouch("plainTextOnly")}</Text>
                            <Box className="rounded-lg border bg-background p-3">
                              <Text className="whitespace-pre-wrap font-mono">{editorPreviewMessage}</Text>
                            </Box>
                          </Stack>
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <DrawableBoardPreview
                        active={drawMode}
                        onStrokePreview={setStrokePreviewCells}
                        onStrokeCommit={handleStrokeCommit}
                      >
                        {/* An LED target board previews as its LED matrix; draw
                          mode hit-tests flap tiles, so it stays on the flaps. */}
                        <DevicePreview
                          model={drawMode ? null : previewModel}
                          ledLayout={previewBoard?.led_layout}
                          layers={drawMode ? undefined : previewLayers}
                          message={shownPreviewMessage}
                          size={dockedPreview ? "sm" : "md"}
                        >
                          <ScaledBoardDisplay
                            message={shownPreviewMessage}
                            isLoading={
                              drawMode
                                ? false
                                : (() => {
                                    const hasContent = debouncedTemplateLines.some((line) => line.trim().length > 0);
                                    const isPending = previewMutation.isPending;
                                    const shouldIgnore = shouldIgnoreNextResponse.current;

                                    if (isTransitioning) return true;
                                    if (preview !== null) return false;
                                    if (!hasContent) return false;
                                    if (shouldIgnore) return false;
                                    return isPending && hasContent;
                                  })()
                            }
                            isStatic={drawMode}
                            size={complexEditing.bigBoard ? complexEditing.previewSize : dockedPreview ? "sm" : "md"}
                            // Hero layouts settle a board that overflows by a
                            // little into the pane (tiles stay >= 13 px): a
                            // Flagship shows whole, Den TV still scrolls (BB-B-11).
                            layout={dockedPreview ? "phone-hero" : "medium-hero"}
                            mode={complexEditing.bigBoard ? complexEditing.previewMode : previewMode}
                            onModeChange={
                              complexEditing.bigBoard
                                ? (mode) => complexEditing.setZoom(mode === "fit" ? "fit" : "sm")
                                : changePreviewMode
                            }
                            showModeToggle={false}
                            boardType={effectiveBoardColor}
                            deviceType={deviceType}
                            code62Glyph={effectiveCode62Glyph}
                            notesWide={notesWide}
                            notesTall={notesTall}
                            gridRows={panelGrid?.rows}
                            gridCols={panelGrid?.cols}
                            // DrawableBoardPreview hit-tests strokes through the
                            // tiles' data-row/data-col attributes; only this
                            // editor preview opts into emitting them.
                            emitCellMetadata
                          />
                        </DevicePreview>
                      </DrawableBoardPreview>
                    )}
                    {complexEditing.noteArray && (
                      <Suspense fallback={null}>
                        <ComplexPreviewSeams complex={complexEditing} />
                      </Suspense>
                    )}
                  </Flex>
                  {complexEditing.bigBoard && (
                    <Suspense fallback={null}>
                      <ComplexPreviewOverview
                        complex={complexEditing}
                        board={{
                          message: shownPreviewMessage,
                          boardType: effectiveBoardColor,
                          deviceType,
                          code62Glyph: effectiveCode62Glyph,
                          notesWide,
                          notesTall,
                          gridRows: panelGrid?.rows,
                          gridCols: panelGrid?.cols,
                        }}
                        rendered={renderedRows}
                        overflows={lineOverflow.overflows}
                        minimapId={complexMinimapId}
                        onJump={goToTemplateCell}
                      />
                    </Suspense>
                  )}
                  {drawMode && (
                    <Text tone="muted" size="xs" className="mt-1 text-center">
                      {t("drawModeHint")}
                    </Text>
                  )}

                  {boardSettings?.boards && boardSettings.boards.length > 1 && (
                    <Select value={selectedBoardId} onValueChange={setChosenLiveBoardId}>
                      <SelectTrigger aria-label={t("selectBoardAriaLabel")}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {boardSettings.boards.map((board) => (
                          <SelectItem key={board.id} value={board.id}>
                            {board.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  {liveTargetPaused && (
                    <Alert id="live-output-paused-notice" className="mt-2">
                      <AlertDescription>{t("livePausedNotice")}</AlertDescription>
                    </Alert>
                  )}
                  <LiveOutputSilenceStrip
                    liveOutputEnabled={liveOutputEnabled}
                    lastSilenced={liveSilenced}
                    silenceActive={liveSilence.active || liveSilenced}
                    overriding={liveOverrideSilence}
                    until={liveSilence.until}
                    onSendAnyway={() => setLiveOverrideSilence(true)}
                    onStopOverriding={() => setLiveOverrideSilence(false)}
                  />
                  {formulaIde.previewFooter}
                </EditorPreview>
                {formulaIde.rightSlot && <Box className="order-2 min-w-0 lg:col-start-2">{formulaIde.rightSlot}</Box>}
                <Box className="order-3 min-w-0 px-2 lg:px-0 lg:col-start-1">
                  <Flex align="center" justify="between" className="flex-wrap gap-y-2 mb-2">
                    <Flex align="center" gap="2" className="flex-wrap">
                      <label className="text-xs sm:text-sm font-medium">{t("previewLabel")}</label>
                      <BoardSizeIndicator
                        deviceType={deviceType}
                        notesWide={notesWide}
                        notesTall={notesTall}
                        gridRows={gridRows}
                        gridCols={gridCols}
                        className="ml-1"
                      />
                      <PanelFitNote
                        deviceType={deviceType}
                        notesWide={notesWide}
                        notesTall={notesTall}
                        gridRows={gridRows}
                        gridCols={gridCols}
                      />
                      {/* Device/size retarget (issue #1250): both new AND saved
                          pages can change board size. Converting a saved page is
                          lossy (shrinks truncate), so saving a shrinking retarget
                          asks for confirmation first. */}
                      <Select value={sizeSelectValue} onValueChange={handleSizeChange}>
                        <SelectTrigger
                          {...anchorProps("page-editor.device")}
                          className="h-7 pointer-coarse:h-11 w-auto gap-1 px-2 text-xs"
                          aria-label={t("deviceTypeSwitcherAriaLabel")}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {/* FiestaPanels first: a panel's grid is auto-fit from
                              its TV size, so nobody can pick it out of the
                              generic Notes-wide/tall selects below. Absent on an
                              install with no panels, leaving the picker exactly
                              the three sizes it has always been. */}
                          {fiestaPanelTargets.length > 0 && (
                            <SelectGroup>
                              <SelectLabel>{tPanels("yourPanelsGroupLabel")}</SelectLabel>
                              {fiestaPanelTargets.map((panel) => (
                                <SelectItem key={panel.id} value={targetValue(panel)} className="text-xs">
                                  {tPanels("panelSizeOption", {
                                    name: panel.name,
                                    cols: panel.cols,
                                    rows: panel.rows,
                                  })}
                                </SelectItem>
                              ))}
                            </SelectGroup>
                          )}
                          {/* Every other display with a custom grid — an output
                              plugin's board, such as an LED matrix — named for
                              its board and model, so a page can be authored
                              for it. Driven by the board list alone. */}
                          {otherDisplayTargets.length > 0 && (
                            <SelectGroup>
                              <SelectLabel>{tPanels("yourDisplaysGroupLabel")}</SelectLabel>
                              {otherDisplayTargets.map((display) => (
                                <SelectItem key={display.id} value={targetValue(display)} className="text-xs">
                                  {tPanels(
                                    display.modelLabel
                                      ? display.led
                                        ? "displaySizeOptionLed"
                                        : "displaySizeOption"
                                      : "panelSizeOption",
                                    {
                                      name: display.name,
                                      model: display.modelLabel ?? "",
                                      cols: display.cols,
                                      rows: display.rows,
                                    },
                                  )}
                                </SelectItem>
                              ))}
                            </SelectGroup>
                          )}
                          <SelectItem value="flagship" className="text-xs">
                            {tDisplaySettings("flagshipLabel")}
                          </SelectItem>
                          <SelectItem value="note" className="text-xs">
                            {tDisplaySettings("noteLabel")}
                          </SelectItem>
                          <SelectItem value="note_array" className="text-xs">
                            {tDisplaySettings("noteArrayLabel")}
                          </SelectItem>
                          {/* A panel page no listed panel matches: still named,
                              at its own grid, so the trigger never goes blank. */}
                          {sizeSelectValue === "panel" && (
                            <SelectItem value="panel" className="text-xs">
                              {tPanels("panelGridOption", { cols: dims.cols, rows: dims.rows })}
                            </SelectItem>
                          )}
                        </SelectContent>
                      </Select>
                      {deviceType === "note_array" && (
                        <>
                          <Select value={String(notesWide)} onValueChange={(v) => setNotesWide(Number(v))}>
                            <SelectTrigger
                              className="h-7 pointer-coarse:h-11 w-auto gap-1 px-2 text-xs"
                              aria-label={tDisplaySettings("notesWideLabel")}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {NOTE_AXIS_OPTIONS.map((n) => (
                                <SelectItem key={`w-${n}`} value={String(n)} className="text-xs">
                                  {t("notesWideOption", { count: n })}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Select value={String(notesTall)} onValueChange={(v) => setNotesTall(Number(v))}>
                            <SelectTrigger
                              className="h-7 pointer-coarse:h-11 w-auto gap-1 px-2 text-xs"
                              aria-label={tDisplaySettings("notesTallLabel")}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {NOTE_AXIS_OPTIONS.map((n) => (
                                <SelectItem key={`t-${n}`} value={String(n)} className="text-xs">
                                  {t("notesTallOption", { count: n })}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </>
                      )}
                    </Flex>
                    <Flex align="center" gap="1.5" className="shrink-0">
                      <Text as="span" size="xs" tone="muted" className="mr-0.5">
                        {t("boardColorLabel")}
                      </Text>
                      <button
                        onClick={() => setPreviewBoardColor("black")}
                        aria-label={t("previewAsBlack")}
                        aria-pressed={effectiveBoardColor === "black"}
                        className={`h-5 w-5 pointer-coarse:size-11 rounded-full border-2 bg-board-surface-dark transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                          effectiveBoardColor === "black"
                            ? "border-primary ring-1 ring-primary/30"
                            : "border-border hover:border-muted-foreground"
                        }`}
                      />
                      <button
                        onClick={() => setPreviewBoardColor("white")}
                        aria-label={t("previewAsWhite")}
                        aria-pressed={effectiveBoardColor === "white"}
                        className={`h-5 w-5 pointer-coarse:size-11 rounded-full border-2 bg-board-surface-light transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                          effectiveBoardColor === "white"
                            ? "border-primary ring-1 ring-primary/30"
                            : "border-border hover:border-muted-foreground"
                        }`}
                      />
                    </Flex>
                  </Flex>
                </Box>

                {/* Pixel canvases: edited for an LED pixel board; on any other
                    board a page that has them says why their areas are blank. */}
                {pixelBoard ? (
                  <Box hidden={editingSurface !== "canvases"} className="order-1 min-w-0">
                    <CanvasesPanel
                      ref={canvasesPanelRef}
                      canvases={canvases}
                      onChange={setCanvases}
                      gridRows={dims.rows}
                      gridCols={dims.cols}
                      board={pixelBoard}
                      issues={canvasIssues}
                      error={canvasError}
                    />
                  </Box>
                ) : (
                  canvases.length > 0 && (
                    <Alert data-testid="canvas-not-pixel-notice">
                      <AlertDescription>{tCanvas("notPixelNotice")}</AlertDescription>
                    </Alert>
                  )
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Box>

      <ChangePageDialog
        open={showPageId !== null}
        onOpenChange={(open) => {
          if (!open) setShowPageId(null);
        }}
        initialPageId={showPageId}
        board={boardSettings?.boards?.find((board) => board.id === selectedBoardId)}
        isPrimary={boardSettings?.boards?.[0]?.id === selectedBoardId}
        scheduleEnabled={targetDetail?.schedule_enabled ?? previewBoard?.schedule_enabled ?? false}
        nextChange={scheduleNextChange(targetDetail, new Date())}
        silence={liveSilence.active ? { until: liveSilence.until } : null}
      />
      {/* Export dialog */}
      <Dialog open={exportOpen} onOpenChange={setExportOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("exportDialogTitle")}</DialogTitle>
            <DialogDescription>{t("exportDialogDescription")}</DialogDescription>
          </DialogHeader>
          <Box className="relative">
            <Textarea
              readOnly
              value={exportShareString}
              aria-label={t("exportStringAriaLabel")}
              className="h-28 pr-10 text-xs font-mono bg-muted resize-none"
              onFocus={(e) => e.target.select()}
            />
            <CopyButton
              value={exportShareString}
              size="icon-sm"
              labels={{ copy: t("exportCopyAriaLabel") }}
              className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
            />
          </Box>
        </DialogContent>
      </Dialog>

      {/* Shrinking-retarget confirmation (issue #1250). Conversion between
          geometries is lossy: content that doesn't fit the smaller board is
          cut off, so the save is gated behind an explicit confirm. */}
      <AlertDialog
        open={confirmRetargetOpen}
        onOpenChange={(open) => {
          setConfirmRetargetOpen(open);
          if (!open) showAfterSaveRef.current = false;
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("retargetConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("retargetConfirmDescription", {
                oldSize: originalDims ? `${originalDims.rows} × ${originalDims.cols}` : "",
                newSize: `${dims.rows} × ${dims.cols}`,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmRetargetOpen(false);
                saveMutation.mutate({ showRequested: showAfterSaveRef.current });
              }}
            >
              {t("retargetConfirmAction")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {formulaIde.overlays}
    </FormulaIdeContext.Provider>
  );
});
PageBuilder.displayName = "PageBuilder";
