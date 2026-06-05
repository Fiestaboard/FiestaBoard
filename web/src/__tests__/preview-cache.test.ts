import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearPreviewCache, clearPreviewCacheForPage } from "@/lib/preview-cache";

const BATCH_CACHE_KEY = "fiestaboard_previews_batch";

describe("preview-cache", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe("clearPreviewCache", () => {
    it("removes the batch cache key from localStorage", () => {
      localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify({ "page-1": { lines: ["test"] } }));
      expect(localStorage.getItem(BATCH_CACHE_KEY)).not.toBeNull();

      clearPreviewCache();
      expect(localStorage.getItem(BATCH_CACHE_KEY)).toBeNull();
    });

    it("does nothing when cache does not exist", () => {
      clearPreviewCache();
      expect(localStorage.getItem(BATCH_CACHE_KEY)).toBeNull();
    });

    it("does nothing when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);

      expect(() => clearPreviewCache()).not.toThrow();

      vi.stubGlobal("window", originalWindow);
    });
  });

  describe("clearPreviewCacheForPage", () => {
    it("returns early when window is undefined (SSR)", () => {
      const originalWindow = globalThis.window;
      vi.stubGlobal("window", undefined);

      expect(() => clearPreviewCacheForPage("page-1")).not.toThrow();

      vi.stubGlobal("window", originalWindow);
    });

    it("removes a specific page from cached previews", () => {
      const cached = { "page-1": { lines: ["hello"] }, "page-2": { lines: ["world"] } };
      localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(cached));

      clearPreviewCacheForPage("page-1");

      const result = JSON.parse(localStorage.getItem(BATCH_CACHE_KEY)!);
      expect(result["page-1"]).toBeUndefined();
      expect(result["page-2"]).toEqual({ lines: ["world"] });
    });

    it("does nothing when cache key does not exist", () => {
      clearPreviewCacheForPage("page-1");
      expect(localStorage.getItem(BATCH_CACHE_KEY)).toBeNull();
    });

    it("does nothing when page is not in cache", () => {
      const cached = { "page-2": { lines: ["hello"] } };
      localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(cached));

      clearPreviewCacheForPage("page-99");

      const result = JSON.parse(localStorage.getItem(BATCH_CACHE_KEY)!);
      expect(result["page-2"]).toEqual({ lines: ["hello"] });
    });

    it("clears entire cache when stored JSON is invalid", () => {
      localStorage.setItem(BATCH_CACHE_KEY, "not-valid-json");

      clearPreviewCacheForPage("page-1");

      expect(localStorage.getItem(BATCH_CACHE_KEY)).toBeNull();
    });
  });
});
