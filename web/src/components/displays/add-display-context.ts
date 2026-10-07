import { createContext, useContext } from "react";

import type { WizardOutputChoice } from "@/components/wizard/step-output-plugin";

/**
 * Opens the add-a-display flow: from its first step, or at one display's
 * setup (a Marketplace card). The flow belongs to the Displays section
 * (app/routes/displays.tsx), which owns the header's "Add a display" button and
 * the dialog, so the list asks for it here rather than mounting a second
 * dialog of its own.
 */
export const AddDisplayContext = createContext<(output?: WizardOutputChoice) => void>(() => {});

export function useAddDisplay() {
  return useContext(AddDisplayContext);
}
