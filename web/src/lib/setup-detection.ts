/**
 * Setup detection utilities for the FiestaBoard onboarding wizard.
 *
 * Detects first-run state, manages wizard completion status,
 * and provides utilities for the setup flow.
 */

import type { Code62Glyph, ConfigValidationResponse } from "./api";
import { api } from "./api";

const WIZARD_COMPLETE_KEY = "fiestaboard_wizard_complete";
const WIZARD_PROGRESS_KEY = "fiestaboard_wizard_progress";

export interface WizardProgress {
  currentStep: number;
  /**
   * The output chosen on the first step (plan D18). Absent in progress saved
   * by the three-step, Vestaboard-only wizard; see {@link getWizardProgress}.
   */
  outputId?: string;
  /** Its display name, for the step titles after a reload. */
  outputName?: string;
  /** The board the wizard created for a TV or an output plugin. */
  createdBoard?: {
    outputId: string;
    boardId: string;
    name: string;
    viewerPath?: string;
  };
  boardConfig?: {
    /** The Vestaboard's connection as its settings screen edits it (the board's `output_config`). */
    output_config?: Record<string, unknown>;
    /** Progress saved before the step moved onto the settings screen kept the connection flat. */
    api_mode?: "local" | "cloud";
    local_api_key?: string;
    cloud_key?: string;
    host?: string;
    device_type?: "flagship" | "note";
    board_color?: "black" | "white";
    /** Which flap this Flagship's code-62 slot carries (issue #1657). */
    code62_glyph?: Code62Glyph;
  };
  plugins?: {
    date_time?: {
      enabled: boolean;
      timezone: string;
    };
    star_trek_quotes?: {
      enabled: boolean;
      ratio: string;
    };
    guest_wifi?: {
      enabled: boolean;
      ssid: string;
      password: string;
    };
  };
}

/**
 * Check if the setup wizard needs to be shown.
 * Returns true if:
 * - Config validation fails (first run)
 * - Wizard has never been completed
 *
 * @returns Promise resolving to whether wizard should show
 */
export async function shouldShowWizard(): Promise<boolean> {
  try {
    const validation = await api.validateSetup();

    // If first run (missing board config), always show wizard.
    // Server truth wins — localStorage completion flag from a previous Pi
    // must not suppress the wizard on a fresh device.
    if (validation.is_first_run) {
      return true;
    }

    // If config is invalid, show wizard
    if (!validation.valid) {
      // But check if user has previously completed wizard and explicitly skipped
      // In that case, don't auto-show (user can manually trigger)
      if (isWizardCompleted()) {
        return false;
      }
      return true;
    }

    return false;
  } catch (error) {
    console.error("Failed to check setup status:", error);
    // If we can't reach the API, don't show wizard (might be network issue)
    return false;
  }
}

/**
 * Get detailed setup validation status.
 */
export async function getSetupStatus(): Promise<ConfigValidationResponse | null> {
  try {
    return await api.validateSetup();
  } catch (error) {
    console.error("Failed to get setup status:", error);
    return null;
  }
}

/**
 * Check if the wizard has been completed before.
 */
export function isWizardCompleted(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(WIZARD_COMPLETE_KEY) === "true";
}

/**
 * Mark the wizard as completed.
 */
export function markWizardComplete(): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(WIZARD_COMPLETE_KEY, "true");
  // Clear any saved progress
  localStorage.removeItem(WIZARD_PROGRESS_KEY);
}

/**
 * Clear the wizard completion status (for re-running wizard).
 */
export function clearWizardCompletion(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(WIZARD_COMPLETE_KEY);
  localStorage.removeItem(WIZARD_PROGRESS_KEY);
}

/**
 * Save wizard progress for resuming later.
 *
 * Sensitive credentials (API keys, Wi-Fi passwords) are intentionally
 * stripped before persisting to ``localStorage``: that storage is not a
 * secure place for secrets and any persisted copy survives sign-out.
 * Users can re-enter the values when resuming the wizard.
 */
export function saveWizardProgress(progress: WizardProgress): void {
  if (typeof window === "undefined") return;

  // Deep-clone and redact secrets before persisting.
  const sanitized: WizardProgress = {
    ...progress,
    boardConfig: progress.boardConfig
      ? {
          ...progress.boardConfig,
          // Drop the API keys — they're sensitive credentials.
          local_api_key: undefined,
          cloud_key: undefined,
        }
      : undefined,
    plugins: progress.plugins
      ? {
          ...progress.plugins,
          guest_wifi: progress.plugins.guest_wifi
            ? {
                ...progress.plugins.guest_wifi,
                // Drop the Wi-Fi password.
                password: "",
              }
            : undefined,
        }
      : undefined,
  };

  localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify(sanitized));
}

/**
 * Get saved wizard progress.
 */
export function getWizardProgress(): WizardProgress | null {
  if (typeof window === "undefined") return null;
  const saved = localStorage.getItem(WIZARD_PROGRESS_KEY);
  if (!saved) return null;
  try {
    return upgradeWizardProgress(JSON.parse(saved) as WizardProgress);
  } catch {
    return null;
  }
}

/**
 * Progress saved by the Vestaboard-only wizard (no `outputId`) counted its
 * steps from "Connect"; the wizard now opens on "choose your display". Past
 * its first step that wizard was a Vestaboard one, so resume it as such, one
 * step later. On its first step there is nothing to carry over.
 */
export function upgradeWizardProgress(progress: WizardProgress): WizardProgress {
  if (progress.outputId !== undefined || progress.currentStep <= 1) return progress;
  return { ...progress, outputId: "vestaboard", currentStep: progress.currentStep + 1 };
}

/**
 * Clear saved wizard progress.
 */
export function clearWizardProgress(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(WIZARD_PROGRESS_KEY);
}
