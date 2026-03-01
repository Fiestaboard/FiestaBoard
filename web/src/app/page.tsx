"use client";

import { useEffect, useState } from "react";
import { ActivePageDisplay } from "@/components/active-page-display";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Info } from "lucide-react";
import { getSetupStatus } from "@/lib/setup-detection";
import { useWizard } from "@/components/wizard-provider";

export default function Home() {
  const [boardNotConfigured, setBoardNotConfigured] = useState(false);
  const { triggerWizard } = useWizard();

  useEffect(() => {
    getSetupStatus()
      .then((status) => {
        if (status && !status.valid) {
          setBoardNotConfigured(true);
        }
      })
      .catch(() => {
        // Silently ignore - getSetupStatus already logs errors
      });
  }, []);

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="mb-4 sm:mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Dashboard
          </h1>
          <p className="text-muted-foreground mt-1 text-sm sm:text-base">
            Monitor your board display and system activity
          </p>
        </div>

        {boardNotConfigured && (
          <div className="mb-4 sm:mb-6">
            <Alert className="border-info/50 bg-info/10">
              <Info className="h-4 w-4 text-info" />
              <AlertTitle>No board configured</AlertTitle>
              <AlertDescription className="flex flex-col sm:flex-row sm:items-center gap-2">
                <span>
                  Your board is not set up yet. Connect your board to start displaying content.
                </span>
                <Button variant="outline" size="sm" onClick={triggerWizard} className="w-fit">
                  Run Setup Wizard
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        )}

        <div className="animate-card-fade-in">
          <ActivePageDisplay />
        </div>
      </div>
    </div>
  );
}
