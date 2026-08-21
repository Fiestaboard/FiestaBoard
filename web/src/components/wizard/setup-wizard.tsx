"use client";

import { Box, Button, Flex, Text, WizardShell } from "@fiestaboard/ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { LanguageSelector } from "@/components/language-selector";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type { Code62Glyph } from "@/lib/api";
import { appUrl } from "@/lib/base-path";
import type { WizardProgress } from "@/lib/setup-detection";
import { clearWizardProgress, getWizardProgress, markWizardComplete, saveWizardProgress } from "@/lib/setup-detection";

import { StepBoardSetup } from "./step-board-setup";
import type { WizardPluginConfig } from "./step-easy-plugins";
import { StepEasyPlugins } from "./step-easy-plugins";
import { StepWelcome } from "./step-welcome";

interface SetupWizardProps {
  onComplete?: () => void;
}

const TOTAL_STEPS = 3;

// Decorative split-flap field behind the wizard card. BoardBackdrop renders
// aria-hidden, so these are not user-facing copy and deliberately stay
// untranslated — they are sample board output, in the fixed-width uppercase
// vocabulary the hardware actually flips.
const BACKDROP_PHRASES = [
  "WELCOME",
  "LETS GET STARTED",
  "72 AND CLEAR",
  "N JUDAH 4 MIN",
  "SUNSET 8 04",
  "GOOD MORNING",
  "BOARD CONNECTED",
  "HELLO WORLD",
];

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const router = useRouter();
  const t = useTranslations("wizard");
  const tc = useTranslations("common");
  // Restore saved progress in the state initializers rather than a mount
  // effect. The effect version rendered step 1 with empty fields and then
  // jumped to the saved step, which also made the "save progress" effect below
  // fire once with the empty defaults (react-hooks/set-state-in-effect, issue
  // #1568). Safe because the app is a static SPA (`ssr: false`).
  // `useState(getWizardProgress)` reads localStorage exactly once.
  const [saved] = useState(getWizardProgress);

  const [currentStep, setCurrentStep] = useState(() => saved?.currentStep ?? 1);
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
    code62_glyph: Code62Glyph;
  }>(() => ({
    api_mode: saved?.boardConfig?.api_mode ?? "cloud",
    local_api_key: saved?.boardConfig?.local_api_key || "",
    cloud_key: saved?.boardConfig?.cloud_key || "",
    host: saved?.boardConfig?.host || "",
    connectionVerified: false,
    device_type: saved?.boardConfig?.device_type || "flagship",
    board_color: saved?.boardConfig?.board_color || "black",
    // "degree" preserves what every Flagship drew before Vestaboard swapped the
    // flap, so a user who skips the question is not opted into a change (#1657).
    code62_glyph: saved?.boardConfig?.code62_glyph || "degree",
  }));

  // Plugin config state
  const [pluginConfig, setPluginConfig] = useState<WizardPluginConfig>(() => ({
    date_time: { enabled: true, timezone: "America/Los_Angeles" },
    registry_selected: [],
    ...saved?.plugins,
  }));

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
        code62_glyph: boardConfig.code62_glyph,
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
    <WizardShell
      icon={
        <img
          src={appUrl("/icons/icon-96x96.png")}
          alt=""
          width={48}
          height={48}
          className="h-10 w-10 sm:h-12 sm:w-12"
        />
      }
      title={t("welcomeTitle")}
      description={t("welcomeSubtitle")}
      aside={<LanguageSelector />}
      steps={[t("progressConnect"), t("progressCustomize"), t("progressFinish")]}
      current={currentStep}
      progressLabel={t("progressLabel")}
      stepTitle={stepTitles[currentStep - 1]}
      stepDescription={stepDescriptions[currentStep - 1]}
      backdropPhrases={BACKDROP_PHRASES}
      footer={
        <>
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
        </>
      }
    >
      {renderStep()}
    </WizardShell>
  );
}
