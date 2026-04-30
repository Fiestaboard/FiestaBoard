"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Loader2, RefreshCw } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type UpdatePhase = "pulling" | "restarting" | "ready" | "error";

interface UpdateContextValue {
  isUpdating: boolean;
  startUpdate: (currentVersion?: string) => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const UpdateContext = createContext<UpdateContextValue>({
  isUpdating: false,
  startUpdate: () => {},
});

// ---------------------------------------------------------------------------
// localStorage persistence key
// Stored value: JSON string of { fromVersion?: string; startedAt: number }
// ---------------------------------------------------------------------------

const LS_KEY = "fb_updating";
const MAX_AGE_MS = 10 * 60 * 1000; // 10 minutes — matches UPDATE_TIMEOUT_MS

function readPersisted(): { fromVersion?: string; startedAt: number } | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { fromVersion?: string; startedAt: number };
    if (typeof parsed.startedAt !== "number") return null;
    if (Date.now() - parsed.startedAt > MAX_AGE_MS) {
      localStorage.removeItem(LS_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writePersisted(fromVersion?: string) {
  try {
    localStorage.setItem(
      LS_KEY,
      JSON.stringify({ fromVersion, startedAt: Date.now() }),
    );
  } catch {}
}

function clearPersisted() {
  try {
    localStorage.removeItem(LS_KEY);
  } catch {}
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function UpdateProvider({ children }: { children: React.ReactNode }) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<string | undefined>(
    undefined,
  );

  // On mount: resume an in-progress update if a recent entry exists in localStorage.
  useEffect(() => {
    const persisted = readPersisted();
    if (persisted) {
      setCurrentVersion(persisted.fromVersion);
      setIsUpdating(true);
    }
  }, []);

  const startUpdate = useCallback((version?: string) => {
    writePersisted(version);
    setCurrentVersion(version);
    setIsUpdating(true);
  }, []);

  const handleDone = useCallback(() => {
    clearPersisted();
    setIsUpdating(false);
  }, []);

  return (
    <UpdateContext.Provider value={{ isUpdating, startUpdate }}>
      {children}
      {isUpdating && (
        <UpdateOverlay currentVersion={currentVersion} onDone={handleDone} />
      )}
    </UpdateContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useUpdate() {
  return useContext(UpdateContext);
}

// ---------------------------------------------------------------------------
// Overlay
// ---------------------------------------------------------------------------

const UPDATE_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes

/**
 * Full-screen black overlay rendered at the provider level (app layout).
 * Survives client-side navigation and even a manual browser refresh (via
 * localStorage).
 *
 * Polling strategy — two-phase:
 *   Phase 1 ("pulling"): poll /version every 2 s.
 *     - If the API throws (container stopped) → set everWentDown = true.
 *     - If the API returns a NEW version (without going down first) →
 *       rare fast swap, treat as done.
 *   Phase 2 (everWentDown): poll /version every 2 s.
 *     - Once the API responds successfully → "ready" → reload.
 *
 * A 10-minute deadline surfaces an error state with a manual refresh
 * button so the user can never be stuck in an infinite spinner.
 */
function UpdateOverlay({
  currentVersion,
  onDone,
}: {
  currentVersion?: string;
  onDone: () => void;
}) {
  const [phase, setPhase] = useState<UpdatePhase>("pulling");
  const [elapsed, setElapsed] = useState(0);
  const everWentDown = useRef(false);

  // Elapsed-time counter — ticks every second.
  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Polling loop.
  useEffect(() => {
    let cancelled = false;
    const deadline = Date.now() + UPDATE_TIMEOUT_MS;

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setPhase("error");
        return;
      }

      try {
        const v = await api.getVersion();
        if (everWentDown.current) {
          // Container came back up after being down — reload.
          if (!cancelled) {
            setPhase("ready");
            clearPersisted();
            setTimeout(() => window.location.reload(), 800);
          }
          return;
        }
        // Container still running. Detect version change (fast swap without
        // a visible down period).
        if (
          currentVersion &&
          v.package_version &&
          v.package_version !== currentVersion
        ) {
          if (!cancelled) {
            setPhase("ready");
            clearPersisted();
            setTimeout(() => window.location.reload(), 800);
          }
          return;
        }
      } catch {
        // API is unreachable — the old container stopped.
        everWentDown.current = true;
        setPhase("restarting");
      }

      setTimeout(tick, 2000);
    };

    // Brief initial pause so Docker has time to begin processing the
    // update command before we start checking.
    setTimeout(tick, 1500);
    return () => {
      cancelled = true;
    };
  }, [currentVersion]);

  // Format elapsed time as M:SS.
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedLabel = `${minutes}:${String(seconds).padStart(2, "0")} elapsed`;

  if (phase === "error") {
    return (
      <div className="fixed inset-0 z-[200] bg-black text-white flex items-center justify-center">
        <div className="text-center space-y-4 max-w-sm mx-auto px-4">
          <h2 className="text-xl font-semibold">Update taking longer than expected</h2>
          <p className="text-sm text-white/70">
            The update may still be running in the background. Check{" "}
            <code className="text-xs bg-white/10 px-1 rounded">docker logs fiestaupdater</code>{" "}
            on the host, then refresh.
          </p>
          <Button
            variant="outline"
            className="border-white/30 text-white hover:bg-white/10 hover:text-white"
            onClick={() => {
              clearPersisted();
              onDone();
            }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Dismiss and refresh page
          </Button>
        </div>
      </div>
    );
  }

  const phaseMessage =
    phase === "pulling" && !everWentDown.current
      ? "Pulling the latest image from Docker Hub…"
      : phase === "ready"
        ? "Update complete. Reloading…"
        : "Restarting FiestaBoard…";

  return (
    <div className="fixed inset-0 z-[200] bg-black text-white flex items-center justify-center">
      <div className="text-center space-y-6 max-w-sm mx-auto px-4">
        {phase === "ready" ? (
          <RefreshCw className="h-12 w-12 mx-auto animate-spin text-white" />
        ) : (
          <Loader2 className="h-12 w-12 mx-auto animate-spin text-white" />
        )}
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">Updating FiestaBoard</h2>
          <p className="text-base text-white/80">{phaseMessage}</p>
        </div>
        <div className="space-y-1">
          <p className="text-sm text-white/50">{elapsedLabel}</p>
          <p className="text-xs text-white/40">
            Updates can take a few minutes — please don&apos;t close this tab.
          </p>
        </div>
      </div>
    </div>
  );
}
