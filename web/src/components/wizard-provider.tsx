"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import dynamic from "next/dynamic";
import { shouldShowWizard, clearWizardCompletion } from "@/lib/setup-detection";
import { useTranslations } from "next-intl";

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
const SetupWizard = dynamic(
  () => import("@/components/wizard").then(mod => ({ default: mod.SetupWizard })),
  {
    ssr: false,
    loading: () => <WizardLoadingFallback />,
  }
);

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
  const [isWizardActive, setIsWizardActive] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);

  // Check if wizard should be shown on mount
  useEffect(() => {
    const checkWizard = async () => {
      try {
        const shouldShow = await shouldShowWizard();
        setIsWizardActive(shouldShow);
      } catch (error) {
        console.error("Failed to check wizard status:", error);
        setIsWizardActive(false);
      } finally {
        setHasChecked(true);
      }
    };

    checkWizard();
  }, []);

  const triggerWizard = useCallback(() => {
    // Clear completion status to allow re-running
    clearWizardCompletion();
    setIsWizardActive(true);
  }, []);

  const handleComplete = useCallback(() => {
    setIsWizardActive(false);
  }, []);

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
  return (
    <WizardContext.Provider value={{ isWizardActive, triggerWizard }}>
      {children}
    </WizardContext.Provider>
  );
}

