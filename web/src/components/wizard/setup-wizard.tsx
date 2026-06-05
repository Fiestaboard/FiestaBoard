"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { LanguageSelector } from "@/components/language-selector";
import { Aurora } from "@/components/ui/aurora";
import { Button } from "@/components/ui/button";
import type { WizardProgress } from "@/lib/setup-detection";
import { clearWizardProgress, getWizardProgress, markWizardComplete, saveWizardProgress } from "@/lib/setup-detection";
import { cn } from "@/lib/utils";

import { StepBoardSetup } from "./step-board-setup";
import type { WizardPluginConfig } from "./step-easy-plugins";
import { StepEasyPlugins } from "./step-easy-plugins";
import { StepWelcome } from "./step-welcome";

interface SetupWizardProps {
  onComplete?: () => void;
}

const TOTAL_STEPS = 3;

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const router = useRouter();
  const t = useTranslations("wizard");
  const tc = useTranslations("common");
  const [currentStep, setCurrentStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [canProceed, setCanProceed] = useState(false);

  // Board config state
  const [boardConfig, setBoardConfig] = useState<{
    api_mode: "local" | "cloud";
    local_api_key: string;
    cloud_key: string;
    host: string;
    connectionVerified: boolean;
    device_type: "flagship" | "note";
    board_color: "black" | "white";
  }>({
    api_mode: "cloud",
    local_api_key: "",
    cloud_key: "",
    host: "",
    connectionVerified: false,
    device_type: "flagship",
    board_color: "black",
  });

  // Plugin config state
  const [pluginConfig, setPluginConfig] = useState<WizardPluginConfig>({
    date_time: { enabled: true, timezone: "America/Los_Angeles" },
    registry_selected: [],
  });

  // Restore progress on mount
  useEffect(() => {
    const saved = getWizardProgress();
    if (saved) {
      setCurrentStep(saved.currentStep);
      if (saved.boardConfig) {
        setBoardConfig((prev) => ({
          ...prev,
          api_mode: saved.boardConfig!.api_mode,
          local_api_key: saved.boardConfig!.local_api_key || "",
          cloud_key: saved.boardConfig!.cloud_key || "",
          host: saved.boardConfig!.host || "",
          device_type: saved.boardConfig!.device_type || "flagship",
          board_color: saved.boardConfig!.board_color || "black",
        }));
      }
      if (saved.plugins) {
        setPluginConfig((prev) => ({
          ...prev,
          ...saved.plugins,
        }));
      }
    }
  }, []);

  // Save progress on change
  useEffect(() => {
    const progress: WizardProgress = {
      currentStep,
      boardConfig: {
        api_mode: boardConfig.api_mode,
        local_api_key: boardConfig.local_api_key,
        cloud_key: boardConfig.cloud_key,
        host: boardConfig.host,
        device_type: boardConfig.device_type,
        board_color: boardConfig.board_color,
      },
      plugins: pluginConfig,
    };
    saveWizardProgress(progress);
  }, [currentStep, boardConfig, pluginConfig]);

  const handleNext = useCallback(() => {
    if (currentStep < TOTAL_STEPS) {
      setCurrentStep((prev) => prev + 1);
      setCanProceed(false);
    }
  }, [currentStep]);

  const handleBack = useCallback(() => {
    if (currentStep > 1) {
      setCurrentStep((prev) => prev - 1);
    }
  }, [currentStep]);

  const handleComplete = useCallback(() => {
    markWizardComplete();
    clearWizardProgress();
    onComplete?.();
    router.push("/");
  }, [onComplete, router]);

  // Render step content
  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return (
          <StepBoardSetup
            config={boardConfig}
            onConfigChange={setBoardConfig}
            onValidChange={setCanProceed}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
          />
        );
      case 2:
        return <StepEasyPlugins config={pluginConfig} onConfigChange={setPluginConfig} onValidChange={setCanProceed} />;
      case 3:
        return (
          <StepWelcome
            boardConfig={boardConfig}
            pluginConfig={pluginConfig}
            onComplete={handleComplete}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
          />
        );
      default:
        return null;
    }
  };

  // Step titles
  const stepTitles = [t("stepTitles.connectBoard"), t("stepTitles.addDataSources"), t("stepTitles.allSet")];

  const stepDescriptions = [
    t("stepDescriptions.enterCredentials"),
    t("stepDescriptions.enableFeatures"),
    t("stepDescriptions.sendTestMessage"),
  ];

  return (
    <div className="fixed inset-0 z-50 bg-background overflow-y-auto">
      {/* Aurora background - fixed so it stays in place while content scrolls */}
      <div className="fixed inset-0 pointer-events-none">
        <Aurora colorStops={["#f8e71c", "#eb4034", "#AA00FF", "#9b59b6"]} blend={0.5} amplitude={1.0} speed={0.5} />
      </div>

      {/* Content container */}
      <div className="relative min-h-full flex items-start justify-center py-6 sm:py-10 px-4 sm:px-6">
        <div className="w-full max-w-lg bg-background/75 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/10 p-6 sm:p-8">
          {/* Header */}
          <header className="text-center pb-4">
            <div className="flex items-center justify-between mb-4">
              <div />
              <div className="inline-flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-primary/10 overflow-hidden">
                <Image
                  src="/icons/icon-96x96.png"
                  alt=""
                  width={48}
                  height={48}
                  className="w-10 h-10 sm:w-12 sm:h-12"
                />
              </div>
              <LanguageSelector />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{t("welcomeTitle")}</h1>
            <p className="text-muted-foreground mt-2 text-sm sm:text-base">{t("welcomeSubtitle")}</p>
          </header>

          {/* Progress indicator */}
          <div className="pb-4">
            <div className="flex items-center gap-2">
              {[1, 2, 3].map((step) => (
                <div
                  key={step}
                  className={cn(
                    "flex-1 h-2 rounded-full transition-all duration-500",
                    step <= currentStep ? "bg-primary" : "bg-muted",
                  )}
                />
              ))}
            </div>
            <div className="flex justify-between mt-2 text-xs text-muted-foreground">
              <span>{t("progressConnect")}</span>
              <span>{t("progressCustomize")}</span>
              <span>{t("progressFinish")}</span>
            </div>
          </div>

          {/* Step header */}
          <div className="mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold">{stepTitles[currentStep - 1]}</h2>
            <p className="text-muted-foreground mt-1">{stepDescriptions[currentStep - 1]}</p>
          </div>

          {/* Step content */}
          {renderStep()}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-border">
            <div>
              {currentStep > 1 && (
                <Button variant="ghost" onClick={handleBack} disabled={isLoading} size="lg">
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  {tc("back")}
                </Button>
              )}
            </div>

            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">
                {t("stepOf", { current: currentStep, total: TOTAL_STEPS })}
              </span>

              {currentStep === 1 && (
                <Button variant="ghost" onClick={handleComplete} disabled={isLoading} size="lg">
                  {t("skipForNow")}
                </Button>
              )}

              {currentStep < TOTAL_STEPS && (
                <Button onClick={handleNext} disabled={!canProceed || isLoading} size="lg">
                  {tc("next")}
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
