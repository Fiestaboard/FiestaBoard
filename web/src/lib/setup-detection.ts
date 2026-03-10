/**
 * Setup detection utilities for the FiestaBoard onboarding wizard.
 * 
 * Detects first-run state, manages wizard completion status,
 * and provides utilities for the setup flow.
 */

import { api, ConfigValidationResponse } from "./api";

const WIZARD_COMPLETE_KEY = "fiestaboard_wizard_complete";
const WIZARD_PROGRESS_KEY = "fiestaboard_wizard_progress";

export interface WizardProgress {
  currentStep: number;
  boardConfig?: {
    api_mode: "local" | "cloud";
    local_api_key?: string;
    cloud_key?: string;
    host?: string;
    device_type?: "flagship" | "note";
    board_color?: "black" | "white";
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
    
    // If first run (missing board config), show wizard unless user already skipped
    if (validation.is_first_run) {
      if (isWizardCompleted()) {
        return false;
      }
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
 */
export function saveWizardProgress(progress: WizardProgress): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify(progress));
}

/**
 * Get saved wizard progress.
 */
export function getWizardProgress(): WizardProgress | null {
  if (typeof window === "undefined") return null;
  const saved = localStorage.getItem(WIZARD_PROGRESS_KEY);
  if (!saved) return null;
  try {
    return JSON.parse(saved) as WizardProgress;
  } catch {
    return null;
  }
}

/**
 * Clear saved wizard progress.
 */
export function clearWizardProgress(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(WIZARD_PROGRESS_KEY);
}

