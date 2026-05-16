import { describe, it, expect, vi, afterEach } from "vitest";
import {
  writeLiveOutputMessage,
  readLiveOutputMessage,
  onLiveOutputMessageChange,
} from "@/lib/live-output-channel";

const STORAGE_KEY = "fiestaboard:liveOutputMessage";

describe("live-output-channel", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  describe("writeLiveOutputMessage", () => {
    it("removes the key when message is null", () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify("hello"));
      writeLiveOutputMessage(null);
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it("writes JSON-encoded string when message is non-null", () => {
      writeLiveOutputMessage("hello world");
      expect(localStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify("hello world"));
    });

    it("does not throw when localStorage throws on write", () => {
      vi.spyOn(localStorage, "setItem").mockImplementation(() => {
        throw new Error("storage unavailable");
      });
      expect(() => writeLiveOutputMessage("any string")).not.toThrow();
    });

    it("does not throw when localStorage throws on remove", () => {
      vi.spyOn(localStorage, "removeItem").mockImplementation(() => {
        throw new Error("storage unavailable");
      });
      expect(() => writeLiveOutputMessage(null)).not.toThrow();
    });
  });

  describe("readLiveOutputMessage", () => {
    it("returns null when key is not set", () => {
      expect(readLiveOutputMessage()).toBeNull();
    });

    it("returns the stored message string", () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify("test message"));
      expect(readLiveOutputMessage()).toBe("test message");
    });

    it("returns null when localStorage throws", () => {
      vi.spyOn(localStorage, "getItem").mockImplementation(() => {
        throw new Error("storage unavailable");
      });
      expect(readLiveOutputMessage()).toBeNull();
    });
  });

  describe("onLiveOutputMessageChange", () => {
    it("does not call callback for unrelated storage keys", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      window.dispatchEvent(
        new StorageEvent("storage", { key: "other-key", newValue: "whatever" }),
      );
      expect(callback).not.toHaveBeenCalled();
      unsubscribe();
    });

    it("calls callback with null when newValue is null", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      window.dispatchEvent(
        new StorageEvent("storage", { key: STORAGE_KEY, newValue: null }),
      );
      expect(callback).toHaveBeenCalledWith(null);
      unsubscribe();
    });

    it("calls callback with parsed string when newValue is valid JSON", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: STORAGE_KEY,
          newValue: JSON.stringify("from other tab"),
        }),
      );
      expect(callback).toHaveBeenCalledWith("from other tab");
      unsubscribe();
    });

    it("calls callback with null when newValue is invalid JSON", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      window.dispatchEvent(
        new StorageEvent("storage", { key: STORAGE_KEY, newValue: "not-valid-json{{" }),
      );
      expect(callback).toHaveBeenCalledWith(null);
      unsubscribe();
    });

    it("stops calling callback after unsubscribe", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      unsubscribe();
      window.dispatchEvent(
        new StorageEvent("storage", { key: STORAGE_KEY, newValue: null }),
      );
      expect(callback).not.toHaveBeenCalled();
    });
  });
});
