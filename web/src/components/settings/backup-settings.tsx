"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, Download, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

interface PendingImport {
  fileName: string;
  payload: unknown;
}

export function BackupSettings() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [reinstallPlugins, setReinstallPlugins] = useState(true);
  const [pending, setPending] = useState<PendingImport | null>(null);

  const importMutation = useMutation({
    mutationFn: (vars: { payload: unknown; reinstallPlugins: boolean }) =>
      api.importBackup(vars.payload, vars.reinstallPlugins),
    onSuccess: (result) => {
      const restored = result.restored_files.length;
      const failed = result.plugins.failed.length;
      const installed = result.plugins.installed.length;
      const manualRequired = result.plugins.manual_reinstall_required ?? [];

      let msg = `Restored ${restored} file${restored === 1 ? "" : "s"}.`;
      if (installed > 0) {
        msg += ` Reinstalled ${installed} plugin${installed === 1 ? "" : "s"}.`;
      }
      if (failed > 0) {
        msg += ` ${failed} plugin${failed === 1 ? "" : "s"} could not be reinstalled — install manually.`;
      }
      toast.success(msg);

      if (manualRequired.length > 0) {
        const names = manualRequired.map((p) => p.plugin_id).join(", ");
        toast.warning(
          `${manualRequired.length} external plugin${manualRequired.length === 1 ? "" : "s"} must be reinstalled manually via Integrations: ${names}`,
          { duration: 8000 },
        );
      }

      // Invalidate every query so the UI re-fetches the restored data.
      queryClient.invalidateQueries();
    },
    onError: (err: Error) => {
      toast.error(`Import failed: ${err.message}`);
    },
  });

  const handleExport = () => {
    // Trigger a file download via a temporary anchor element.  The
    // browser handles the Content-Disposition header from the server.
    const link = document.createElement("a");
    link.href = api.exportBackupUrl();
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Backup download started");
  };

  const handleFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so selecting the same file twice still fires onChange.
    event.target.value = "";
    if (!file) return;

    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      toast.error(`Could not read file: ${(err as Error).message}`);
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      toast.error(`File is not valid JSON: ${(err as Error).message}`);
      return;
    }

    if (!parsed || typeof parsed !== "object" || !(parsed as Record<string, unknown>).fiestaboard_backup) {
      toast.error("This does not look like a FiestaBoard backup file.");
      return;
    }

    setPending({ fileName: file.name, payload: parsed });
  };

  const handleConfirmImport = () => {
    if (!pending) return;
    importMutation.mutate(
      { payload: pending.payload, reinstallPlugins },
      {
        onSettled: () => setPending(null),
      },
    );
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Database className="h-4 w-4" />
            Backup &amp; Restore
          </CardTitle>
          <CardDescription>
            Export all of your FiestaBoard configuration — board settings, pages, carousels, schedules and plugin
            configuration — as a single JSON file. Re-upload that file on a new instance to migrate or recover after an
            upgrade.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col sm:flex-row gap-3">
            <Button variant="default" className="gap-2" onClick={handleExport} disabled={importMutation.isPending}>
              <Download className="h-4 w-4" />
              Export backup
            </Button>
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => fileInputRef.current?.click()}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Import backup…
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleFileSelected}
            />
          </div>

          <div className="flex items-start gap-3 rounded-md border border-border/60 bg-muted/40 p-3">
            <Switch id="backup-reinstall-plugins" checked={reinstallPlugins} onCheckedChange={setReinstallPlugins} />
            <div className="space-y-1">
              <Label htmlFor="backup-reinstall-plugins" className="cursor-pointer">
                Reinstall external plugins after import
              </Label>
              <p className="text-xs text-muted-foreground">
                When enabled, FiestaBoard will attempt to clone any external plugins recorded in the backup that are not
                yet installed on this instance. Their configuration is restored from the backup either way.
              </p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            Note: backups contain sensitive values such as API keys and board credentials in plain text. Store the file
            securely and do not share it publicly.
          </p>
        </CardContent>
      </Card>

      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Replace current configuration?
            </AlertDialogTitle>
            <AlertDialogDescription>
              You are about to restore <span className="font-medium">{pending?.fileName}</span>. Your existing pages,
              carousels, schedules and configuration will be overwritten. A timestamped copy of each existing file is
              kept alongside the new one so you can roll back manually if needed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={importMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmImport} disabled={importMutation.isPending}>
              {importMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Restoring…
                </>
              ) : (
                "Restore backup"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
