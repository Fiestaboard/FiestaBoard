"use client";

import { Aurora, Box, Button, Flex, Heading, Text } from "@fiestaboard/ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { LanguageSelector } from "@/components/language-selector";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { appUrl } from "@/lib/base-path";
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
    <Box className="fixed inset-0 z-50 bg-background overflow-y-auto">
      {/* Aurora background - fixed so it stays in place while content scrolls */}
      <Box className="fixed inset-0 pointer-events-none">
        <Aurora colorStops={["#f8e71c", "#eb4034", "#AA00FF", "#9b59b6"]} blend={0.5} amplitude={1.0} speed={0.5} />
      </Box>

      {/* Content container */}
      <Flex align="start" justify="center" className="relative min-h-full py-6 sm:py-10 px-4 sm:px-6">
        <Box className="w-full max-w-lg bg-background/75 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/10 p-6 sm:p-8">
          {/* Header */}
          <Box as="header" className="text-center pb-4">
            <Flex align="center" justify="between" className="mb-4">
              <Box />
              <Flex
                inline
                align="center"
                justify="center"
                className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-primary/10 overflow-hidden"
              >
                <img
                  src={appUrl("/icons/icon-96x96.png")}
                  alt=""
                  width={48}
                  height={48}
                  className="w-10 h-10 sm:w-12 sm:h-12"
                />
              </Flex>
              <LanguageSelector />
            </Flex>
            {/* eslint-disable-next-line react/forbid-elements -- wizard hero <h1>: Heading has no level=1 and PageHeader renders an icon+card layout unfit for this centered hero title */}
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{t("welcomeTitle")}</h1>
            <Text tone="muted" className="mt-2 text-sm sm:text-base">
              {t("welcomeSubtitle")}
            </Text>
          </Box>

          {/* Progress indicator */}
          <Box className="pb-4">
            <Flex align="center" gap="2">
              {[1, 2, 3].map((step) => (
                <Box
                  key={step}
                  className={cn(
                    "flex-1 h-2 rounded-full transition-all duration-500",
                    step <= currentStep ? "bg-primary" : "bg-muted",
                  )}
                />
              ))}
            </Flex>
            <Flex justify="between" className="mt-2 text-xs text-muted-foreground">
              <Text as="span" size="xs" tone="muted">
                {t("progressConnect")}
              </Text>
              <Text as="span" size="xs" tone="muted">
                {t("progressCustomize")}
              </Text>
              <Text as="span" size="xs" tone="muted">
                {t("progressFinish")}
              </Text>
            </Flex>
          </Box>

          {/* Step header */}
          <Box className="mb-6">
            <Heading level={2} className="text-xl sm:text-2xl">
              {stepTitles[currentStep - 1]}
            </Heading>
            <Text tone="muted" className="mt-1">
              {stepDescriptions[currentStep - 1]}
            </Text>
          </Box>

          {/* Step content */}
          {renderStep()}

          {/* Navigation */}
          <Flex align="center" justify="between" className="mt-8 pt-6 border-t border-border">
            <Box>
              {currentStep > 1 && (
                <Button variant="ghost" onClick={handleBack} disabled={isLoading} size="lg">
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  {tc("back")}
                </Button>
              )}
            </Box>

            <Flex align="center" gap="3">
              <Text as="span" tone="muted">
                {t("stepOf", { current: currentStep, total: TOTAL_STEPS })}
              </Text>

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
            </Flex>
          </Flex>
        </Box>
      </Flex>
    </Box>
  );
}
