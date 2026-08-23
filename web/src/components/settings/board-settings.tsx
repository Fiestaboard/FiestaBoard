"use client";

import {
  Badge,
  Box,
  Button,
  Flex,
  Grid,
  PageSection,
  Skeleton,
  Stack,
  Text,
  TextLink,
  TooltipProvider,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { SecretInput } from "@fiestaboard/ui/components/forms/secret-input";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Key, KeyRound, Loader2, Monitor, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import type { BoardConfig, DiscoveredBoard } from "@/lib/api";
import { api } from "@/lib/api";

type LocalKeyMode = "api_key" | "enablement_token";

export function BoardSettings() {
  const t = useTranslations("boardSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<Partial<BoardConfig>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [isEnabling, setIsEnabling] = useState(false);
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [discoveredBoards, setDiscoveredBoards] = useState<DiscoveredBoard[]>([]);

  // Fetch current config
  const { data: configData, isLoading } = useQuery({
    queryKey: ["board-config"],
    queryFn: api.getBoardConfig,
  });

  // Initialize form. Done during render rather than in an effect so the saved
  // connection details are in the first commit, and so the auto-save effect
  // below never observes an intermediate empty formData
  // (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([configData]) && configData?.config) {
    setFormData(configData.config);
    setHasChanges(false);
  }

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: Partial<BoardConfig>) => api.updateBoardConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-config"] });
      queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.invalidateQueries({ queryKey: ["status"] });
      toast.success(t("toastSaved"));
      setHasChanges(false);
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Handle field change
  const handleChange = (key: keyof BoardConfig, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  // Handle save
  const handleSave = () => {
    updateMutation.mutate(formData);
  };

  // Handle enablement token exchange
  const handleEnableLocalApi = async () => {
    if (!formData.host || !enablementToken) {
      toast.error(t("boardHostAndTokenRequired"));
      return;
    }

    setIsEnabling(true);
    try {
      const result = await api.enableLocalApi({
        host: formData.host,
        enablement_token: enablementToken,
      });

      if (result.success && result.api_key) {
        // Update the form with the retrieved API key
        handleChange("local_api_key", result.api_key);
        setEnablementToken("");
        setLocalKeyMode("api_key");
        toast.success(t("toastLocalApiEnabled"));
      } else {
        toast.error(result.message || t("toastFailedToEnable"));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toastFailedToEnable"));
    } finally {
      setIsEnabling(false);
    }
  };

  // Handle scanning for boards on the network
  const handleScanForBoards = async () => {
    setScanStatus("scanning");
    setDiscoveredBoards([]);
    try {
      const result = await api.scanForBoards();
      setDiscoveredBoards(result.boards);
      setScanStatus("done");
      if (result.boards.length >= 1) {
        toast.info(t("toastFoundBoards", { count: result.boards.length }));
      } else {
        toast.info(t("toastNoBoardsFound"));
      }
    } catch {
      setScanStatus("error");
      toast.error(t("toastScanFailed"));
    }
  };

  // Auto-save when form data changes (debounced)
  useEffect(() => {
    // Skip if no changes or if a mutation is already in progress
    if (!hasChanges || updateMutation.isPending) {
      return;
    }

    // Debounce auto-save by 1 second
    const timeoutId = setTimeout(() => {
      handleSave();
    }, 1000);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData, hasChanges]);

  const apiMode = formData.api_mode ?? "local";
  const hasLocalKey = formData.local_api_key === "***" || (formData.local_api_key && formData.local_api_key.length > 0);
  const hasCloudKey = formData.cloud_key === "***" || (formData.cloud_key && formData.cloud_key.length > 0);
  const hasHost = formData.host && formData.host.length > 0;

  const isConfigValid = (apiMode === "local" && hasLocalKey && hasHost) || (apiMode === "cloud" && hasCloudKey);

  if (isLoading) {
    return (
      <PageSection>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mt-2 h-4 w-64" />
        <Skeleton className="mt-4 h-40 w-full" />
      </PageSection>
    );
  }

  return (
    <PageSection
      icon={
        <Box className="p-2 rounded-md bg-primary/10">
          <Monitor className="h-5 w-5 text-primary" />
        </Box>
      }
      title={
        <>
          {t("connection")}
          {isConfigValid ? (
            <Badge variant="default" className="text-xs bg-board-green">
              <Check className="h-3 w-3 mr-1" />
              {t("configured")}
            </Badge>
          ) : (
            <Badge variant="destructive" className="text-xs">
              <AlertCircle className="h-3 w-3 mr-1" />
              {t("incomplete")}
            </Badge>
          )}
        </>
      }
      description={t("configureDescription")}
      contentClassName="space-y-4"
    >
      <TooltipProvider>
        {/* API Mode */}
        <Stack gap="1.5">
          <label className="text-xs font-medium">{t("connectionMode")}</label>
          <Grid cols="2" gap="2">
            <button
              onClick={() => handleChange("api_mode", "local")}
              className={`p-3 rounded-md border text-left transition-colors ${
                apiMode === "local" ? "border-primary bg-primary/10" : "border-muted hover:border-primary/50"
              }`}
            >
              <Text weight="medium">{t("localApi")}</Text>
              <Text size="xs" tone="muted">
                {t("localApiDescription")}
              </Text>
            </button>
            <button
              onClick={() => handleChange("api_mode", "cloud")}
              className={`p-3 rounded-md border text-left transition-colors ${
                apiMode === "cloud" ? "border-primary bg-primary/10" : "border-muted hover:border-primary/50"
              }`}
            >
              <Text weight="medium">{t("cloudApi")}</Text>
              <Text size="xs" tone="muted">
                {t("cloudApiDescription")}
              </Text>
            </button>
          </Grid>
        </Stack>

        {/* Local API Fields */}
        {apiMode === "local" && (
          <>
            {/* Board Host - always needed for local */}
            <Stack gap="1.5">
              <label className="text-xs font-medium">
                {t("boardHost")}{" "}
                <Text as="span" size="xs" tone="destructive">
                  *
                </Text>
              </label>
              <Flex gap="2">
                <input
                  type="text"
                  value={formData.host ?? ""}
                  onChange={(e) => handleChange("host", e.target.value)}
                  placeholder="192.168.1.100"
                  className="flex-1 h-9 px-3 text-sm rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleScanForBoards}
                  disabled={scanStatus === "scanning"}
                  className="h-9 w-9 p-0"
                  title={t("scanTooltip")}
                  aria-label={t("scanTooltip")}
                >
                  {scanStatus === "scanning" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Search className="h-3.5 w-3.5" />
                  )}
                </Button>
              </Flex>
              <Text size="xs" tone="muted">
                {t("boardHostHint")}
              </Text>
            </Stack>

            {/* Scan results */}
            {scanStatus === "done" && discoveredBoards.length >= 1 && (
              <Stack gap="1.5">
                <label className="text-xs font-medium">{t("foundBoards", { count: discoveredBoards.length })}</label>
                <Stack gap="1">
                  {discoveredBoards.map((board) => (
                    <button
                      key={board.ip}
                      type="button"
                      onClick={() => {
                        handleChange("host", board.ip);
                      }}
                      className={`w-full flex items-center justify-between p-2 rounded-md border text-xs transition-colors text-left ${
                        formData.host === board.ip
                          ? "border-primary bg-primary/10"
                          : "border-muted hover:border-primary/50"
                      }`}
                    >
                      <Text as="span" size="xs" className="font-mono">
                        {board.ip}
                      </Text>
                      {board.hostname && (
                        <Text as="span" size="xs" tone="muted">
                          {board.hostname}
                        </Text>
                      )}
                    </button>
                  ))}
                </Stack>
              </Stack>
            )}

            {/* Local Key Mode Toggle */}
            <Stack gap="1.5">
              <label className="text-xs font-medium">{t("authMethod")}</label>
              <Grid cols="2" gap="2">
                <button
                  type="button"
                  onClick={() => setLocalKeyMode("api_key")}
                  className={`flex items-center justify-center gap-1.5 p-2 rounded-md border text-xs transition-colors ${
                    localKeyMode === "api_key"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-muted hover:border-primary/50 text-muted-foreground"
                  }`}
                >
                  <Key className="h-3.5 w-3.5" />
                  <Text as="span" size="xs">
                    {t("apiKey")}
                  </Text>
                </button>
                <button
                  type="button"
                  onClick={() => setLocalKeyMode("enablement_token")}
                  className={`flex items-center justify-center gap-1.5 p-2 rounded-md border text-xs transition-colors ${
                    localKeyMode === "enablement_token"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-muted hover:border-primary/50 text-muted-foreground"
                  }`}
                >
                  <KeyRound className="h-3.5 w-3.5" />
                  <Text as="span" size="xs">
                    {t("enablementToken")}
                  </Text>
                </button>
              </Grid>
            </Stack>

            {localKeyMode === "api_key" ? (
              <Stack gap="1.5">
                <label className="text-xs font-medium" htmlFor="board-local-api-key">
                  {t("localApiKey")}{" "}
                  <Text as="span" size="xs" tone="destructive">
                    *
                  </Text>
                </label>
                <SecretInput
                  id="board-local-api-key"
                  value={formData.local_api_key === "***" ? "" : (formData.local_api_key ?? "")}
                  onChange={(e) => handleChange("local_api_key", e.target.value)}
                  placeholder={hasLocalKey ? t("localApiKeySetPlaceholder") : t("localApiKeyPlaceholder")}
                  revealDisabled={formData.local_api_key === "***"}
                  // The old Tooltip explaining why a server-stored value cannot be
                  // revealed has nowhere to attach now that the toggle is internal,
                  // so that copy becomes the disabled toggle's accessible name.
                  showLabel={formData.local_api_key === "***" ? t("cannotReveal") : t("showApiKey")}
                  hideLabel={t("hideApiKey")}
                />
                <Text size="xs" tone="muted">
                  {t.rich("localApiSetupGuideHint", {
                    link: (chunks) => (
                      <TextLink
                        href="https://fiestaboard.app/docs/setup/api-keys"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {chunks}
                      </TextLink>
                    ),
                  })}
                </Text>
              </Stack>
            ) : (
              <Stack gap="2">
                <Stack gap="1.5">
                  <label className="text-xs font-medium" htmlFor="board-enablement-token">
                    {t("enablementToken")}
                  </label>
                  <SecretInput
                    id="board-enablement-token"
                    value={enablementToken}
                    onChange={(e) => setEnablementToken(e.target.value)}
                    placeholder={t("enablementTokenPlaceholder")}
                    showLabel={t("showToken")}
                    hideLabel={t("hideToken")}
                  />
                  <Text size="xs" tone="muted">
                    {t.rich("enablementTokenHint", {
                      link: (chunks) => (
                        <TextLink
                          href="https://www.vestaboard.com/local-api"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          {chunks}
                        </TextLink>
                      ),
                    })}
                  </Text>
                </Stack>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleEnableLocalApi}
                  disabled={!formData.host || !enablementToken || isEnabling}
                  className="w-full"
                >
                  {isEnabling ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      {t("enabling")}
                    </>
                  ) : (
                    t("getApiKey")
                  )}
                </Button>
              </Stack>
            )}
          </>
        )}

        {/* Cloud API Fields */}
        {apiMode === "cloud" && (
          <Stack gap="1.5">
            <label className="text-xs font-medium" htmlFor="board-cloud-key">
              {t("readWriteApiKey")}{" "}
              <Text as="span" size="xs" tone="destructive">
                *
              </Text>
            </label>
            <SecretInput
              id="board-cloud-key"
              value={formData.cloud_key === "***" ? "" : (formData.cloud_key ?? "")}
              onChange={(e) => handleChange("cloud_key", e.target.value)}
              placeholder={hasCloudKey ? t("cloudKeySetPlaceholder") : t("cloudKeyPlaceholder")}
              revealDisabled={formData.cloud_key === "***"}
              showLabel={formData.cloud_key === "***" ? t("cannotReveal") : t("showCloudKey")}
              hideLabel={t("hideCloudKey")}
            />
            <Text size="xs" tone="muted">
              {t("cloudKeyHint")}
            </Text>
          </Stack>
        )}

        {/* Validation message */}
        {!isConfigValid && (
          <Flex align="center" gap="2" className="p-2 rounded-md bg-destructive/10 text-foreground text-xs">
            <AlertCircle className="h-4 w-4" />
            <Text as="span" size="xs">
              {apiMode === "local" ? t("localApiRequired") : t("cloudApiRequired")}
            </Text>
          </Flex>
        )}

        {/* Auto-save indicator */}
        {updateMutation.isPending && (
          <Flex align="center" justify="center" gap="2" className="pt-2 text-xs text-muted-foreground">
            <Spinner size="sm" className="size-3 text-primary" label={null} />
            <Text as="span" size="xs" tone="muted">
              {tCommon("saving")}
            </Text>
          </Flex>
        )}
      </TooltipProvider>
    </PageSection>
  );
}

// Backward compatibility alias
export const FiestaboardSettings = BoardSettings;
