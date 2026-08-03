"use client";

import { Box, Button, Code, Flex, Heading, Stack, Text } from "@fiestaboard/ui";
import { RefreshCw } from "lucide-react";
import { createContext, Fragment, useCallback, useContext, useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

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
    localStorage.setItem(LS_KEY, JSON.stringify({ fromVersion, startedAt: Date.now() }));
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
  const [currentVersion, setCurrentVersion] = useState<string | undefined>(undefined);

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
      {isUpdating && <UpdateOverlay currentVersion={currentVersion} onDone={handleDone} />}
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
function UpdateOverlay({ currentVersion, onDone }: { currentVersion?: string; onDone: () => void }) {
  const t = useTranslations("updateOverlay");
  const [phase, setPhase] = useState<UpdatePhase>("pulling");
  const everWentDown = useRef(false);

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
        if (currentVersion && v.package_version && v.package_version !== currentVersion) {
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

  if (phase === "error") {
    return (
      <Flex align="center" justify="center" className="fixed inset-0 z-[200] bg-black text-white">
        <Stack gap="4" className="text-center max-w-sm mx-auto px-4">
          <Heading level={2} className="text-xl">
            {t("takingLonger")}
          </Heading>
          <Text className="text-white/70">
            {t.rich("takingLongerDescription", {
              code: (chunks) => <Code className="text-xs bg-white/10 px-1 rounded">{chunks}</Code>,
            })}
          </Text>
          <Button
            variant="outline"
            className="border-white/30 text-white hover:bg-white/10 hover:text-white"
            onClick={() => {
              clearPersisted();
              onDone();
            }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            {t("dismissAndRefresh")}
          </Button>
        </Stack>
      </Flex>
    );
  }

  const steps = [
    { key: "pull", label: t("stepPull") },
    { key: "restart", label: t("stepRestart") },
    { key: "done", label: t("stepDone") },
  ];
  const stepIndex = phase === "ready" ? 2 : phase === "restarting" ? 1 : 0;

  const phaseMessage =
    phase === "pulling" && !everWentDown.current
      ? t("phasePulling")
      : phase === "ready"
        ? t("phaseReady")
        : t("phaseRestarting");

  return (
    <Flex align="center" justify="center" className="fixed inset-0 z-[200] bg-black text-white">
      <Stack gap="6" className="text-center max-w-xs mx-auto px-4">
        {/* Spinner */}
        <Box className="h-12 w-12 mx-auto rounded-full border-[3px] border-white/20 border-t-white animate-spin" />

        {/* Title + current phase message */}
        <Stack gap="2">
          <Heading level={2} className="text-2xl">
            {t("updatingFiestaboard")}
          </Heading>
          <Text size="base" className="text-white/80">
            {phaseMessage}
          </Text>
        </Stack>

        {/* Step dots */}
        <Flex align="start" className="w-full">
          {steps.map((step, i) => {
            const isCompleted = i < stepIndex;
            const isActive = i === stepIndex;
            return (
              <Fragment key={step.key}>
                <Stack align="center" gap="1.5" className="flex-shrink-0">
                  <Box
                    className={cn(
                      "h-2.5 w-2.5 rounded-full transition-all duration-500",
                      isCompleted || isActive ? "bg-white" : "bg-white/25",
                      isActive && "ring-2 ring-white/40 ring-offset-2 ring-offset-black",
                    )}
                  />
                  <Text
                    as="span"
                    size="xs"
                    className={cn(
                      "leading-none transition-colors duration-500",
                      isActive ? "text-white" : isCompleted ? "text-white/50" : "text-white/25",
                    )}
                  >
                    {step.label}
                  </Text>
                </Stack>
                {i < steps.length - 1 && (
                  <Box
                    className={cn(
                      "flex-1 h-px mt-[5px] mx-2 transition-all duration-500",
                      isCompleted ? "bg-white/50" : "bg-white/15",
                    )}
                  />
                )}
              </Fragment>
            );
          })}
        </Flex>

        <Text size="xs" className="text-white/40">
          {t("dontCloseTab")}
        </Text>
      </Stack>
    </Flex>
  );
}
