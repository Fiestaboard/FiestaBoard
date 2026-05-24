"use client";

import {
  useCallback,
  useEffect,
  useRef,
} from "react";

import { PageBuilder, type PageBuilderHandle } from "@/components/page-builder";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import type { DeviceType } from "@/lib/api";

export interface PageEditorShellProps {
  pageId?: string;
  /** Device type for new pages (ignored when pageId is set). */
  deviceType?: DeviceType;
  /** If true, ignore and clear any saved draft for a new page. */
  skipDraft?: boolean;
  onClose: () => void;
  onSave: () => void;
}

/**
 * Hosts the page builder and registers it with the global AI panel bridge
 * so the AI assistant can read and edit the current page from anywhere
 * in the app.
 */
export function PageEditorShell({
  pageId,
  deviceType,
  skipDraft,
  onClose,
  onSave,
}: PageEditorShellProps) {
  const builderRef = useRef<PageBuilderHandle>(null);
  const { register, unregister } = usePageEditorBridge();

  const getSnapshot = useCallback(
    () => builderRef.current?.getCurrentPage() ?? null,
    [],
  );

  const applyOp = useCallback(
    (call: Parameters<NonNullable<PageBuilderHandle["applyToolCall"]>>[0]) => {
      builderRef.current?.applyToolCall(call);
    },
    [],
  );

  const getCanUndo = useCallback(
    () => builderRef.current?.canUndo() ?? false,
    [],
  );

  const undo = useCallback(() => {
    builderRef.current?.undo();
  }, []);

  const save = useCallback(
    () => builderRef.current?.save() ?? Promise.resolve(null),
    [],
  );

  useEffect(() => {
    register({ getSnapshot, applyOp, save, getCanUndo, undo });
    return () => unregister();
  }, [register, unregister, getSnapshot, applyOp, save, getCanUndo, undo]);

  return (
    <div className="flex flex-1 min-h-0 w-full overflow-hidden bg-background">
      <div className="flex h-full w-full min-w-0 flex-1 flex-col overflow-y-auto bg-background px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 lg:py-3">
        <PageBuilder
          ref={builderRef}
          pageId={pageId}
          deviceType={deviceType}
          skipDraft={skipDraft}
          onClose={onClose}
          onSave={onSave}
        />
      </div>
    </div>
  );
}
