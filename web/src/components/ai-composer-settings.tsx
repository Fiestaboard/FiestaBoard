"use client";

import {
  Box,
  Button,
  Flex,
  Input,
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
  SegmentedControl,
  SegmentedControlItem,
  Text,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import { ChevronDown, Search, ShieldCheck, X, Zap } from "lucide-react";
import { useState } from "react";

import { AiBotMark } from "@/components/ai-bot-mark";
import { useTranslations } from "@/i18n/translations";
import type { AiApprovalMode, AIModel, AISettings } from "@/lib/api";

/** Settings for the next FiestaBot turn, composed from the shared selection primitives. */
export function ComposerSettingsPill({
  approvalMode,
  onApprovalModeChange,
  approvalModeDisabled,
  autoNote,
  autoForThisChatOnly,
  providers,
  providerId,
  onProviderChange,
  models,
  model,
  onModelChange,
  modelsLoading = false,
  modelsError = false,
  onRetryModels,
}: {
  approvalMode: AiApprovalMode;
  onApprovalModeChange: (value: string) => void;
  approvalModeDisabled: boolean;
  autoNote: boolean;
  autoForThisChatOnly: boolean;
  providers: AISettings["providers"];
  providerId: string;
  onProviderChange: (id: string) => void;
  models: AIModel[];
  model: string;
  onModelChange: (id: string) => void;
  modelsLoading?: boolean;
  modelsError?: boolean;
  onRetryModels?: () => void;
}) {
  const t = useTranslations("aiChatPanel");
  const common = useTranslations("common");
  const combobox = useTranslations("modelCombobox");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [modelAtOpen, setModelAtOpen] = useState(model);
  const selected = models.find((item) => item.id === model);
  const modelName = selected?.name || model.split("/").at(-1) || t("defaultModel");
  const modeLabel = t(`approvalMode.${approvalMode}`);
  const provider = providers.find((item) => item.id === providerId);
  const tokens = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = models.filter((item) =>
    tokens.every((token) => `${item.name} ${item.id}`.toLocaleLowerCase().includes(token)),
  );
  // Keep the current model visible when reopening a large catalogue.
  const pinned = models.find((item) => item.id === modelAtOpen);
  const ordered = !tokens.length && pinned ? [pinned, ...matches.filter((item) => item.id !== pinned.id)] : matches;
  const visible = ordered.slice(0, 40);
  const customId = query.trim();
  const offerCustom = !!customId && !models.some((item) => item.id === customId);
  function choose(id: string) {
    onModelChange(id);
    setOpen(false);
  }
  return (
    <Popover
      modal
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        if (value) {
          setQuery("");
          setModelAtOpen(model);
        }
      }}
    >
      <PopoverTrigger
        className="inline-flex h-8 min-w-0 shrink items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-2.5 text-xs text-foreground transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t("composerSettings.triggerAriaLabel", { mode: modeLabel, model: modelName })}
        data-testid="ai-composer-settings"
      >
        {approvalMode === "ask" ? (
          <ShieldCheck className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : (
          <Zap className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
        )}
        <Text as="span" className="truncate" aria-hidden="true">
          {modeLabel} · {modelName}
        </Text>
        <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        sideOffset={10}
        collisionPadding={12}
        className="w-[360px] max-w-[calc(100vw-24px)] max-h-[min(680px,var(--available-height))] overflow-y-auto rounded-2xl p-0 shadow-xl"
        label={t("composerSettings.popoverLabel")}
        data-ai-composer-settings-popup=""
      >
        <Flex align="center" gap="3" className="border-b border-border/60 px-4 py-3.5">
          <AiBotMark className="size-8 rounded-lg" />
          <Box className="min-w-0 flex-1">
            <PopoverTitle className="text-sm font-semibold">{t("composerSettings.popoverLabel")}</PopoverTitle>
            <PopoverDescription className="mt-0.5 text-xs">{t("composerSettings.description")}</PopoverDescription>
          </Box>
          <PopoverClose
            aria-label={common("close")}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="size-4" aria-hidden="true" />
          </PopoverClose>
        </Flex>
        <Box className="space-y-3 border-b border-border/60 p-4">
          <Text size="xs" weight="medium" tone="muted">
            {t("approvalMode.label")}
          </Text>
          <ToggleCardGroup
            aria-label={t("approvalMode.label")}
            value={approvalMode}
            onValueChange={onApprovalModeChange}
            disabled={approvalModeDisabled}
            columns="1"
            size="sm"
            indicator="trailing"
            className="gap-2"
            data-testid="ai-approval-mode"
          >
            <ToggleCard
              value="ask"
              aria-label={t("approvalMode.ask")}
              aria-description={t("composerSettings.askDescription")}
              title={t("approvalMode.ask")}
              description={t("composerSettings.askDescription")}
              icon={<ShieldCheck />}
            />
            <ToggleCard
              value="auto"
              aria-label={t("approvalMode.auto")}
              aria-description={t("composerSettings.autoDescription")}
              title={t("approvalMode.auto")}
              description={t("composerSettings.autoDescription")}
              icon={<Zap />}
            />
          </ToggleCardGroup>
          <Text size="xs" tone="muted">
            {t("composerSettings.alwaysAsk")}
          </Text>
          {autoNote && (
            <Text size="xs" tone="muted" data-testid="ai-approval-mode-note">
              {t("approvalMode.autoNote")}
            </Text>
          )}
          {autoForThisChatOnly && (
            <Text size="xs" tone="muted" data-testid="ai-approval-mode-this-chat">
              {t("approvalMode.thisChat")}
            </Text>
          )}
        </Box>
        <Box className="space-y-3 p-4">
          <Flex align="center" justify="between" gap="2">
            <Text size="xs" weight="medium">
              {t("modelSelectAriaLabel")}
            </Text>
            {providers.length === 1 && (
              <Text size="xs" tone="muted" className="truncate">
                {provider?.name || provider?.id}
              </Text>
            )}
          </Flex>
          {providers.length > 1 && (
            <SegmentedControl
              aria-label={t("providerSelectAriaLabel")}
              value={providerId}
              onValueChange={(id) => {
                const nextProvider = providers.find((item) => item.id === id);
                setModelAtOpen(nextProvider?.default_model ?? nextProvider?.models[0] ?? "");
                setQuery("");
                onProviderChange(id);
              }}
              wrap
              size="sm"
              className="max-w-full"
            >
              {providers.map((item) => (
                <SegmentedControlItem
                  key={item.id}
                  value={item.id}
                  className="h-auto min-h-8 min-w-0 whitespace-normal break-words py-1.5 data-[checked]:text-foreground"
                >
                  {item.name || item.id}
                </SegmentedControlItem>
              ))}
            </SegmentedControl>
          )}
          <Box className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label={t("composerSettings.modelSearch")}
              placeholder={t("composerSettings.modelSearch")}
              className="h-10 pl-9 text-sm"
            />
          </Box>
          {modelsLoading && (
            <Text size="xs" tone="muted" role="status">
              {t("composerSettings.modelsLoading")}
            </Text>
          )}
          {modelsError && (
            <Box role="status" className="space-y-1">
              <Text size="xs" tone="muted">
                {t("composerSettings.modelsError")}
              </Text>
              <Button variant="ghost" size="sm" onClick={onRetryModels}>
                {t("composerSettings.retryModels")}
              </Button>
            </Box>
          )}
          {visible.length > 0 ? (
            <ToggleCardGroup
              key={`${providerId}:${query}`}
              aria-label={t("modelSelectAriaLabel")}
              value={model}
              onValueChange={onModelChange}
              columns="1"
              size="sm"
              indicator="trailing"
              // Base UI measures radio offsets relative to this scrolling group.
              className="relative max-h-56 gap-1 overflow-y-auto overscroll-contain p-0.5"
            >
              {visible.map((item) => (
                <ToggleCard
                  key={item.id}
                  value={item.id}
                  aria-label={item.name || item.id}
                  aria-description={item.id}
                  title={item.name || item.id}
                  description={item.name && item.name !== item.id ? item.id : undefined}
                  onClick={() => choose(item.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      choose(item.id);
                    }
                  }}
                  className="min-h-12 shrink-0 rounded-lg border-transparent break-words hover:bg-muted/60 data-[checked]:border-primary/30 [overflow-wrap:anywhere]"
                />
              ))}
            </ToggleCardGroup>
          ) : (
            !modelsLoading &&
            !modelsError && (
              <Text size="xs" tone="muted" role="status">
                {t(models.length ? "composerSettings.modelsNoMatches" : "composerSettings.modelsEmpty")}
              </Text>
            )
          )}
          {matches.length > visible.length && (
            <Text size="xs" tone="muted">
              {combobox("showingFirst", { shown: visible.length, total: matches.length })}
            </Text>
          )}
          {offerCustom && (
            <Button
              variant="outline"
              className="h-auto min-h-11 w-full flex-col items-start whitespace-normal break-all py-2 text-left"
              onClick={() => choose(customId)}
              aria-label={t("composerSettings.useCustomModel", { id: customId })}
            >
              <Text as="span">{t("composerSettings.useCustomModel", { id: customId })}</Text>
              <Text as="span" className="text-xs font-normal text-muted-foreground">
                {t("composerSettings.customModel")}
              </Text>
            </Button>
          )}
        </Box>
      </PopoverContent>
    </Popover>
  );
}
