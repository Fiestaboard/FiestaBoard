"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Box,
  Flex,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import type { AIProvider, AISettings } from "@/lib/api";
import { api } from "@/lib/api";

type ProviderPreset = {
  label: string;
  base_url: string;
  protocol: "openai" | "anthropic";
  group: "cloud" | "local";
};

// BYO-key cloud providers and local servers that fully honor the
// OpenAI chat-completions wire format (including `response_format:
// json_object`, which the page generator relies on) or the native
// Anthropic Messages API. Adding one here is the only step needed
// — the backend protocol adapters in src/ai/protocols.py already
// cover every entry below.
const PROVIDER_PRESETS: ProviderPreset[] = [
  // Cloud — meta-router + first-party APIs.
  { label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", protocol: "openai", group: "cloud" },
  { label: "OpenAI", base_url: "https://api.openai.com/v1", protocol: "openai", group: "cloud" },
  { label: "Anthropic", base_url: "https://api.anthropic.com/v1", protocol: "anthropic", group: "cloud" },
  { label: "Groq", base_url: "https://api.groq.com/openai/v1", protocol: "openai", group: "cloud" },
  { label: "DeepSeek", base_url: "https://api.deepseek.com/v1", protocol: "openai", group: "cloud" },
  { label: "Mistral", base_url: "https://api.mistral.ai/v1", protocol: "openai", group: "cloud" },
  { label: "Together AI", base_url: "https://api.together.xyz/v1", protocol: "openai", group: "cloud" },
  { label: "Fireworks AI", base_url: "https://api.fireworks.ai/inference/v1", protocol: "openai", group: "cloud" },
  // Local — common self-hosted servers.
  { label: "Ollama", base_url: "http://localhost:11434/v1", protocol: "openai", group: "local" },
  { label: "LM Studio", base_url: "http://localhost:1234/v1", protocol: "openai", group: "local" },
  { label: "llama.cpp", base_url: "http://localhost:8080/v1", protocol: "openai", group: "local" },
  { label: "vLLM", base_url: "http://localhost:8000/v1", protocol: "openai", group: "local" },
];

function emptyProvider(): AIProvider {
  return {
    id: `provider-${Math.random().toString(36).slice(2, 10)}`,
    name: "",
    protocol: "openai",
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
  expanded: boolean;
  onToggleExpanded: (open: boolean) => void;
  onChange: (next: AIProvider) => void;
  onRemove: () => void;
  onMakeDefault: () => void;
}

function ProviderRow({
  provider,
  isDefault,
  expanded,
  onToggleExpanded,
  onChange,
  onRemove,
  onMakeDefault,
}: ProviderRowProps) {
  const [showKey, setShowKey] = useState(false);
  const [modelInput, setModelInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

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
      default_model: provider.default_model === model ? nextModels[0] : provider.default_model,
    };
    onChange(next);
  };

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testAiProvider({
        provider_id: provider.id,
        provider,
      });
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

  const summaryName = provider.name.trim() || "Unnamed provider";
  const modelCount = provider.models.length;

  return (
    <Collapsible open={expanded} onOpenChange={onToggleExpanded} className="rounded-md border">
      <Flex align="center" justify="between" gap="2" className="p-2">
        <CollapsibleTrigger className="flex flex-1 items-center gap-2 min-w-0 text-left rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
              expanded ? "rotate-180" : ""
            }`}
          />
          <Text as="span" size="sm" weight="medium" className="truncate">
            {summaryName}
          </Text>
          {isDefault && (
            <Badge variant="default" className="h-5 text-[10px] shrink-0">
              Default
            </Badge>
          )}
          {provider.protocol === "anthropic" && (
            <Badge variant="outline" className="h-5 text-[10px] shrink-0">
              Anthropic
            </Badge>
          )}
          <Text as="span" tone="muted" className="text-[11px] shrink-0">
            {modelCount === 0 ? "no models" : `${modelCount} model${modelCount === 1 ? "" : "s"}`}
          </Text>
        </CollapsibleTrigger>
        <Flex align="center" gap="1.5" className="shrink-0">
          {!isDefault && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7"
              onClick={onMakeDefault}
              disabled={provider.models.length === 0}
              title={provider.models.length === 0 ? "Add at least one model first" : "Make this the default provider"}
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
        </Flex>
      </Flex>

      <CollapsibleContent>
        <Stack gap="3" className="border-t p-3">
          <Stack gap="1.5">
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
          </Stack>

          <Stack gap="1.5">
            <Label htmlFor={`protocol-${provider.id}`} className="text-xs">
              Protocol
            </Label>
            <Select
              value={provider.protocol ?? "openai"}
              onValueChange={(value) =>
                onChange({
                  ...provider,
                  protocol: value as "openai" | "anthropic",
                })
              }
            >
              <SelectTrigger id={`protocol-${provider.id}`} className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openai">
                  OpenAI-compatible (OpenAI, OpenRouter, Groq, DeepSeek, Mistral, Together, Fireworks, Ollama, LM
                  Studio, vLLM, …)
                </SelectItem>
                <SelectItem value="anthropic">Anthropic (Messages API)</SelectItem>
              </SelectContent>
            </Select>
          </Stack>

          <Stack gap="1.5">
            <Label htmlFor={`url-${provider.id}`} className="text-xs">
              Base URL
            </Label>
            <Input
              id={`url-${provider.id}`}
              value={provider.base_url}
              onChange={(e) => onChange({ ...provider, base_url: e.target.value })}
              placeholder="https://openrouter.ai/api/v1"
              className="h-8 font-mono text-xs"
            />
            <Stack gap="1" className="rounded-md border border-dashed bg-muted/30 p-2">
              <Text weight="medium" tone="muted" className="text-[10px] uppercase tracking-wide">
                Quick presets
              </Text>
              {(["cloud", "local"] as const).map((group) => {
                const presets = PROVIDER_PRESETS.filter((p) => p.group === group);
                return (
                  <Flex key={group} wrap align="center" gap="1">
                    <Text as="span" tone="muted" className="text-[10px] uppercase tracking-wide pr-1 w-10">
                      {group === "cloud" ? "Cloud" : "Local"}
                    </Text>
                    {presets.map((preset) => (
                      <Button
                        key={preset.label}
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-[11px]"
                        onClick={() =>
                          onChange({
                            ...provider,
                            base_url: preset.base_url,
                            protocol: preset.protocol,
                            // Only fill the name if the user hasn't typed one
                            // — don't clobber a custom label on a re-click.
                            name: provider.name.trim() ? provider.name : preset.label,
                          })
                        }
                      >
                        {preset.label}
                      </Button>
                    ))}
                  </Flex>
                );
              })}
            </Stack>
          </Stack>

          <Stack gap="1.5">
            <Label htmlFor={`key-${provider.id}`} className="text-xs">
              API Key
            </Label>
            <Box className="relative">
              <KeyRound className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                id={`key-${provider.id}`}
                type={showKey ? "text" : "password"}
                value={provider.api_key}
                onChange={(e) => onChange({ ...provider, api_key: e.target.value })}
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
                {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </Button>
            </Box>
          </Stack>

          <Stack gap="1.5">
            <Label className="text-xs">Models</Label>
            <Flex gap="1.5">
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
                onBlur={addModel}
                className="h-8 font-mono text-xs"
              />
              <Button type="button" size="sm" variant="outline" className="h-8" onClick={addModel}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </Flex>
            {provider.models.length > 0 && (
              <Flex wrap gap="1" className="pt-1">
                {provider.models.map((m) => (
                  <Badge key={m} variant="secondary" className="font-mono text-[11px] gap-1">
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
              </Flex>
            )}
          </Stack>

          {provider.models.length > 0 && (
            <Stack gap="1.5">
              <Label htmlFor={`default-${provider.id}`} className="text-xs">
                Default model
              </Label>
              <Select
                value={provider.default_model || provider.models[0]}
                onValueChange={(value) => onChange({ ...provider, default_model: value })}
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
            </Stack>
          )}

          <Flex align="center" justify="between" gap="2" className="pt-1">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 gap-1.5"
              onClick={runTest}
              disabled={testing || provider.models.length === 0 || !provider.base_url}
            >
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              <Text as="span" size="xs">
                Test connection
              </Text>
            </Button>
            {testResult && (
              <Flex
                align="center"
                gap="1"
                className={`text-xs ${testResult.ok ? "text-success" : "text-destructive"}`}
              >
                {testResult.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                <Text as="span" size="xs" tone={testResult.ok ? "success" : "destructive"} className="line-clamp-2">
                  {testResult.message}
                </Text>
              </Flex>
            )}
          </Flex>
        </Stack>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function AiSettings() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });

  const [draft, setDraft] = useState<AISettings | null>(null);
  // Per-row expansion. Empty by default — providers start collapsed and
  // show only their summary line, matching the MQTT settings card.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const setRowExpanded = (id: string, open: boolean) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (open) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const current: AISettings = draft ?? data ?? { enabled: false, providers: [], default_provider_id: null };

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
    // A freshly-added provider has nothing to summarize yet, so open it
    // immediately for editing.
    setRowExpanded(provider.id, true);
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
        <Flex align="start" justify="between" gap="2">
          <Box>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              AI Providers
            </CardTitle>
            <CardDescription>
              Configure OpenAI-compatible LLMs for the &ldquo;Gen AI&rdquo; page generator. BYO-LLM: FiestaBoard never
              bundles a key.
            </CardDescription>
          </Box>
          <Flex align="center" gap="2" className="pt-1">
            <Label htmlFor="ai-enabled" className="text-xs">
              {current.enabled ? "Enabled" : "Disabled"}
            </Label>
            <Switch
              id="ai-enabled"
              checked={current.enabled}
              onCheckedChange={toggleEnabled}
              disabled={saveMutation.isPending}
            />
          </Flex>
        </Flex>
      </CardHeader>
      <CardContent className="space-y-3">
        <Alert>
          <AlertDescription className="text-xs">
            Your prompts and the variable list of your enabled plugins are sent directly to the provider you configure.
            API keys are stored on this device and never sent anywhere else.
          </AlertDescription>
        </Alert>

        {current.providers.length === 0 ? (
          <Text tone="muted" className="rounded-md border border-dashed p-6 text-center">
            No providers configured yet.
          </Text>
        ) : (
          <Stack gap="3">
            {current.providers.map((p, idx) => (
              <ProviderRow
                key={p.id}
                provider={p}
                isDefault={p.id === current.default_provider_id}
                expanded={expandedIds.has(p.id)}
                onToggleExpanded={(open) => setRowExpanded(p.id, open)}
                onChange={(next) => updateProvider(idx, next)}
                onRemove={() => removeProvider(idx)}
                onMakeDefault={() => makeDefault(idx)}
              />
            ))}
          </Stack>
        )}

        <Flex wrap align="center" justify="between" gap="2" className="pt-1">
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={addProvider}>
            <Plus className="h-3.5 w-3.5" />
            Add provider
          </Button>
          {hasDraft && (
            <Flex gap="2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
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
            </Flex>
          )}
        </Flex>
      </CardContent>
    </Card>
  );
}
