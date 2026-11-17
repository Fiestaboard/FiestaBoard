"use client";

import { Box, Flex, Text } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import type { ReactNode } from "react";
import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";
import { clearWizardCompletion, shouldShowWizard } from "@/lib/setup-detection";

import { isUntouchedPlaceholder } from "./wizard/default-board";

function WizardLoadingFallback() {
  const t = useTranslations("wizardProvider");
  return (
    <Flex align="center" justify="center" className="fixed inset-0 bg-background">
      <Box className="text-center">
        <Spinner size="lg" className="size-8 text-primary" label={null} />
        <Text tone="muted" className="mt-4">
          {t("loadingSetupWizard")}
        </Text>
      </Box>
    </Flex>
  );
}

// Lazy load SetupWizard since it's only needed on first visit or when manually triggered
const SetupWizardLazy = lazy(() => import("@/components/wizard").then((mod) => ({ default: mod.SetupWizard })));
function SetupWizard(props: React.ComponentProps<typeof SetupWizardLazy>) {
  return (
    <Suspense fallback={<WizardLoadingFallback />}>
      <SetupWizardLazy {...props} />
    </Suspense>
  );
}

interface WizardContextType {
  isWizardActive: boolean;
  triggerWizard: () => void; // Opens wizard and clears completion status (for manual re-run)
}

const WizardContext = createContext<WizardContextType | undefined>(undefined);

export function useWizard() {
  const context = useContext(WizardContext);
  if (!context) {
    throw new Error("useWizard must be used within a WizardProvider");
  }
  return context;
}

interface WizardProviderProps {
  children: ReactNode;
}

export function WizardProvider({ children }: WizardProviderProps) {
  const t = useTranslations("wizardProvider");
  const pathname = usePathname();
  // ``/login`` owns its own UI (sign-in form, first-run auth picker) and the
  // ``/config/validate`` request the wizard relies on is unauthenticated-401
  // there. Treat the auth screen as a "wizard off" surface and re-check the
  // moment the user leaves it — that's the transition where the first-run
  // wizard should appear on a freshly provisioned device. The FiestaPanel
  // viewer is chrome-less for the same reason: a TV browser has no session,
  // and a wall display must never be replaced by the setup wizard.
  const isOnAuthScreen = pathname ? isChromelessPath(pathname) : false;
  const [isWizardActive, setIsWizardActive] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);
  const rerunRequest = useRef(0);

  useEffect(
    () => () => {
      rerunRequest.current++;
    },
    [isOnAuthScreen],
  );

  useEffect(() => {
    // Skip the check on /login — ``/config/validate`` would 401 there and
    // the render branch below renders children directly, so there's nothing
    // to gate. The effect re-runs (via the ``isOnAuthScreen`` dep) the
    // moment the user navigates away from /login, which is the transition
    // where the first-run wizard should appear on a freshly provisioned
    // device.
    if (isOnAuthScreen) return;

    let cancelled = false;
    const checkWizard = async () => {
      try {
        const requested = await shouldShowWizard();
        // A broken connection on an installed display belongs to Displays.
        // Setup is only for an empty hub (including the old seed placeholder).
        const shouldShow = requested && (await api.getBoardSettings()).boards.every(isUntouchedPlaceholder);
        if (!cancelled) setIsWizardActive(shouldShow);
      } catch (error) {
        console.error("Failed to check wizard status:", error);
        if (!cancelled) setIsWizardActive(false);
      } finally {
        if (!cancelled) setHasChecked(true);
      }
    };

    checkWizard();
    return () => {
      cancelled = true;
    };
  }, [isOnAuthScreen]);

  const triggerWizard = useCallback(() => {
    const request = ++rerunRequest.current;
    // Check before changing visibility: a pending fleet read must never
    // replace the app with a wizard and then take it away again.
    void api
      .getBoardSettings()
      .then(({ boards }) => {
        if (request !== rerunRequest.current || isOnAuthScreen || !boards.every(isUntouchedPlaceholder)) return;
        clearWizardCompletion();
        setIsWizardActive(true);
      })
      .catch((error) => {
        console.error("Failed to check displays before setup:", error);
        if (request === rerunRequest.current) toast.error(t("eligibilityFailed"));
      });
  }, [isOnAuthScreen, t]);

  const handleComplete = useCallback(() => {
    rerunRequest.current++;
    setIsWizardActive(false);
  }, []);

  // On /login we never render the wizard: that page owns its own UI and the
  // wizard's API probe isn't authorized there yet. Hand control back to the
  // children (the login page) immediately — no loading screen, no wizard.
  if (isOnAuthScreen) {
    return <WizardContext.Provider value={{ isWizardActive: false, triggerWizard }}>{children}</WizardContext.Provider>;
  }

  // Show loading state while checking
  if (!hasChecked) {
    return (
      <Flex align="center" justify="center" className="fixed inset-0 bg-background">
        <Box className="text-center">
          <Spinner size="lg" className="size-8 text-primary" label={null} />
          <Text tone="muted" className="mt-4">
            {t("loading")}
          </Text>
        </Box>
      </Flex>
    );
  }

  // Show full-screen wizard if active (replaces all content)
  if (isWizardActive) {
    return (
      <WizardContext.Provider value={{ isWizardActive, triggerWizard }}>
        <SetupWizard onComplete={handleComplete} />
      </WizardContext.Provider>
    );
  }

  // Show normal app content
  return <WizardContext.Provider value={{ isWizardActive, triggerWizard }}>{children}</WizardContext.Provider>;
}
