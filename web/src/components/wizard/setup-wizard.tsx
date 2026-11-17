"use client";

import { Alert, AlertDescription, Button, Flex, Grid, Input, Label, Stack, Text } from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { TimezonePicker } from "@/components/ui/timezone-picker";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { clearWizardProgress, getWizardProgress, markWizardComplete, saveWizardProgress } from "@/lib/setup-detection";

import { type BoardConfig, type BoardSetupHandle, StepBoardSetup } from "./step-board-setup";
import { StepChooseOutput } from "./step-choose-output";
import { StepEasyPlugins, type WizardPluginConfig } from "./step-easy-plugins";
import {
  type OutputSetupHandle,
  StepOutputPlugin,
  type WizardCreatedBoard,
  type WizardOutputChoice,
} from "./step-output-plugin";
import { type PanelSetupHandle, StepPanelSetup } from "./step-panel-setup";
import { StepWelcome } from "./step-welcome";
import { WizardFrame } from "./wizard-frame";

export function SetupWizard({ onComplete }: { onComplete?: () => void }) {
  const t = useTranslations("wizard");
  const tc = useTranslations("common");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [saved] = useState(getWizardProgress);
  const [currentStep, setCurrentStep] = useState(() => Math.min(4, Math.max(0, saved?.currentStep ?? 0)));
  const [isLoading, setIsLoading] = useState(false);
  const [canProceed, setCanProceed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<WizardOutputChoice | null>(() =>
    saved?.outputId
      ? { id: saved.outputId, name: saved.outputName ?? saved.outputId }
      : saved
        ? null
        : { id: "vestaboard", name: "Vestaboard" },
  );
  const [createdBoard, setCreatedBoard] = useState<WizardCreatedBoard | null>(() => saved?.createdBoard ?? null);
  const [boardConfig, setBoardConfig] = useState<BoardConfig>(() => ({
    output_config: saved?.boardConfig?.output_config ?? {
      api_mode: saved?.boardConfig?.api_mode ?? "local",
      host: saved?.boardConfig?.host ?? "",
      local_api_key: saved?.boardConfig?.local_api_key ?? "",
      cloud_key: saved?.boardConfig?.cloud_key ?? "",
    },
    connectionVerified: false,
    device_type: saved?.boardConfig?.device_type ?? "flagship",
    board_color: saved?.boardConfig?.board_color ?? "black",
    code62_glyph: saved?.boardConfig?.code62_glyph ?? "degree",
  }));
  const [pluginConfig, setPluginConfig] = useState<WizardPluginConfig>(() => ({
    date_time: { enabled: false, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" },
    registry_selected: [],
    ...saved?.plugins,
  }));
  const general = useQuery({ queryKey: ["wizard-general"], queryFn: api.getGeneralConfig });
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [timezoneDraft, setTimezoneDraft] = useState<string | null>(null);
  const hubName = nameDraft ?? general.data?.instance_name ?? t("intro.defaultName");
  const timezone = timezoneDraft ?? general.data?.timezone ?? pluginConfig.date_time.timezone;
  const boardStep = useRef<BoardSetupHandle>(null);
  const panelStep = useRef<PanelSetupHandle>(null);
  const outputStep = useRef<OutputSetupHandle>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const previousStep = useRef(currentStep);
  const busy = useRef(false);

  useEffect(() => {
    saveWizardProgress({
      currentStep,
      outputId: output?.id,
      outputName: output?.name,
      createdBoard: createdBoard ?? undefined,
      boardConfig,
      plugins: pluginConfig,
    });
  }, [currentStep, output, createdBoard, boardConfig, pluginConfig]);
  useEffect(() => {
    if (previousStep.current === currentStep) return;
    previousStep.current = currentStep;
    contentRef.current?.closest("[data-slot=card]")?.querySelector<HTMLElement>("h1")?.focus();
  }, [currentStep]);

  const finish = useCallback(
    (outcome: "completed" | "skipped", destination: "/" | "/settings/system" = "/") => {
      void api.setWizardState(outcome).catch(() => undefined);
      markWizardComplete();
      clearWizardProgress();
      onComplete?.();
      router.push(destination);
    },
    [onComplete, router],
  );

  const next = async (skipTest = false) => {
    if (busy.current) return;
    busy.current = true;
    setError(null);
    try {
      if (currentStep === 0) {
        setIsLoading(true);
        await api.updateGeneralConfig({ instance_name: hubName.trim(), timezone });
        void queryClient.invalidateQueries({ queryKey: ["all-settings"] });
        setPluginConfig((config) => ({ ...config, date_time: { ...config.date_time, timezone } }));
      }
      if (currentStep === 2) {
        if (output?.id === "vestaboard") {
          const board = await boardStep.current?.save(skipTest);
          if (!board) return;
          setCreatedBoard(board);
        } else if (output?.id === "fiestapanel") {
          const board = await panelStep.current?.save();
          if (!board) return;
          setCreatedBoard(board);
        } else if (output && createdBoard?.outputId !== output.id) {
          const board = await outputStep.current?.save(skipTest);
          if (!board) return;
          setCreatedBoard(board);
        }
      }
      setCurrentStep((step) => step + 1);
      setCanProceed(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t("intro.saveFailed"));
    } finally {
      busy.current = false;
      setIsLoading(false);
    }
  };
  const back = () => {
    setCanProceed(false);
    setCurrentStep((step) => Math.max(0, step - 1));
  };
  const titles = [
    t("welcomeTitle"),
    t("stepTitles.chooseOutput"),
    output?.id === "fiestapanel"
      ? t("stepTitles.setUpTv")
      : output && output.id !== "vestaboard"
        ? t("stepTitles.setUpOutput", { name: output.name })
        : t("stepTitles.connectBoard"),
    t("stepTitles.addDataSources"),
    t("stepTitles.review"),
  ];
  const descriptions = [
    t("intro.description"),
    t("stepDescriptions.chooseOutput"),
    output?.id === "fiestapanel"
      ? t("stepDescriptions.setUpTv")
      : output && output.id !== "vestaboard"
        ? t("stepDescriptions.setUpOutput")
        : t("stepDescriptions.enterCredentials"),
    t("stepDescriptions.optionalIntegrations"),
    t("stepDescriptions.review"),
  ];

  return (
    <WizardFrame
      current={currentStep}
      steps={[t("progressDisplay"), t("progressConnect"), t("progressCustomize"), t("progressFinish")]}
      title={titles[currentStep]}
      description={descriptions[currentStep]}
      hub={`${hubName} · ${window.location.hostname}`}
      progressLabel={t("progressLabel")}
      eyebrow={currentStep ? t("stepOf", { current: currentStep, total: 4 }) : undefined}
      footer={
        currentStep < 4 ? (
          <Flex
            justify="between"
            gap="2"
            className="mt-2 flex-col-reverse md:flex-row [&_button]:max-md:min-h-11 [&_button]:max-md:w-full"
          >
            {currentStep === 0 ? (
              <Button
                variant="ghost"
                onClick={() => {
                  finish("skipped", "/settings/system");
                }}
              >
                {t("intro.restore")}
              </Button>
            ) : (
              <Button variant="outline" onClick={back} disabled={isLoading}>
                {tc("back")}
              </Button>
            )}
            <Flex gap="2" className="flex-col-reverse md:flex-row">
              {currentStep === 1 && (
                <Button variant="ghost" disabled={isLoading} onClick={() => finish("skipped")}>
                  {t("chooseOutput.skipTitle")}
                </Button>
              )}
              {currentStep === 2 && (
                <Button variant="ghost" disabled={isLoading} onClick={() => void next(true)}>
                  {t("skipForNow")}
                </Button>
              )}
              {currentStep === 3 && (
                <Button
                  variant="ghost"
                  disabled={isLoading}
                  onClick={() => {
                    setPluginConfig((config) => ({
                      ...config,
                      date_time: { ...config.date_time, enabled: false },
                      registry_selected: [],
                    }));
                    setCurrentStep(4);
                  }}
                >
                  {t("skipForNow")}
                </Button>
              )}
              <Button
                disabled={isLoading || (currentStep === 0 ? !hubName.trim() : !canProceed)}
                onClick={() => void next()}
              >
                {currentStep === 0 ? t("intro.start") : t("continue")}
              </Button>
            </Flex>
          </Flex>
        ) : null
      }
    >
      <Stack gap="4" ref={contentRef}>
        {currentStep === 0 && (
          <>
            <Grid gap="1.5">
              <Label htmlFor="wizard-hub-name">{t("intro.name")}</Label>
              <Input
                id="wizard-hub-name"
                maxLength={100}
                value={hubName}
                onChange={(event) => setNameDraft(event.target.value)}
              />
              <Text size="xs" tone="muted">
                {t("intro.nameHint")}
              </Text>
            </Grid>
            <Grid gap="1.5">
              <Label htmlFor="wizard-timezone">{t("intro.timezone")}</Label>
              <TimezonePicker id="wizard-timezone" value={timezone} onChange={setTimezoneDraft} />
              <Text size="xs" tone="muted">
                {t("intro.timezoneHint")}
              </Text>
            </Grid>
          </>
        )}
        {currentStep === 1 && (
          <StepChooseOutput
            value={output?.id ?? null}
            onChange={(chosen) => {
              setOutput({ id: chosen.id, name: chosen.name });
              if (output?.id !== chosen.id) setCreatedBoard(null);
            }}
            onValidChange={setCanProceed}
          />
        )}
        {currentStep === 2 &&
          (output?.id === "fiestapanel" ? (
            <StepPanelSetup
              ref={panelStep}
              hideCreate
              created={createdBoard}
              onCreated={setCreatedBoard}
              onValidChange={setCanProceed}
              setIsLoading={setIsLoading}
            />
          ) : output && output.id !== "vestaboard" ? (
            <StepOutputPlugin
              ref={outputStep}
              hideCreate
              key={output.id}
              output={output}
              created={createdBoard}
              onCreated={setCreatedBoard}
              onValidChange={setCanProceed}
              setIsLoading={setIsLoading}
            />
          ) : (
            <StepBoardSetup
              ref={boardStep}
              createdBoardId={createdBoard?.outputId === "vestaboard" ? createdBoard.boardId : undefined}
              config={boardConfig}
              onConfigChange={setBoardConfig}
              onValidChange={setCanProceed}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
            />
          ))}
        {currentStep === 3 && (
          <StepEasyPlugins config={pluginConfig} onConfigChange={setPluginConfig} onValidChange={setCanProceed} />
        )}
        {currentStep === 4 && (
          <>
            <StepWelcome
              hub={{ name: hubName, timezone }}
              boardConfig={boardConfig}
              pluginConfig={pluginConfig}
              output={output}
              createdBoard={createdBoard}
              onComplete={() => finish("completed")}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              onBack={back}
            />
          </>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </Stack>
    </WizardFrame>
  );
}
