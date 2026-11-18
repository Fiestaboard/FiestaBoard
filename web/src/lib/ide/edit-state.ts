import type { EditState, PreviewDisplayState } from "@fiestaboard/ui";

export interface EditStateInput {
  /** The editor holds edits that neither the page nor its hub draft has. */
  unsaved: boolean;
  /** The page has a hub draft (H9a) that no board shows. */
  hasDraft: boolean;
  /** Mirror to board is on, so a board shows the edits being made. */
  mirroring: boolean;
}

/**
 * The status-row chip (C29), derived per the IDE rulings: Testing while the
 * edits are mirrored to a board, Unsaved for edits nowhere else, Draft when
 * the hub holds a draft the board does not show, else Saved.
 */
export function deriveEditState({ unsaved, hasDraft, mirroring }: EditStateInput): EditState {
  if (mirroring) return "testing";
  if (unsaved) return "unsaved";
  if (hasDraft) return "draft";
  return "saved";
}

/** Live when a board shows the page now; Scheduled when a schedule or collection will; else Not scheduled. */
export function derivePreviewDisplay(showingNow: boolean, scheduled: boolean): PreviewDisplayState {
  if (showingNow) return "live";
  return scheduled ? "scheduled" : "not-scheduled";
}

/**
 * Header actions while a display shows the page (04d decision 4): Save draft
 * keeps the board on the published version; Save & update board publishes.
 */
export function offersDraft(display: PreviewDisplayState): boolean {
  return display !== "not-scheduled";
}
