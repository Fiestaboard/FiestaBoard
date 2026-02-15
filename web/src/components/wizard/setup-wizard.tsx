"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { 
  saveWizardProgress, 
  getWizardProgress, 
  markWizardComplete,
  clearWizardProgress,
  WizardProgress 
} from "@/lib/setup-detection";
import { StepBoardSetup } from "./step-board-setup";
import { StepEasyPlugins } from "./step-easy-plugins";
import { StepWelcome } from "./step-welcome";

interface SetupWizardProps {
  onComplete?: () => void;
}

const TOTAL_STEPS = 3;

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const router = useRouter();
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
  }>({
    api_mode: "cloud",
    local_api_key: "",
    cloud_key: "",
    host: "",
    connectionVerified: false,
  });

  // Plugin config state
  const [pluginConfig, setPluginConfig] = useState<{
    date_time: { enabled: boolean; timezone: string };
    star_trek_quotes: { enabled: boolean; ratio: string };
    guest_wifi: { enabled: boolean; ssid: string; password: string };
  }>({
    date_time: { enabled: true, timezone: "America/Los_Angeles" },
    star_trek_quotes: { enabled: false, ratio: "3:5:9" },
    guest_wifi: { enabled: false, ssid: "", password: "" },
  });

  // Restore progress on mount
  useEffect(() => {
    const saved = getWizardProgress();
    if (saved) {
      setCurrentStep(saved.currentStep);
      if (saved.boardConfig) {
        setBoardConfig(prev => ({
          ...prev,
          api_mode: saved.boardConfig!.api_mode,
          local_api_key: saved.boardConfig!.local_api_key || "",
          cloud_key: saved.boardConfig!.cloud_key || "",
          host: saved.boardConfig!.host || "",
        }));
      }
      if (saved.plugins) {
        setPluginConfig(prev => ({
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
      },
      plugins: pluginConfig,
    };
    saveWizardProgress(progress);
  }, [currentStep, boardConfig, pluginConfig]);

  const handleNext = useCallback(() => {
    if (currentStep < TOTAL_STEPS) {
      setCurrentStep(prev => prev + 1);
      setCanProceed(false);
    }
  }, [currentStep]);

  const handleBack = useCallback(() => {
    if (currentStep > 1) {
      setCurrentStep(prev => prev - 1);
    }
  }, [currentStep]);

  const handleComplete = useCallback(() => {
    markWizardComplete();
    clearWizardProgress();
    onComplete?.();
    // Redirect to home dashboard
    router.push("/");
    // Reload to ensure fresh state
    window.location.reload();
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
        return (
          <StepEasyPlugins
            config={pluginConfig}
            onConfigChange={setPluginConfig}
            onValidChange={setCanProceed}
          />
        );
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
  const stepTitles = [
    "Connect Your Board",
    "Add Data Sources",
    "You're All Set!",
  ];

  const stepDescriptions = [
    "Enter your board credentials to get started",
    "Enable optional features that work right away",
    "Send a test message to your board",
  ];

  return (
    <div className="fixed inset-0 z-50 bg-background">
      {/* Gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-primary/10" />
      
      {/* Content container */}
      <div className="relative h-full flex flex-col">
        {/* Header */}
        <header className="flex-shrink-0 px-4 sm:px-6 pt-6 sm:pt-10 pb-4">
          <div className="max-w-lg mx-auto text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-primary/10 mb-4 overflow-hidden">
              <Image
                src="/icons/icon-96x96.png"
                alt="FiestaBoard"
                width={48}
                height={48}
                className="w-10 h-10 sm:w-12 sm:h-12"
              />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Welcome to FiestaBoard
            </h1>
            <p className="text-muted-foreground mt-2 text-sm sm:text-base">
              Let&apos;s get you set up in just a few steps
            </p>
          </div>
        </header>

        {/* Progress indicator */}
        <div className="flex-shrink-0 px-4 sm:px-6 pb-4">
          <div className="max-w-lg mx-auto">
            <div className="flex items-center gap-2">
              {[1, 2, 3].map((step) => (
                <div
                  key={step}
                  className={cn(
                    "flex-1 h-2 rounded-full transition-all duration-500",
                    step <= currentStep 
                      ? "bg-primary" 
                      : "bg-muted"
                  )}
                />
              ))}
            </div>
            <div className="flex justify-between mt-2 text-xs text-muted-foreground">
              <span>Connect</span>
              <span>Customize</span>
              <span>Finish</span>
            </div>
          </div>
        </div>

        {/* Main content area - scrollable */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-6">
          <div className="max-w-lg mx-auto pb-6">
            {/* Step header */}
            <div className="mb-6">
              <h2 className="text-xl sm:text-2xl font-semibold">
                {stepTitles[currentStep - 1]}
              </h2>
              <p className="text-muted-foreground mt-1">
                {stepDescriptions[currentStep - 1]}
              </p>
            </div>

            {/* Step content */}
            {renderStep()}

            {/* Navigation - inline with content */}
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-border/50">
              <div>
                {currentStep > 1 && (
                  <Button 
                    variant="ghost" 
                    onClick={handleBack} 
                    disabled={isLoading}
                    size="lg"
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Back
                  </Button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                  Step {currentStep} of {TOTAL_STEPS}
                </span>

                {currentStep < TOTAL_STEPS && (
                  <Button 
                    onClick={handleNext} 
                    disabled={!canProceed || isLoading}
                    size="lg"
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

