"use client";

import {
  ActionCard,
  Alert,
  AlertDescription,
  Badge,
  Box,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Combobox,
  Field,
  Flex,
  Grid,
  Input,
  Label,
  PageSection,
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
import { SecretInput } from "@fiestaboard/ui/components/forms/secret-input";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  KeyRound,
  Loader2,
  LogIn,
  Plus,
  Server,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import {
  OAUTH_CONNECTIONS_QUERY_KEY,
  OAuthConnectionPanel,
  oauthReturnErrorKey,
  readOAuthReturn,
} from "@/components/plugin-settings";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { AIModel, AIProvider, AIProviderProtocol, AISettings, AISignInPreset } from "@/lib/api";
import { AI_TURN_CAP_MAX, AI_TURN_CAP_MIN, api } from "@/lib/api";

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

// Providers that offer a sign-in instead of a pasted API key. The board runs
// the sign-in (src/ai/sign_in.py PRESETS); choosing one here only records
// `sign_in.preset` and points the provider at the matching endpoint. The
// API key field stays: removing the sign-in falls back to it.
const SIGN_IN_PRESETS: {
  preset: AISignInPreset;
  label: string;
  base_url: string;
  protocol: AIProviderProtocol;
}[] = [
  { preset: "openrouter", label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", protocol: "openai" },
  { preset: "huggingface", label: "Hugging Face", base_url: "https://router.huggingface.co/v1", protocol: "openai" },
  { preset: "openai_chatgpt", label: "ChatGPT", base_url: "https://api.openai.com/v1", protocol: "openai_responses" },
];

/** The OAuth connection id of a signed-in AI provider. */
const aiConnectionId = (providerId: string) => `ai.${providerId}`;

/**
 * How a provider is set up, which picks the view it is edited in:
 *  - sign_in: a sign-in preset; the view is the sign-in panel and the models.
 *  - api_key: a cloud preset's endpoint; the view is the key and the models.
 *  - local: a local server preset (on any host); the view is its address and the models.
 *  - advanced: anything else; the view is the full form.
 *
 * Read from the saved fields, never stored: a provider saved by any earlier
 * version opens in whichever view matches it, and no view rewrites a field it
 * does not show. Every simple view keeps the rest of the form under Advanced.
 */
export type ProviderSetupKind = "sign_in" | "api_key" | "local" | "advanced";

const CLOUD_PRESETS = PROVIDER_PRESETS.filter((p) => p.group === "cloud");
const LOCAL_PRESETS = PROVIDER_PRESETS.filter((p) => p.group === "local");

const trimSlashes = (value: string) => value.trim().replace(/\/+$/, "").toLowerCase();

function parseUrl(value: string): URL | null {
  try {
    return new URL(value.trim());
  } catch {
    return null;
  }
}

/** The local preset whose port and path *provider* uses, on whatever host it runs. */
function localPresetFor(provider: AIProvider): ProviderPreset | undefined {
  if ((provider.protocol ?? "openai") !== "openai") return undefined;
  const url = parseUrl(provider.base_url);
  if (!url || (url.protocol !== "http:" && url.protocol !== "https:")) return undefined;
  return LOCAL_PRESETS.find((preset) => {
    const presetUrl = new URL(preset.base_url);
    return presetUrl.port === url.port && trimSlashes(presetUrl.pathname) === trimSlashes(url.pathname);
  });
}

export function providerSetupKind(provider: AIProvider): ProviderSetupKind {
  if (provider.sign_in) {
    return SIGN_IN_PRESETS.some((p) => p.preset === provider.sign_in?.preset) ? "sign_in" : "advanced";
  }
  const protocol = provider.protocol ?? "openai";
  if (
    CLOUD_PRESETS.some((p) => p.protocol === protocol && trimSlashes(p.base_url) === trimSlashes(provider.base_url))
  ) {
    return "api_key";
  }
  return localPresetFor(provider) ? "local" : "advanced";
}

const hostOf = (url: string) => parseUrl(url)?.host ?? url;

function SignInChoice({
  provider,
  saved,
  onChange,
  showPanel = true,
}: {
  provider: AIProvider;
  /** Whether the board already has this sign-in saved, so it can run it. */
  saved: boolean;
  onChange: (next: AIProvider) => void;
  /** Whether to include the sign-in panel. The sign-in view shows it on its own, above. */
  showPanel?: boolean;
}) {
  const t = useTranslations("settings.ai.signIn");
  const labelId = useId();

  if (!provider.sign_in) {
    return (
      <Stack gap="1.5" role="group" aria-labelledby={labelId}>
        <Text id={labelId} size="xs" tone="muted">
          {t("choicesLabel")}
        </Text>
        <Flex wrap gap="1.5">
          {SIGN_IN_PRESETS.map((preset) => (
            <Button
              key={preset.preset}
              type="button"
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() =>
                onChange({
                  ...provider,
                  sign_in: { preset: preset.preset },
                  base_url: preset.base_url,
                  protocol: preset.protocol,
                  name: provider.name.trim() ? provider.name : preset.label,
                })
              }
            >
              {t("button", { provider: preset.label })}
            </Button>
          ))}
        </Flex>
      </Stack>
    );
  }

  const label = SIGN_IN_PRESETS.find((p) => p.preset === provider.sign_in?.preset)?.label ?? provider.sign_in.preset;
  const useApiKey = () => {
    const next = { ...provider };
    delete next.sign_in;
    onChange(next);
  };

  return (
    <Stack gap="2" className="rounded-md border border-dashed p-3">
      <Text size="xs" tone="muted">
        {t("activeDescription", { provider: label })}
      </Text>
      {showPanel && <SignInPanel provider={provider} saved={saved} />}
      <Button type="button" size="sm" variant="link" className="h-auto self-start px-0 text-xs" onClick={useApiKey}>
        {t("useApiKey")}
      </Button>
    </Stack>
  );
}

/** A signed-in provider's account connection, or what to do before there is one. */
function SignInPanel({ provider, saved }: { provider: AIProvider; saved: boolean }) {
  const t = useTranslations("settings.ai.signIn");
  if (!provider.sign_in) return null;
  const label = SIGN_IN_PRESETS.find((p) => p.preset === provider.sign_in?.preset)?.label ?? provider.sign_in.preset;
  return saved ? (
    <OAuthConnectionPanel connectionId={aiConnectionId(provider.id)} title={t("panelTitle", { provider: label })} />
  ) : (
    <Text size="xs">{t("saveFirst", { provider: label })}</Text>
  );
}

/** What "Add provider" creates: a kind first, then (for all but advanced) which one. */
export type AddProviderPick =
  | { kind: "sign_in"; preset: (typeof SIGN_IN_PRESETS)[number] }
  | { kind: "api_key" | "local"; preset: ProviderPreset }
  | { kind: "advanced" };

function AddProviderChooser({
  onPick,
  onCancel,
  pending,
}: {
  onPick: (pick: AddProviderPick) => void;
  onCancel: () => void;
  /** The label of the sign-in preset being created, while it saves. */
  pending: string | null;
}) {
  const t = useTranslations("settings.ai.add");
  const titleId = useId();
  const [step, setStep] = useState<"kind" | "sign_in" | "api_key" | "local">("kind");
  // Each step replaces the cards, including the one just pressed, so focus
  // moves to the step's question instead of falling back to the page.
  const groupRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    groupRef.current?.focus();
  }, [step]);

  const options =
    step === "sign_in"
      ? SIGN_IN_PRESETS.map((preset) => ({
          label: preset.label,
          host: hostOf(preset.base_url),
          pick: () => onPick({ kind: "sign_in", preset }),
        }))
      : (step === "api_key" ? CLOUD_PRESETS : LOCAL_PRESETS).map((preset) => ({
          label: preset.label,
          host: hostOf(preset.base_url),
          pick: () => onPick({ kind: step === "api_key" ? "api_key" : "local", preset }),
        }));

  const title =
    step === "kind"
      ? t("title")
      : step === "sign_in"
        ? t("signInPick")
        : step === "api_key"
          ? t("apiKeyPick")
          : t("localPick");

  return (
    <Stack gap="3" className="rounded-md border p-3" data-testid="add-provider">
      <Stack ref={groupRef} tabIndex={-1} gap="2" role="group" aria-labelledby={titleId} className="outline-none">
        <Text id={titleId} size="sm" weight="medium">
          {title}
        </Text>
        <Grid cols="1" sm="2" gap="2">
          {step === "kind" ? (
            <>
              <ActionCard
                icon={<LogIn />}
                title={t("signInTitle")}
                description={t("signInDescription")}
                onClick={() => setStep("sign_in")}
              />
              <ActionCard
                icon={<KeyRound />}
                title={t("apiKeyTitle")}
                description={t("apiKeyDescription")}
                onClick={() => setStep("api_key")}
              />
              <ActionCard
                icon={<Server />}
                title={t("localTitle")}
                description={t("localDescription")}
                onClick={() => setStep("local")}
              />
              <ActionCard
                icon={<SlidersHorizontal />}
                title={t("advancedTitle")}
                description={t("advancedDescription")}
                onClick={() => onPick({ kind: "advanced" })}
              />
            </>
          ) : (
            options.map((option) => (
              <ActionCard
                key={option.label}
                title={option.label}
                description={option.host}
                loading={pending === option.label}
                disabled={pending !== null && pending !== option.label}
                onClick={option.pick}
              />
            ))
          )}
        </Grid>
      </Stack>
      <Flex gap="2">
        {step !== "kind" && (
          <Button type="button" size="sm" variant="ghost" onClick={() => setStep("kind")} disabled={pending !== null}>
            {t("back")}
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={pending !== null}>
          {t("cancel")}
        </Button>
      </Flex>
    </Stack>
  );
}

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
  /** The view a just-added provider opens in; otherwise it is read from the saved fields. */
  initialKind?: ProviderSetupKind;
  /** Whether this provider's sign-in, if any, is saved on the board. */
  signInSaved: boolean;
  /** Whether this provider is saved on the board, so its model list can be asked for. */
  saved: boolean;
  isDefault: boolean;
  expanded: boolean;
  onToggleExpanded: (open: boolean) => void;
  onChange: (next: AIProvider) => void;
  onRemove: () => void;
  onMakeDefault: () => void;
}

function ProviderRow({
  provider,
  initialKind,
  signInSaved,
  saved,
  isDefault,
  expanded,
  onToggleExpanded,
  onChange,
  onRemove,
  onMakeDefault,
}: ProviderRowProps) {
  const t = useTranslations("settings.ai");
  const [modelInput, setModelInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [offeredModels, setOfferedModels] = useState<AIModel[] | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  // Fixed for the row's life, so editing a field under Advanced never swaps
  // the view (and the field being typed in) out from under the user.
  const [kind] = useState<ProviderSetupKind>(() => initialKind ?? providerSetupKind(provider));
  // The sign-in view without a sign-in ("Use the API key instead") is the full form.
  const view: ProviderSetupKind = kind === "sign_in" && !provider.sign_in ? "advanced" : kind;
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const addModelValue = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || provider.models.includes(trimmed)) return;
    onChange({
      ...provider,
      models: [...provider.models, trimmed],
      default_model: provider.default_model || trimmed,
    });
  };

  const addModel = () => {
    addModelValue(modelInput);
    setModelInput("");
  };

  const loadModels = async () => {
    setLoadingModels(true);
    setModelsError(null);
    try {
      const { models } = await api.listAiProviderModels(provider.id);
      setOfferedModels(models);
    } catch (err) {
      setOfferedModels(null);
      setModelsError(err instanceof Error ? err.message : t("loadModelsFailed"));
    } finally {
      setLoadingModels(false);
    }
  };

  const pickable = (offeredModels ?? [])
    .filter((m) => !provider.models.includes(m.id))
    .map((m) => ({
      value: m.id,
      label: m.name === m.id ? m.id : `${m.name} (${m.id})`,
      keywords: [m.name],
    }));

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

  // The form's fields. The full form (advanced) shows them all; the simple
  // views show the few that matter and keep the rest under Advanced.
  const nameField = (
    <Stack gap="1.5">
      <Label htmlFor={`name-${provider.id}`} className="text-xs">
        {t("nameLabel")}
      </Label>
      <Input
        id={`name-${provider.id}`}
        value={provider.name}
        onChange={(e) => onChange({ ...provider, name: e.target.value })}
        placeholder="OpenRouter"
        className="h-8"
      />
    </Stack>
  );

  const protocolField = (
    <Stack gap="1.5">
      <Label htmlFor={`protocol-${provider.id}`} className="text-xs">
        {t("protocolLabel")}
      </Label>
      <Select
        value={provider.protocol ?? "openai"}
        onValueChange={(value) =>
          onChange({
            ...provider,
            protocol: value as AIProviderProtocol,
          })
        }
      >
        <SelectTrigger id={`protocol-${provider.id}`} className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="openai">{t("protocolOpenaiOption")}</SelectItem>
          <SelectItem value="anthropic">{t("protocolAnthropicOption")}</SelectItem>
          {provider.protocol === "openai_responses" && (
            <SelectItem value="openai_responses">{t("protocolResponsesOption")}</SelectItem>
          )}
        </SelectContent>
      </Select>
    </Stack>
  );

  const baseUrlField = (
    <Stack gap="1.5">
      <Label htmlFor={`url-${provider.id}`} className="text-xs">
        {t("baseUrlLabel")}
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
          {t("quickPresetsLabel")}
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
  );

  const apiKeyField = (
    <Stack gap="1.5">
      <Label htmlFor={`key-${provider.id}`} className="text-xs">
        {t("apiKeyLabel")}
      </Label>
      <Box className="relative">
        <KeyRound className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
        <SecretInput
          id={`key-${provider.id}`}
          value={provider.api_key}
          onChange={(e) => onChange({ ...provider, api_key: e.target.value })}
          placeholder="sk-..."
          showLabel="Show API key"
          hideLabel="Hide API key"
          className="h-8 pl-7 text-xs"
        />
      </Box>
    </Stack>
  );

  const addressField = (
    <Field label={t("simple.addressLabel")} description={t("simple.addressDescription")}>
      <Input
        id={`address-${provider.id}`}
        value={provider.base_url}
        onChange={(e) => onChange({ ...provider, base_url: e.target.value })}
        placeholder="http://localhost:11434/v1"
        className="h-8 font-mono text-xs"
      />
    </Field>
  );

  const signInChoice = <SignInChoice provider={provider} saved={signInSaved} onChange={onChange} />;

  const modelFields = (
    <>
      <Stack gap="1.5">
        <Flex align="center" justify="between" gap="2">
          <Label className="text-xs">{t("modelsLabel")}</Label>
          {saved && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 px-2 text-xs"
              onClick={loadModels}
              disabled={loadingModels}
            >
              {loadingModels && <Loader2 className="h-3 w-3 animate-spin" />}
              {t("loadModels")}
            </Button>
          )}
        </Flex>
        {!saved && (
          <Text size="xs" tone="muted">
            {t("simple.modelsAfterSave")}
          </Text>
        )}
        {offeredModels && (
          <Combobox
            options={pickable}
            value=""
            onValueChange={(value) => addModelValue(value)}
            aria-label={t("pickModel")}
            labels={{ placeholder: t("pickModel"), list: t("pickModel"), empty: t("noModelMatches") }}
            className="h-8 font-mono text-xs"
          />
        )}
        {modelsError && (
          <Text size="xs" tone="destructive" role="alert">
            {modelsError}
          </Text>
        )}
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
            {t("defaultModelLabel")}
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
            {t("testConnectionButton")}
          </Text>
        </Button>
        {testResult && (
          <Flex align="center" gap="1" className={`text-xs ${testResult.ok ? "text-success" : "text-destructive"}`}>
            {testResult.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
            <Text as="span" size="xs" tone={testResult.ok ? "success" : "destructive"} className="line-clamp-2">
              {testResult.message}
            </Text>
          </Flex>
        )}
      </Flex>
    </>
  );

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
              {t("defaultBadge")}
            </Badge>
          )}
          {provider.protocol === "anthropic" && (
            <Badge variant="outline" className="h-5 text-[10px] shrink-0">
              {t("anthropicBadge")}
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
              {t("makeDefaultButton")}
            </Button>
          )}
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={onRemove}
            aria-label={t("removeProviderAriaLabel")}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </Flex>
      </Flex>

      <CollapsibleContent>
        <Stack gap="3" className="border-t p-3">
          {view === "advanced" ? (
            <>
              {nameField}
              {protocolField}
              {baseUrlField}
              {apiKeyField}
              {signInChoice}
              {modelFields}
            </>
          ) : (
            <>
              {view === "sign_in" && <SignInPanel provider={provider} saved={signInSaved} />}
              {view === "api_key" && apiKeyField}
              {view === "local" && addressField}
              {modelFields}
              <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
                <CollapsibleTrigger asChild>
                  <Button type="button" size="sm" variant="link" className="h-auto px-0 text-xs">
                    {t("simple.advancedToggle")}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <Stack gap="3" className="pt-2">
                    {nameField}
                    {protocolField}
                    {view !== "local" && baseUrlField}
                    {view !== "api_key" && apiKeyField}
                    {view === "sign_in" ? (
                      <SignInChoice provider={provider} saved={signInSaved} onChange={onChange} showPanel={false} />
                    ) : (
                      signInChoice
                    )}
                  </Stack>
                </CollapsibleContent>
              </Collapsible>
            </>
          )}
        </Stack>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function AiSettings() {
  const t = useTranslations("settings.ai");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });

  const [draft, setDraft] = useState<AISettings | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const tOAuth = useTranslations("integrations.oauth");
  // Per-row expansion. Empty by default — providers start collapsed and
  // show only their summary line, matching the MQTT settings card.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  // "Add provider" asks what kind first; null while it is not open.
  const [adding, setAdding] = useState(false);
  // The view each provider added on this visit opens in.
  const [addedKinds, setAddedKinds] = useState<Map<string, ProviderSetupKind>>(new Map());

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

  // A FiestaBot sign-in lands back on Settings with its outcome in the query
  // (src/oauth/routes.py: ?oauth=…&connection=ai.<id>). Report it once, open
  // that provider's row, and clean the URL so a reload does not repeat it.
  const [aiReturn] = useState(() => {
    const outcome = readOAuthReturn(searchParams);
    const connection = searchParams.get("connection") ?? "";
    return outcome && connection.startsWith("ai.") ? { ...outcome, providerId: connection.slice(3) } : null;
  });
  const aiReturnReported = useRef(false);
  useEffect(() => {
    if (!aiReturn || aiReturnReported.current) return;
    aiReturnReported.current = true;
    if (aiReturn.outcome === "connected") {
      toast.success(tOAuth("toastConnected"));
    } else {
      toast.error(tOAuth(oauthReturnErrorKey(aiReturn.reason)));
    }
    setExpandedIds((prev) => new Set(prev).add(aiReturn.providerId));
    router.replace("/settings?section=integrations", { scroll: false });
  }, [aiReturn, router, tOAuth]);

  const current: AISettings = draft ??
    data ?? {
      enabled: false,
      providers: [],
      default_provider_id: null,
      approval_mode: "ask",
      // null, not a number: "no override, use the server's defaults".
      max_model_calls: null,
      max_tool_calls: null,
    };

  /**
   * A turn cap as typed: a whole number, or null for "no override".
   *
   * Cleared field → null, which is what lets someone go back to the server's
   * defaults after setting a number. Anything unparseable is also null rather
   * than NaN, which would serialize as JSON `null` anyway but only after
   * rendering the field blank-but-dirty on the way there.
   */
  const parseCap = (raw: string): number | null => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const value = Number(trimmed);
    return Number.isInteger(value) ? value : null;
  };

  const saveMutation = useMutation({
    // Only the fields this page edits. `approval_mode` is the chat panel's
    // pill; sending a snapshot of it here would silently revert a mode the
    // user changed in the chat meanwhile.
    mutationFn: (next: AISettings) =>
      api.updateAiSettings({
        enabled: next.enabled,
        providers: next.providers,
        default_provider_id: next.default_provider_id,
        // Edited only here, so a snapshot is safe — unlike `approval_mode`.
        // An explicit null is meaningful: it clears the override.
        max_model_calls: next.max_model_calls,
        max_tool_calls: next.max_tool_calls,
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(["ai-settings"], saved);
      // A provider that gained or lost a sign-in gains or loses its connection.
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
      setDraft(null);
      toast.success("AI provider settings saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateProvider = (idx: number, next: AIProvider) => {
    const providers = current.providers.map((p, i) => (i === idx ? next : p));
    setDraft({ ...current, providers });
  };

  const openAdded = (provider: AIProvider, kind: ProviderSetupKind) => {
    setAddedKinds((prev) => new Map(prev).set(provider.id, kind));
    // A freshly-added provider has nothing to summarize yet, so open it
    // immediately for editing.
    setRowExpanded(provider.id, true);
    setAdding(false);
  };

  const addDraftProvider = (provider: AIProvider, kind: ProviderSetupKind) => {
    setDraft({
      ...current,
      providers: [...current.providers, provider],
      default_provider_id: current.default_provider_id || provider.id,
    });
    openAdded(provider, kind);
  };

  // A sign-in provider is saved as soon as it is chosen: the board can only
  // sign in a provider it knows. Only the new provider is added to what is
  // saved; anything else being edited stays a draft, with the provider in it.
  const createSignedInMutation = useMutation({
    mutationFn: (provider: AIProvider) =>
      api.updateAiSettings({
        providers: [...(data?.providers ?? []), provider],
        default_provider_id: data?.default_provider_id || provider.id,
      }),
    onSuccess: (saved, provider) => {
      queryClient.setQueryData(["ai-settings"], saved);
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
      setDraft((prev) =>
        prev
          ? {
              ...prev,
              providers: [...prev.providers, provider],
              default_provider_id: prev.default_provider_id || provider.id,
            }
          : prev,
      );
      openAdded(provider, "sign_in");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const pickNewProvider = (pick: AddProviderPick) => {
    if (pick.kind === "advanced") {
      addDraftProvider(emptyProvider(), "advanced");
      return;
    }
    const { preset } = pick;
    const provider: AIProvider = {
      ...emptyProvider(),
      name: preset.label,
      base_url: preset.base_url,
      protocol: preset.protocol,
    };
    if (pick.kind === "sign_in") {
      createSignedInMutation.mutate({ ...provider, sign_in: { preset: pick.preset.preset } });
    } else {
      addDraftProvider(provider, pick.kind);
    }
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
      <PageSection>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="mt-2 h-4 w-64" />
      </PageSection>
    );
  }

  return (
    <PageSection
      icon={<Sparkles />}
      title={t("cardTitle")}
      description={t("cardDescription")}
      {...anchorProps("settings.ai")}
      action={
        <Flex align="center" gap="2" className="pt-1">
          <Label htmlFor="ai-enabled" className="text-xs">
            {current.enabled ? tCommon("enabled") : tCommon("disabled")}
          </Label>
          <Switch
            id="ai-enabled"
            checked={current.enabled}
            onCheckedChange={toggleEnabled}
            disabled={saveMutation.isPending}
          />
        </Flex>
      }
      contentClassName="space-y-3"
    >
      <Alert>
        <AlertDescription className="text-xs">{t("privacyNotice")}</AlertDescription>
      </Alert>

      {current.providers.length === 0 ? (
        <Text tone="muted" className="rounded-md border border-dashed p-6 text-center">
          {t("emptyState")}
        </Text>
      ) : (
        <Stack gap="3">
          {current.providers.map((p, idx) => (
            <ProviderRow
              key={p.id}
              provider={p}
              initialKind={addedKinds.get(p.id)}
              signInSaved={
                !!p.sign_in && data?.providers.find((saved) => saved.id === p.id)?.sign_in?.preset === p.sign_in.preset
              }
              saved={!!data?.providers.some((saved) => saved.id === p.id)}
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

      {/* Per-turn runaway caps. Blank means "no opinion" — the
          server's own defaults apply — so the placeholder says that rather
          than restating a number this page would then have to keep in sync
          with `TurnLimits`. Reaching a cap pauses the turn and the chat
          offers to keep going, so these are a backstop, not a work budget. */}
      <Stack gap="2" className="rounded-md border border-dashed p-3">
        <Text size="sm" weight="medium">
          {t("turnLimits.heading")}
        </Text>
        <Text size="xs" tone="muted">
          {t("turnLimits.description")}
        </Text>
        <Flex wrap gap="3">
          <Stack gap="1" className="min-w-0 flex-1">
            <Label htmlFor="ai-max-model-calls" className="text-xs">
              {t("turnLimits.modelCallsLabel")}
            </Label>
            <Input
              id="ai-max-model-calls"
              type="number"
              inputMode="numeric"
              min={AI_TURN_CAP_MIN}
              max={AI_TURN_CAP_MAX}
              value={current.max_model_calls ?? ""}
              placeholder={t("turnLimits.serverDefault")}
              onChange={(e) => setDraft({ ...current, max_model_calls: parseCap(e.target.value) })}
            />
          </Stack>
          <Stack gap="1" className="min-w-0 flex-1">
            <Label htmlFor="ai-max-tool-calls" className="text-xs">
              {t("turnLimits.toolCallsLabel")}
            </Label>
            <Input
              id="ai-max-tool-calls"
              type="number"
              inputMode="numeric"
              min={AI_TURN_CAP_MIN}
              max={AI_TURN_CAP_MAX}
              value={current.max_tool_calls ?? ""}
              placeholder={t("turnLimits.serverDefault")}
              onChange={(e) => setDraft({ ...current, max_tool_calls: parseCap(e.target.value) })}
            />
          </Stack>
        </Flex>
      </Stack>

      {adding && (
        <AddProviderChooser
          onPick={pickNewProvider}
          onCancel={() => setAdding(false)}
          pending={createSignedInMutation.isPending ? (createSignedInMutation.variables?.name ?? null) : null}
        />
      )}

      <Flex wrap align="center" justify="between" gap="2" className="pt-1">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => setAdding(true)}
          aria-expanded={adding}
        >
          <Plus className="h-3.5 w-3.5" />
          {t("addProviderButton")}
        </Button>
        {hasDraft && (
          <Flex gap="2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
              {t("discardButton")}
            </Button>
            <Button
              type="button"
              variant="brand"
              size="sm"
              onClick={() => saveMutation.mutate(current)}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? tCommon("saving") : t("saveChangesButton")}
            </Button>
          </Flex>
        )}
      </Flex>
    </PageSection>
  );
}
