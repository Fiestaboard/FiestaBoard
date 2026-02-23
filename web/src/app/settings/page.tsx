"use client";

import { DisplaySettings } from "@/components/settings/display-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { SystemUpdate } from "@/components/settings/system-update";
import { GeneralSettings } from "@/components/general-settings";
import { useWizard } from "@/components/wizard-provider";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Puzzle, Wand2 } from "lucide-react";

export default function SettingsPage() {
  const { triggerWizard } = useWizard();

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="mb-4 sm:mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Settings
          </h1>
          <p className="text-muted-foreground mt-1 text-sm sm:text-base">
            Configure your FiestaBoard service
          </p>
        </div>

        <div className="space-y-6 sm:space-y-8 max-w-4xl">
          {/* General Settings & Service Control */}
          <section>
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">General Settings</h2>
            <GeneralSettings />
          </section>

          {/* Boards */}
          <section>
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Boards</h2>
            <DisplaySettings />
          </section>

          {/* Integrations Link */}
          <section>
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Data Sources</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Enable and configure data source plugins for your board display.
            </p>
            <Link href="/integrations">
              <Button variant="outline" className="gap-2">
                <Puzzle className="h-4 w-4" />
                Manage Integrations
              </Button>
            </Link>
          </section>

          {/* System Update */}
          <section>
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">System Update</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Check for new versions and update your FiestaBoard installation.
            </p>
            <SystemUpdate />
          </section>

          {/* Debug Tools */}
          <section className="pt-4 border-t">
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Debug</h2>
            <DebugSettings />
          </section>

          {/* Setup Wizard - at the bottom */}
          <section className="pt-4 border-t">
            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Setup Wizard</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Re-run the setup wizard to reconfigure your board connection and basic settings.
            </p>
            <Button variant="outline" onClick={triggerWizard} className="gap-2">
              <Wand2 className="h-4 w-4" />
              Run Setup Wizard
            </Button>
          </section>
        </div>
      </div>
    </div>
  );
}
