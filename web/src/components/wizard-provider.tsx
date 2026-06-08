"use client";

import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type { ReactNode } from "react";
import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useState } from "react";

import { clearWizardCompletion, shouldShowWizard } from "@/lib/setup-detection";

function WizardLoadingFallback() {
  const t = useTranslations("wizardProvider");
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <p className="mt-4 text-muted-foreground">{t("loadingSetupWizard")}</p>
      </div>
    </div>
  );
}

// Lazy load SetupWizard since it's only needed on first visit or when manually triggered
const SetupWizardLazy = lazy(() =>
  import("@/components/wizard").then((mod) => ({ default: mod.SetupWizard })),
);
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
  // wizard should appear on a freshly provisioned device.
  const isOnAuthScreen = pathname?.startsWith("/login") ?? false;
  const [isWizardActive, setIsWizardActive] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);

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
        const shouldShow = await shouldShowWizard();
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
    // Clear completion status to allow re-running
    clearWizardCompletion();
    setIsWizardActive(true);
  }, []);

  const handleComplete = useCallback(() => {
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
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <p className="mt-4 text-muted-foreground">{t("loading")}</p>
        </div>
      </div>
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
