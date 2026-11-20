/**
 * Renders the preview-target controls inline, without the popover around them
 * (BB-E-6 moved them behind the preview header's meta). For suites that test
 * what those controls do (size retargets, the live-output board, colour), not
 * how they are reached; `page-builder-preview-card.test.tsx` covers the popover.
 *
 *   vi.mock("@/components/preview-target-popover", () => import("./mocks/preview-target-popover-inline"));
 */
import type { PreviewTargetPopoverProps } from "@/components/preview-target-popover";

export function PreviewTargetPopover({ children }: PreviewTargetPopoverProps) {
  return <div data-testid="preview-target-inline">{children}</div>;
}
