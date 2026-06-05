import { afterEach, describe, expect, it, vi } from "vitest";

import { onLiveOutputMessageChange, readLiveOutputMessage, writeLiveOutputMessage } from "@/lib/live-output-channel";

const STORAGE_KEY = "fiestaboard:liveOutputMessage";

// CodeQL's StorageEvent extern takes zero constructor arguments, so we dispatch
// a plain Event and attach key/newValue as own properties. The handler in
// live-output-channel.ts only reads those two fields, so the cast is safe.
function fireStorageEvent(key: string | null, newValue: string | null): void {
  const event = new Event("storage");
  Object.defineProperty(event, "key", { value: key, configurable: true });
  Object.defineProperty(event, "newValue", { value: newValue, configurable: true });
  window.dispatchEvent(event as StorageEvent);
}

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
      fireStorageEvent("other-key", "whatever");
      expect(callback).not.toHaveBeenCalled();
      unsubscribe();
    });

    it("calls callback with null when newValue is null", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      fireStorageEvent(STORAGE_KEY, null);
      expect(callback).toHaveBeenCalledWith(null);
      unsubscribe();
    });

    it("calls callback with parsed string when newValue is valid JSON", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      fireStorageEvent(STORAGE_KEY, JSON.stringify("from other tab"));
      expect(callback).toHaveBeenCalledWith("from other tab");
      unsubscribe();
    });

    it("calls callback with null when newValue is invalid JSON", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      fireStorageEvent(STORAGE_KEY, "not-valid-json{{");
      expect(callback).toHaveBeenCalledWith(null);
      unsubscribe();
    });

    it("stops calling callback after unsubscribe", () => {
      const callback = vi.fn();
      const unsubscribe = onLiveOutputMessageChange(callback);
      unsubscribe();
      fireStorageEvent(STORAGE_KEY, null);
      expect(callback).not.toHaveBeenCalled();
    });
  });
});
