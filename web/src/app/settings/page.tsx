"use client";

import { DisplaySettings } from "@/components/settings/display-settings";
import { TransitionSettings } from "@/components/settings/transition-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { SystemUpdate } from "@/components/settings/system-update";
import { GeneralSettings } from "@/components/general-settings";
import { useWizard } from "@/components/wizard-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Wand2, ChevronDown, SlidersHorizontal } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useState } from "react";

export default function SettingsPage() {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const { triggerWizard } = useWizard();

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="space-y-6 sm:space-y-8">
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <h1 className="page-title flex items-center gap-3">
            <SlidersHorizontal className="h-7 w-7 text-brand-emphasis" />
            Settings
          </h1>
          <p className="page-description">
            Configure your FiestaBoard service
          </p>
        </div>
          {/* Update alert banner */}
          <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
            <SystemUpdate />
          </div>

          {/* General Settings & Service Control */}
          <div className="animate-card-fade-in" style={{ animationDelay: "150ms" }}>
            <GeneralSettings />
          </div>

          {/* Boards */}
          <div className="animate-card-fade-in" style={{ animationDelay: "300ms" }}>
            <DisplaySettings />
          </div>

          {/* Board Transitions */}
          <div className="animate-card-fade-in" style={{ animationDelay: "400ms" }}>
            <TransitionSettings />
          </div>

          {/* Advanced: Debug & Setup Wizard - progressive disclosure */}
          <Card className="animate-card-fade-in overflow-hidden" style={{ animationDelay: "500ms" }}>
            <Collapsible
              open={advancedOpen}
              onOpenChange={setAdvancedOpen}
            >
              <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset">
                <h2 className="text-base font-semibold">Advanced</h2>
                <ChevronDown className={`h-5 w-5 text-muted-foreground transition-transform duration-200 ${advancedOpen ? "rotate-180" : ""}`} />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="space-y-6 px-6 pb-6">
                  <DebugSettings />
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Wand2 className="h-4 w-4" />
                        Setup Wizard
                      </CardTitle>
                      <CardDescription>
                        Re-run the setup wizard to reconfigure your board connection and basic settings.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button variant="brand" onClick={triggerWizard} className="gap-2 btn-lift">
                        <Wand2 className="h-4 w-4" />
                        Run Setup Wizard
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </Card>
        </div>
      </div>
    </div>
  );
}
