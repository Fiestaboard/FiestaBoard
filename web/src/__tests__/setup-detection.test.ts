import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WizardProgress } from "@/lib/setup-detection";
import {
  clearWizardCompletion,
  clearWizardProgress,
  getSetupStatus,
  getWizardProgress,
  isWizardCompleted,
  markWizardComplete,
  saveWizardProgress,
  shouldShowWizard,
} from "@/lib/setup-detection";

import { server } from "./mocks/server";

const API_BASE = "/api";
const WIZARD_COMPLETE_KEY = "fiestaboard_wizard_complete";
const WIZARD_PROGRESS_KEY = "fiestaboard_wizard_progress";

describe("setup-detection", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe("shouldShowWizard", () => {
    it("returns true when is_first_run is true", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: false, is_first_run: true, errors: [], missing_fields: [] }),
        ),
      );
      expect(await shouldShowWizard()).toBe(true);
    });

    it("returns true when config is invalid and wizard not completed", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: false, is_first_run: false, errors: ["missing host"], missing_fields: ["host"] }),
        ),
      );
      expect(await shouldShowWizard()).toBe(true);
    });

    it("returns false when config is invalid but wizard was previously completed", async () => {
      localStorage.setItem(WIZARD_COMPLETE_KEY, "true");
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: false, is_first_run: false, errors: ["missing host"], missing_fields: ["host"] }),
        ),
      );
      expect(await shouldShowWizard()).toBe(false);
    });

    it("returns false when config is valid", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] }),
        ),
      );
      expect(await shouldShowWizard()).toBe(false);
    });

    it("returns false when API call fails", async () => {
      server.use(http.get(`${API_BASE}/config/validate`, () => new HttpResponse(null, { status: 500 })));
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      expect(await shouldShowWizard()).toBe(false);
      consoleSpy.mockRestore();
    });
  });

  describe("getSetupStatus", () => {
    it("returns validation response on success", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] }),
        ),
      );
      const result = await getSetupStatus();
      expect(result).not.toBeNull();
      expect(result!.valid).toBe(true);
    });

    it("returns null on API failure", async () => {
      server.use(http.get(`${API_BASE}/config/validate`, () => new HttpResponse(null, { status: 500 })));
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = await getSetupStatus();
      expect(result).toBeNull();
      consoleSpy.mockRestore();
    });
  });

  describe("isWizardCompleted", () => {
    it("returns false when not set", () => {
      expect(isWizardCompleted()).toBe(false);
    });

    it("returns true when set to true", () => {
      localStorage.setItem(WIZARD_COMPLETE_KEY, "true");
      expect(isWizardCompleted()).toBe(true);
    });

    it("returns false when set to other value", () => {
      localStorage.setItem(WIZARD_COMPLETE_KEY, "false");
      expect(isWizardCompleted()).toBe(false);
    });

    it("returns false when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      expect(isWizardCompleted()).toBe(false);
      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("markWizardComplete", () => {
    it("sets completion flag and clears progress", () => {
      localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify({ currentStep: 2 }));
      markWizardComplete();
      expect(localStorage.getItem(WIZARD_COMPLETE_KEY)).toBe("true");
      expect(localStorage.getItem(WIZARD_PROGRESS_KEY)).toBeNull();
    });

    it("does nothing when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      expect(() => markWizardComplete()).not.toThrow();
      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("clearWizardCompletion", () => {
    it("removes both completion and progress keys", () => {
      localStorage.setItem(WIZARD_COMPLETE_KEY, "true");
      localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify({ currentStep: 1 }));
      clearWizardCompletion();
      expect(localStorage.getItem(WIZARD_COMPLETE_KEY)).toBeNull();
      expect(localStorage.getItem(WIZARD_PROGRESS_KEY)).toBeNull();
    });

    it("does nothing when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      expect(() => clearWizardCompletion()).not.toThrow();
      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("saveWizardProgress", () => {
    it("saves progress to localStorage", () => {
      const progress: WizardProgress = {
        currentStep: 2,
        boardConfig: { api_mode: "local", host: "192.168.1.1" },
      };
      saveWizardProgress(progress);
      const saved = JSON.parse(localStorage.getItem(WIZARD_PROGRESS_KEY)!);
      expect(saved.currentStep).toBe(2);
      expect(saved.boardConfig.api_mode).toBe("local");
    });

    it("does nothing when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      const progress: WizardProgress = { currentStep: 1 };
      expect(() => saveWizardProgress(progress)).not.toThrow();
      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("getWizardProgress", () => {
    it("returns null when no progress saved", () => {
      expect(getWizardProgress()).toBeNull();
    });

    it("returns parsed progress", () => {
      const progress: WizardProgress = { currentStep: 3 };
      localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify(progress));
      const result = getWizardProgress();
      expect(result).not.toBeNull();
      expect(result!.currentStep).toBe(3);
    });

    it("returns null when stored JSON is invalid", () => {
      localStorage.setItem(WIZARD_PROGRESS_KEY, "not-json");
      expect(getWizardProgress()).toBeNull();
    });

    it("returns null when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      expect(getWizardProgress()).toBeNull();
      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("clearWizardProgress", () => {
    it("removes progress key", () => {
      localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify({ currentStep: 1 }));
      clearWizardProgress();
      expect(localStorage.getItem(WIZARD_PROGRESS_KEY)).toBeNull();
    });

    it("does nothing when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);
      expect(() => clearWizardProgress()).not.toThrow();
      vi.stubGlobal("window", originalWindow);
    });
  });
});
