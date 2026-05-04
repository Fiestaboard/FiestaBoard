"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Sparkles,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  Loader2,
  CheckCircle2,
  XCircle,
  KeyRound,
} from "lucide-react";
import { api } from "@/lib/api";
import type { AIProvider, AISettings } from "@/lib/api";

const PROVIDER_PRESETS: { label: string; base_url: string }[] = [
  { label: "OpenRouter", base_url: "https://openrouter.ai/api/v1" },
  { label: "OpenAI", base_url: "https://api.openai.com/v1" },
  { label: "Local (Ollama / LM Studio)", base_url: "http://localhost:11434/v1" },
];

function emptyProvider(): AIProvider {
  return {
    id: `provider-${Math.random().toString(36).slice(2, 10)}`,
    name: "",
    base_url: PROVIDER_PRESETS[0].base_url,
    api_key: "",
    models: [],
    default_model: undefined,
    headers: {},
  };
}

interface ProviderRowProps {
  provider: AIProvider;
  isDefault: boolean;
  onChange: (next: AIProvider) => void;
  onRemove: () => void;
  onMakeDefault: () => void;
}

function ProviderRow({
  provider,
  isDefault,
  onChange,
  onRemove,
  onMakeDefault,
}: ProviderRowProps) {
  const [showKey, setShowKey] = useState(false);
  const [modelInput, setModelInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<
    { ok: boolean; message: string } | null
  >(null);

  const addModel = () => {
    const trimmed = modelInput.trim();
    if (!trimmed) return;
    if (provider.models.includes(trimmed)) {
      setModelInput("");
      return;
    }
    const next = {
      ...provider,
      models: [...provider.models, trimmed],
      default_model: provider.default_model || trimmed,
    };
    onChange(next);
    setModelInput("");
  };

  const removeModel = (model: string) => {
    const nextModels = provider.models.filter((m) => m !== model);
    const next: AIProvider = {
      ...provider,
      models: nextModels,
      default_model:
        provider.default_model === model
          ? nextModels[0]
          : provider.default_model,
    };
    onChange(next);
  };

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testAiProvider({ provider_id: provider.id });
      setTestResult({ ok: result.ok, message: result.message });
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : "Test failed",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="rounded-md border p-3 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor={`name-${provider.id}`} className="text-xs">
            Name
          </Label>
          <Input
            id={`name-${provider.id}`}
            value={provider.name}
            onChange={(e) => onChange({ ...provider, name: e.target.value })}
            placeholder="OpenRouter"
            className="h-8"
          />
        </div>
        <div className="flex items-center gap-1.5 pt-5">
          {isDefault ? (
            <Badge variant="default" className="h-6">Default</Badge>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7"
              onClick={onMakeDefault}
              disabled={provider.models.length === 0}
              title={
                provider.models.length === 0
                  ? "Add at least one model first"
                  : "Make this the default provider"
              }
            >
              Make default
            </Button>
          )}
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={onRemove}
            aria-label="Remove provider"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`url-${provider.id}`} className="text-xs">
          Base URL
        </Label>
        <Input
          id={`url-${provider.id}`}
          value={provider.base_url}
          onChange={(e) =>
            onChange({ ...provider, base_url: e.target.value })
          }
          placeholder="https://openrouter.ai/api/v1"
          className="h-8 font-mono text-xs"
        />
        <div className="flex flex-wrap gap-1">
          {PROVIDER_PRESETS.map((preset) => (
            <Button
              key={preset.label}
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              onClick={() =>
                onChange({ ...provider, base_url: preset.base_url })
              }
            >
              {preset.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`key-${provider.id}`} className="text-xs">
          API Key
        </Label>
        <div className="relative">
          <KeyRound className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            id={`key-${provider.id}`}
            type={showKey ? "text" : "password"}
            value={provider.api_key}
            onChange={(e) =>
              onChange({ ...provider, api_key: e.target.value })
            }
            placeholder="sk-..."
            className="h-8 pl-7 pr-8 font-mono text-xs"
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="absolute right-0 top-0 h-8 w-8"
            onClick={() => setShowKey((v) => !v)}
            aria-label={showKey ? "Hide API key" : "Show API key"}
          >
            {showKey ? (
              <EyeOff className="h-3.5 w-3.5" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Models</Label>
        <div className="flex gap-1.5">
          <Input
            value={modelInput}
            onChange={(e) => setModelInput(e.target.value)}
            placeholder="openai/gpt-4o-mini"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addModel();
              }
            }}
            className="h-8 font-mono text-xs"
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8"
            onClick={addModel}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {provider.models.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {provider.models.map((m) => (
              <Badge
                key={m}
                variant="secondary"
                className="font-mono text-[11px] gap-1"
              >
                {m}
                <button
                  type="button"
                  onClick={() => removeModel(m)}
                  className="hover:text-destructive"
                  aria-label={`Remove model ${m}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {provider.models.length > 0 && (
        <div className="space-y-1.5">
          <Label htmlFor={`default-${provider.id}`} className="text-xs">
            Default model
          </Label>
          <Select
            value={provider.default_model || provider.models[0]}
            onValueChange={(value) =>
              onChange({ ...provider, default_model: value })
            }
          >
            <SelectTrigger id={`default-${provider.id}`} className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {provider.models.map((m) => (
                <SelectItem key={m} value={m} className="font-mono text-xs">
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 gap-1.5"
          onClick={runTest}
          disabled={
            testing || provider.models.length === 0 || !provider.base_url
          }
        >
          {testing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          <span className="text-xs">Test connection</span>
        </Button>
        {testResult && (
          <div
            className={`flex items-center gap-1 text-xs ${
              testResult.ok ? "text-success" : "text-destructive"
            }`}
          >
            {testResult.ok ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <XCircle className="h-3.5 w-3.5" />
            )}
            <span className="line-clamp-2">{testResult.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function AiSettings() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });

  const [draft, setDraft] = useState<AISettings | null>(null);

  const current: AISettings = draft ??
    data ?? { enabled: false, providers: [], default_provider_id: null };

  const saveMutation = useMutation({
    mutationFn: (next: AISettings) => api.updateAiSettings(next),
    onSuccess: (saved) => {
      queryClient.setQueryData(["ai-settings"], saved);
      setDraft(null);
      toast.success("AI provider settings saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateProvider = (idx: number, next: AIProvider) => {
    const providers = current.providers.map((p, i) => (i === idx ? next : p));
    setDraft({ ...current, providers });
  };

  const addProvider = () => {
    const provider = emptyProvider();
    const providers = [...current.providers, provider];
    setDraft({
      ...current,
      providers,
      default_provider_id: current.default_provider_id || provider.id,
    });
  };

  const removeProvider = (idx: number) => {
    const removed = current.providers[idx];
    const providers = current.providers.filter((_, i) => i !== idx);
    let default_provider_id = current.default_provider_id;
    if (removed && removed.id === default_provider_id) {
      default_provider_id = providers[0]?.id ?? null;
    }
    setDraft({ ...current, providers, default_provider_id });
  };

  const makeDefault = (idx: number) => {
    const provider = current.providers[idx];
    if (!provider) return;
    setDraft({ ...current, default_provider_id: provider.id });
  };

  const toggleEnabled = (enabled: boolean) => {
    saveMutation.mutate({ ...current, enabled });
  };

  const hasDraft = draft !== null;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              AI Providers
            </CardTitle>
            <CardDescription>
              Configure OpenAI-compatible LLMs for the &ldquo;Gen AI&rdquo;
              page generator. BYO-LLM: FiestaBoard never bundles a key.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <Label htmlFor="ai-enabled" className="text-xs">
              {current.enabled ? "Enabled" : "Disabled"}
            </Label>
            <Switch
              id="ai-enabled"
              checked={current.enabled}
              onCheckedChange={toggleEnabled}
              disabled={saveMutation.isPending}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Alert>
          <AlertDescription className="text-xs">
            Your prompts and the variable list of your enabled plugins are
            sent directly to the provider you configure. API keys are stored
            on this device and never sent anywhere else.
          </AlertDescription>
        </Alert>

        {current.providers.length === 0 ? (
          <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            No providers configured yet.
          </div>
        ) : (
          <div className="space-y-3">
            {current.providers.map((p, idx) => (
              <ProviderRow
                key={p.id}
                provider={p}
                isDefault={p.id === current.default_provider_id}
                onChange={(next) => updateProvider(idx, next)}
                onRemove={() => removeProvider(idx)}
                onMakeDefault={() => makeDefault(idx)}
              />
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={addProvider}
          >
            <Plus className="h-3.5 w-3.5" />
            Add provider
          </Button>
          {hasDraft && (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setDraft(null)}
              >
                Discard
              </Button>
              <Button
                type="button"
                variant="brand"
                size="sm"
                onClick={() => saveMutation.mutate(current)}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? "Saving..." : "Save changes"}
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
