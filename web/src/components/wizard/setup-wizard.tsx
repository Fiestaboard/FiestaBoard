"use client";

import { Box, Button, Flex, Text, WizardShell } from "@fiestaboard/ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { LanguageSelector } from "@/components/language-selector";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { appUrl } from "@/lib/base-path";
import type { WizardProgress } from "@/lib/setup-detection";
import { clearWizardProgress, getWizardProgress, markWizardComplete, saveWizardProgress } from "@/lib/setup-detection";

import { type BoardConfig, StepBoardSetup } from "./step-board-setup";
import { StepChooseOutput } from "./step-choose-output";
import type { WizardPluginConfig } from "./step-easy-plugins";
import { StepEasyPlugins } from "./step-easy-plugins";
import type { WizardCreatedBoard, WizardOutputChoice } from "./step-output-plugin";
import { StepOutputPlugin } from "./step-output-plugin";
import { StepPanelSetup } from "./step-panel-setup";
import { StepWelcome } from "./step-welcome";

/**
 * The Vestaboard connection saved progress carries: its `output_config`, or —
 * in progress saved before the step moved onto the board settings screen —
 * the same fields kept flat. A wizard opened for the first time starts in
 * cloud mode, the easiest setup.
 */
function savedOutputConfig(saved: WizardProgress["boardConfig"]): Record<string, unknown> {
  if (saved?.output_config) return saved.output_config;
  const flat = {
    api_mode: saved?.api_mode ?? "cloud",
    host: saved?.host,
    local_api_key: saved?.local_api_key,
    cloud_key: saved?.cloud_key,
  };
  return Object.fromEntries(Object.entries(flat).filter(([, value]) => value));
}

interface SetupWizardProps {
  onComplete?: () => void;
}

// 1 choose the display (plan D18), 2 set it up, 3 data sources, 4 finish.
const TOTAL_STEPS = 4;

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

  // The display chosen on step 1 (plan D18), and the board the TV or
  // output-plugin step created for it.
  const [output, setOutput] = useState<WizardOutputChoice | null>(() =>
    saved?.outputId ? { id: saved.outputId, name: saved.outputName ?? saved.outputId } : null,
  );
  const [createdBoard, setCreatedBoard] = useState<WizardCreatedBoard | null>(() => saved?.createdBoard ?? null);

  // Board config state: the Vestaboard's connection is its settings
  // screen's `output_config` (progress saved before that kept the same
  // fields flat; they carry over).
  const [boardConfig, setBoardConfig] = useState<BoardConfig>(() => ({
    output_config: savedOutputConfig(saved?.boardConfig),
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
      outputId: output?.id,
      outputName: output?.name,
      createdBoard: createdBoard ?? undefined,
      boardConfig: {
        output_config: boardConfig.output_config,
        device_type: boardConfig.device_type,
        board_color: boardConfig.board_color,
        code62_glyph: boardConfig.code62_glyph,
      },
      plugins: pluginConfig,
    };
    saveWizardProgress(progress);
  }, [currentStep, output, createdBoard, boardConfig, pluginConfig]);

  // Each step starts at its heading: after Next or Back, focus moves to the
  // new step's title, so keyboard and screen-reader users are not left on a
  // button that just disappeared. Not on first render — the page has just
  // opened and focus belongs where the browser put it.
  const contentRef = useRef<HTMLDivElement>(null);
  const shownStep = useRef(currentStep);
  useEffect(() => {
    if (shownStep.current === currentStep) return;
    shownStep.current = currentStep;
    const heading = contentRef.current?.parentElement?.querySelector<HTMLElement>("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [currentStep]);

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

  const finish = useCallback(
    (outcome: "completed" | "skipped") => {
      // Kept server-side too (plan D18), so the wizard stays away in every
      // browser, not just this one. Best effort: failing to record it only
      // means the next browser may offer the wizard again.
      void api.setWizardState(outcome).catch(() => undefined);
      markWizardComplete();
      clearWizardProgress();
      onComplete?.();
      router.push("/");
    },
    [onComplete, router],
  );
  const handleComplete = useCallback(() => finish("completed"), [finish]);
  const handleSkip = useCallback(() => finish("skipped"), [finish]);

  const renderSetupStep = () => {
    if (output?.id === "fiestapanel") {
      return (
        <StepPanelSetup
          created={createdBoard}
          onCreated={setCreatedBoard}
          onValidChange={setCanProceed}
          setIsLoading={setIsLoading}
        />
      );
    }
    if (output && output.id !== "vestaboard") {
      return (
        <StepOutputPlugin
          key={output.id}
          output={output}
          created={createdBoard}
          onCreated={setCreatedBoard}
          onValidChange={setCanProceed}
          setIsLoading={setIsLoading}
        />
      );
    }
    return (
      <StepBoardSetup
        config={boardConfig}
        onConfigChange={setBoardConfig}
        onValidChange={setCanProceed}
        isLoading={isLoading}
        setIsLoading={setIsLoading}
      />
    );
  };

  // Render step content
  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return (
          <StepChooseOutput
            value={output?.id ?? null}
            onChange={(chosen) => setOutput({ id: chosen.id, name: chosen.name })}
            onSkip={handleSkip}
            onValidChange={setCanProceed}
          />
        );
      case 2:
        return renderSetupStep();
      case 3:
        return <StepEasyPlugins config={pluginConfig} onConfigChange={setPluginConfig} onValidChange={setCanProceed} />;
      case 4:
        return (
          <StepWelcome
            boardConfig={boardConfig}
            pluginConfig={pluginConfig}
            output={output}
            createdBoard={createdBoard}
            onComplete={handleComplete}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
          />
        );
      default:
        return null;
    }
  };

  // Step titles: the set-up step is named for the display chosen.
  const setupTitle =
    output?.id === "fiestapanel"
      ? t("stepTitles.setUpTv")
      : output && output.id !== "vestaboard"
        ? t("stepTitles.setUpOutput", { name: output.name })
        : t("stepTitles.connectBoard");
  const setupDescription =
    output?.id === "fiestapanel"
      ? t("stepDescriptions.setUpTv")
      : output && output.id !== "vestaboard"
        ? t("stepDescriptions.setUpOutput")
        : t("stepDescriptions.enterCredentials");
  const stepTitles = [t("stepTitles.chooseOutput"), setupTitle, t("stepTitles.addDataSources"), t("stepTitles.allSet")];

  const stepDescriptions = [
    t("stepDescriptions.chooseOutput"),
    setupDescription,
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
      steps={[t("progressDisplay"), t("progressConnect"), t("progressCustomize"), t("progressFinish")]}
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

            {/* Step 1 offers "I'll add a display later" in its own content. */}
            {currentStep === 2 && (
              <Button variant="ghost" onClick={handleSkip} disabled={isLoading} size="lg">
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
      <Box ref={contentRef}>{renderStep()}</Box>
    </WizardShell>
  );
}
