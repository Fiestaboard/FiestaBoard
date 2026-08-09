"use client";

import { Box, Button, Code, Flex, Heading, Stack, Text } from "@fiestaboard/ui";
import { RefreshCw } from "lucide-react";
import { createContext, Fragment, useCallback, useContext, useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api, type UpdateAttemptStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type UpdatePhase = "pulling" | "restarting" | "ready" | "failed" | "error";

interface UpdateContextValue {
  isUpdating: boolean;
  startUpdate: (currentVersion?: string) => void;
  /**
   * True when the page has just reloaded itself at the end of an update and
   * the API hasn't answered yet. BootGate reads this to explain the wait
   * ("finishing update") instead of showing its generic "can't connect"
   * treatment, which reads as a failure when nothing is wrong.
   */
  awaitingPostUpdateBoot: boolean;
  /** Called by BootGate once the API answers, retiring the marker. */
  markPostUpdateBootComplete: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const UpdateContext = createContext<UpdateContextValue>({
  isUpdating: false,
  startUpdate: () => {},
  awaitingPostUpdateBoot: false,
  markPostUpdateBootComplete: () => {},
});

// ---------------------------------------------------------------------------
// localStorage persistence
//
// Two distinct states share one key:
//   * `awaitingBoot` unset — an update is in flight; the overlay resumes and
//     keeps polling (survives a manual refresh mid-update).
//   * `awaitingBoot: true` — the update FINISHED and we reloaded the page on
//     purpose. The overlay must NOT resume (it would see "success" again and
//     reload forever); only BootGate cares, so it can say "finishing update"
//     while the new container's API warms up.
// ---------------------------------------------------------------------------

const LS_KEY = "fb_updating";
const MAX_AGE_MS = 10 * 60 * 1000; // 10 minutes — matches UPDATE_TIMEOUT_MS
/** A post-update boot that hasn't completed within this window is stale. */
const AWAITING_BOOT_MAX_AGE_MS = 5 * 60 * 1000;

interface PersistedUpdate {
  fromVersion?: string;
  startedAt: number;
  awaitingBoot?: boolean;
}

function readPersisted(): PersistedUpdate | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedUpdate;
    if (typeof parsed.startedAt !== "number") return null;
    const maxAge = parsed.awaitingBoot ? AWAITING_BOOT_MAX_AGE_MS : MAX_AGE_MS;
    if (Date.now() - parsed.startedAt > maxAge) {
      localStorage.removeItem(LS_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writePersisted(entry: PersistedUpdate) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(entry));
  } catch {}
}

function clearPersisted() {
  try {
    localStorage.removeItem(LS_KEY);
  } catch {}
}

/**
 * Flip the persisted entry into "we reloaded, waiting for the new container"
 * mode. Keeps `startedAt` fresh so the staleness window is measured from the
 * reload, not from when the update began.
 */
function markAwaitingBoot(fromVersion?: string) {
  writePersisted({ fromVersion, startedAt: Date.now(), awaitingBoot: true });
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function UpdateProvider({ children }: { children: React.ReactNode }) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<string | undefined>(undefined);
  const [awaitingPostUpdateBoot, setAwaitingPostUpdateBoot] = useState(false);

  // On mount: pick up whatever the previous page life left behind.
  useEffect(() => {
    const persisted = readPersisted();
    if (!persisted) return;
    setCurrentVersion(persisted.fromVersion);
    if (persisted.awaitingBoot) {
      setAwaitingPostUpdateBoot(true);
    } else {
      setIsUpdating(true);
    }
  }, []);

  const startUpdate = useCallback((version?: string) => {
    writePersisted({ fromVersion: version, startedAt: Date.now() });
    setCurrentVersion(version);
    setIsUpdating(true);
  }, []);

  const markPostUpdateBootComplete = useCallback(() => {
    clearPersisted();
    setAwaitingPostUpdateBoot(false);
  }, []);

  const handleDone = useCallback(() => {
    clearPersisted();
    setIsUpdating(false);
  }, []);

  return (
    <UpdateContext.Provider value={{ isUpdating, startUpdate, awaitingPostUpdateBoot, markPostUpdateBootComplete }}>
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
const POLL_INTERVAL_MS = 2000;
/** Docker needs a beat to start acting on the request before we poll. */
const INITIAL_DELAY_MS = 1500;
/** Let the user read "update complete" before the page goes white. */
const READY_HOLD_MS = 800;
/**
 * Consecutive failed polls before we believe the container is actually gone.
 * A single failure means nothing: while the sidecar pulls a few hundred MB the
 * box is busy enough that one request can time out, and nginx answers 503 from
 * its `@api_starting` fallback whenever uvicorn is slow to respond. Treating
 * either as "the container went down" is what used to end the overlay early.
 */
const DOWN_THRESHOLD = 3;

/** Sidecar states that mean the attempt is over and it worked. */
const SUCCESS_STATES: ReadonlySet<UpdateAttemptStatus> = new Set<UpdateAttemptStatus>(["success", "rolled_back"]);
/** Sidecar states that mean the attempt is over and it did not work. */
const FAILURE_STATES: ReadonlySet<UpdateAttemptStatus> = new Set<UpdateAttemptStatus>(["failed", "rollback_failed"]);

/**
 * Full-screen overlay rendered at the provider level (app layout). Survives
 * client-side navigation and a manual browser refresh (via localStorage).
 *
 * Polling strategy — the fiestaupdater sidecar is the source of truth:
 *
 *   Every 2 s, ask the API for /system/update/status, which proxies the
 *   sidecar's own record of the attempt. The sidecar is a separate container,
 *   so that record survives FiestaBoard being torn down and recreated.
 *
 *     - `in_progress` / `none`  → still working; keep waiting.
 *     - `success` / `rolled_back` → the new image is in place; reload.
 *     - `failed` / `rollback_failed` → surface the sidecar's error instead of
 *       silently reloading into the version the user was already on.
 *     - request failed → the API is unreachable. Only after DOWN_THRESHOLD
 *       *consecutive* failures do we call that a restart; single blips during
 *       the pull are noise.
 *
 * The previous implementation inferred everything from /version alone: one
 * failed poll flipped it to "restarting", and the next successful poll — even
 * from the same, unchanged container — was read as "update complete", so it
 * reloaded the user back to Settings while the pull was still running. The
 * banner was of course still there (nothing had been updated yet), and the
 * real restart landed a minute later with no explanation on screen.
 *
 * Fallback: if the sidecar's record is unavailable (state file lost, sidecar
 * replaced) but the API came back reporting a *different* package version
 * after a confirmed down period, that is also proof the swap happened.
 *
 * A 10-minute deadline surfaces an error state with a manual refresh button so
 * the user can never be stuck in an infinite spinner.
 */
function UpdateOverlay({ currentVersion, onDone }: { currentVersion?: string; onDone: () => void }) {
  const t = useTranslations("updateOverlay");
  const [phase, setPhase] = useState<UpdatePhase>("pulling");
  const [failureReason, setFailureReason] = useState<string | null>(null);
  const everWentDown = useRef(false);

  // Polling loop.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = Date.now() + UPDATE_TIMEOUT_MS;
    let consecutiveFailures = 0;

    const finish = () => {
      if (cancelled) return;
      setPhase("ready");
      // Deliberately NOT clearPersisted(): the marker flips to "awaiting boot"
      // so that after the reload BootGate can explain the wait rather than
      // showing a bare "Waiting to start…" / "Couldn't connect".
      markAwaitingBoot(currentVersion);
      timer = setTimeout(() => window.location.reload(), READY_HOLD_MS);
    };

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setPhase("error");
        return;
      }

      try {
        const status = await api.getUpdateStatus();
        consecutiveFailures = 0;
        const attempt = status.last_update_status;

        if (attempt && SUCCESS_STATES.has(attempt)) {
          finish();
          return;
        }
        if (attempt && FAILURE_STATES.has(attempt)) {
          if (!cancelled) {
            setFailureReason(status.last_update_error);
            setPhase("failed");
            clearPersisted();
          }
          return;
        }

        // No usable sidecar verdict. If the container demonstrably went away
        // and came back on a different version, the swap happened regardless
        // of what the state file says.
        if (everWentDown.current) {
          const v = await api.getVersion();
          if (currentVersion && v.package_version && v.package_version !== currentVersion) {
            finish();
            return;
          }
        }

        if (!cancelled) setPhase(everWentDown.current ? "restarting" : "pulling");
      } catch {
        // The API is unreachable — but one failure is not a restart.
        consecutiveFailures += 1;
        if (consecutiveFailures >= DOWN_THRESHOLD) {
          everWentDown.current = true;
          if (!cancelled) setPhase("restarting");
        }
      }

      if (!cancelled) timer = setTimeout(tick, POLL_INTERVAL_MS);
    };

    timer = setTimeout(tick, INITIAL_DELAY_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [currentVersion]);

  if (phase === "failed") {
    return (
      <Flex align="center" justify="center" className="fixed inset-0 z-[200] bg-black text-white">
        <Stack gap="4" className="text-center max-w-sm mx-auto px-4">
          <Heading level={2} className="text-xl">
            {t("failedHeading")}
          </Heading>
          <Text className="text-white/70">
            {t.rich("failedDescription", {
              code: (chunks: React.ReactNode) => <Code className="text-xs bg-white/10 px-1 rounded">{chunks}</Code>,
            })}
          </Text>
          {failureReason && (
            <Text size="xs" className="text-white/50">
              {t("failedReason", { reason: failureReason })}
            </Text>
          )}
          <Button
            variant="outline"
            className="border-white/30 text-white hover:bg-white/10 hover:text-white"
            onClick={onDone}
          >
            {t("dismiss")}
          </Button>
        </Stack>
      </Flex>
    );
  }

  if (phase === "error") {
    return (
      <Flex align="center" justify="center" className="fixed inset-0 z-[200] bg-black text-white">
        <Stack gap="4" className="text-center max-w-sm mx-auto px-4">
          <Heading level={2} className="text-xl">
            {t("takingLonger")}
          </Heading>
          <Text className="text-white/70">
            {t.rich("takingLongerDescription", {
              code: (chunks: React.ReactNode) => <Code className="text-xs bg-white/10 px-1 rounded">{chunks}</Code>,
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
    phase === "pulling" ? t("phasePulling") : phase === "ready" ? t("phaseReady") : t("phaseRestarting");

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
