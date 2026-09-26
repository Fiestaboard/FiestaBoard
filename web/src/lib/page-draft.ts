// The localStorage key the page editor autosaves an unsaved draft under.
//
// Lives outside page-builder.tsx so the always-mounted AI drawer can drop
// the draft after the assistant turns it into a real page without pulling
// the whole editor into the initial bundle.
export function getDraftKey(pageId?: string): string {
  return `fiestaboard-page-draft-${pageId || "new"}`;
}
