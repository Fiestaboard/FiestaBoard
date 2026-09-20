"use client";

import { Flex, Stack } from "@fiestaboard/ui";
import { useEffect, useRef } from "react";

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
export function PageEditorShell({ pageId, deviceType, skipDraft, onClose, onSave }: PageEditorShellProps) {
  const builderRef = useRef<PageBuilderHandle>(null);
  const { register, unregister } = usePageEditorBridge();

  const call = <K extends keyof PageBuilderHandle>(key: K): PageBuilderHandle[K] | undefined =>
    builderRef.current?.[key];

  useEffect(() => {
    register({
      getSnapshot: () => call("getCurrentPage")?.() ?? null,
      getPageId: () => pageId,
      hasUnsavedChanges: () => call("hasUnsavedChanges")?.() ?? false,
      beginStaging: () => call("beginStaging")?.(),
      stageName: (value) => call("stageName")?.(value),
      stageLine: (index, value) => call("stageLine")?.(index, value),
      stageDeviceType: (value) => call("stageDeviceType")?.(value),
      discardStaging: () => call("discardStaging")?.(),
      reloadFromServer: () => call("reloadFromServer")?.() ?? Promise.resolve(),
    });
    return () => unregister();
  }, [register, unregister, pageId]);

  return (
    <Flex className="flex-1 min-h-0 w-full overflow-hidden bg-background">
      <Stack className="h-full w-full min-w-0 flex-1 overflow-y-auto bg-background px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 lg:py-3">
        <PageBuilder
          ref={builderRef}
          pageId={pageId}
          deviceType={deviceType}
          skipDraft={skipDraft}
          onClose={onClose}
          onSave={onSave}
        />
      </Stack>
    </Flex>
  );
}
