"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sparkles, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { AIGenerateResult, AISettings, DeviceType } from "@/lib/api";

const PLACEHOLDER_PROMPT =
  "A page with the Bay Wheels station near 34th & Noriega, the weather, " +
  "and drive time to my work address.";

export interface AiPageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deviceType: DeviceType;
  /**
   * Snapshot of the editor's current page, sent to the LLM when the
   * "Use current page as starting point" checkbox is checked.
   */
  currentPage?: {
    name: string;
    template: string[];
    line_metadata: { alignment: string; wrap: boolean }[];
  };
  /** Called when the user accepts the AI-generated page. */
  onInsert: (page: AIGenerateResult["page"]) => void;
}

export function AiPageDialog({
  open,
  onOpenChange,
  deviceType,
  currentPage,
  onInsert,
}: AiPageDialogProps) {
  const [prompt, setPrompt] = useState("");
  const [providerId, setProviderId] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [useCurrentPage, setUseCurrentPage] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AIGenerateResult | null>(null);

  const { data: settings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
    enabled: open,
  });

  const providers = settings?.providers ?? [];
  const selectedProvider =
    providers.find((p) => p.id === providerId) ??
    providers.find((p) => p.id === settings?.default_provider_id) ??
    providers[0];
  const effectiveProviderId = selectedProvider?.id ?? "";
  const availableModels = selectedProvider?.models ?? [];
  const effectiveModel =
    model && availableModels.includes(model)
      ? model
      : selectedProvider?.default_model ?? availableModels[0] ?? "";

  const reset = () => {
    setPrompt("");
    setError(null);
    setResult(null);
    setUseCurrentPage(false);
    setProviderId("");
    setModel("");
  };

  const handleClose = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.generateAiPage({
        prompt: prompt.trim(),
        device_type: deviceType,
        provider_id: effectiveProviderId || undefined,
        model: effectiveModel || undefined,
        current_page:
          useCurrentPage && currentPage
            ? {
                name: currentPage.name,
                type: "template",
                device_type: deviceType,
                template: currentPage.template,
                line_metadata: currentPage.line_metadata,
              }
            : undefined,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleInsert = () => {
    if (!result) return;
    onInsert(result.page);
    handleClose(false);
  };

  const noProviders = providers.length === 0;
  const aiDisabled = settings ? !settings.enabled : false;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Gen AI page
          </DialogTitle>
          <DialogDescription>
            Describe the page you want and an LLM will draft a template.
            Review the result before saving — nothing is auto-saved.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {(noProviders || aiDisabled) && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {noProviders
                  ? "No AI providers configured. Add one in Settings → AI Providers."
                  : "AI is disabled. Enable it in Settings → AI Providers."}
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="ai-prompt">What should the page show?</Label>
            <Textarea
              id="ai-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={PLACEHOLDER_PROMPT}
              rows={4}
              disabled={generating || noProviders || aiDisabled}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ai-provider" className="text-xs">
                Provider
              </Label>
              <Select
                value={effectiveProviderId}
                onValueChange={(v) => {
                  setProviderId(v);
                  setModel("");
                }}
                disabled={providers.length <= 1}
              >
                <SelectTrigger id="ai-provider" className="h-8">
                  <SelectValue placeholder="Default provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name || p.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ai-model" className="text-xs">
                Model
              </Label>
              <Select
                value={effectiveModel}
                onValueChange={setModel}
                disabled={availableModels.length === 0}
              >
                <SelectTrigger id="ai-model" className="h-8">
                  <SelectValue placeholder="Default model" />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((m) => (
                    <SelectItem
                      key={m}
                      value={m}
                      className="font-mono text-xs"
                    >
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {currentPage && (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={useCurrentPage}
                onChange={(e) => setUseCurrentPage(e.target.checked)}
                disabled={generating}
                className="h-4 w-4"
              />
              <span>Use current page as a starting point</span>
            </label>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="break-words">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {result && (
            <div className="space-y-2 rounded-md border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{result.page.name}</div>
                <Badge variant="secondary" className="font-mono text-[10px]">
                  {result.model_used}
                </Badge>
              </div>
              <pre className="rounded bg-muted p-2 text-[11px] font-mono whitespace-pre-wrap break-all">
                {result.page.template
                  .map((line, i) => `${i + 1}: ${line || "(empty)"}`)
                  .join("\n")}
              </pre>
              {result.warnings.length > 0 && (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="text-xs font-medium mb-1">
                      Warnings:
                    </div>
                    <ul className="list-disc pl-4 text-xs space-y-0.5">
                      {result.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="ghost" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          {result && (
            <Button
              variant="outline"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Regenerate"
              )}
            </Button>
          )}
          {result ? (
            <Button variant="brand" onClick={handleInsert}>
              Insert into editor
            </Button>
          ) : (
            <Button
              variant="brand"
              onClick={handleGenerate}
              disabled={
                generating ||
                !prompt.trim() ||
                noProviders ||
                aiDisabled ||
                !effectiveProviderId ||
                !effectiveModel
              }
              className="gap-1.5"
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Generate
                </>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
