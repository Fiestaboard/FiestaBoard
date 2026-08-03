"use client";

import {
  Badge,
  Box,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Skeleton,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Monitor, Smartphone, Zap } from "lucide-react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

const OUTPUT_OPTIONS = [
  {
    value: "ui" as const,
    icon: Monitor,
  },
  {
    value: "board" as const,
    icon: Zap,
  },
  {
    value: "both" as const,
    icon: Smartphone,
  },
];

export function OutputTargetSelector() {
  const t = useTranslations("outputTarget");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();

  const getOptionLabel = (value: string) => {
    const labels: Record<string, string> = {
      ui: t("uiOnly"),
      board: t("boardOnly"),
      both: t("uiAndBoard"),
    };
    return labels[value] || value;
  };
  const getOptionDescription = (value: string) => {
    const descriptions: Record<string, string> = {
      ui: t("uiOnlyDescription"),
      board: t("boardOnlyDescription"),
      both: t("uiAndBoardDescription"),
    };
    return descriptions[value] || value;
  };

  const { data: settings, isLoading } = useQuery({
    queryKey: ["output-settings"],
    queryFn: api.getOutputSettings,
  });

  const updateMutation = useMutation({
    mutationFn: (target: "ui" | "board" | "both") => api.updateOutputSettings(target),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["output-settings"] });
      queryClient.invalidateQueries({ queryKey: ["status"] });
      toast.success(t("toastUpdated"));
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="text-base sm:text-lg">{t("title")}</CardTitle>
          <CardDescription className="text-xs sm:text-sm">{t("description")}</CardDescription>
        </CardHeader>
        <CardContent className="px-4 sm:px-6">
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  const currentTarget = settings?.target || "ui";

  return (
    <Card>
      <CardHeader className="px-4 sm:px-6">
        <CardTitle className="text-base sm:text-lg">{t("title")}</CardTitle>
        <CardDescription className="text-xs sm:text-sm">{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 px-4 sm:px-6">
        {OUTPUT_OPTIONS.map((option) => {
          const Icon = option.icon;
          const isActive = currentTarget === option.value;
          const isEffective = settings?.effective_target === option.value;

          return (
            <button
              key={option.value}
              onClick={() => updateMutation.mutate(option.value)}
              disabled={updateMutation.isPending}
              aria-pressed={isActive}
              className={`w-full p-4 rounded-lg border-2 text-left transition-all active:scale-[0.98] min-h-[64px] ${
                isActive ? "border-brand bg-brand/5" : "border-muted hover:border-brand/50 active:bg-muted/50"
              }`}
            >
              <Flex align="start" gap="3">
                <Box
                  className={`p-2 rounded-md shrink-0 ${
                    isActive ? "bg-brand-emphasis text-brand-foreground" : "bg-muted"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                </Box>
                <Box className="flex-1 min-w-0">
                  <Flex align="center" gap="2" wrap>
                    <Text as="span" size="sm" weight="medium" className="sm:text-base">
                      {getOptionLabel(option.value)}
                    </Text>
                    {isActive && (
                      <Badge variant="default" className="text-[10px] sm:text-xs">
                        {tc("active")}
                      </Badge>
                    )}
                    {isEffective && !isActive && (
                      <Badge variant="secondary" className="text-[10px] sm:text-xs">
                        {tc("effective")}
                      </Badge>
                    )}
                  </Flex>
                  <Text size="xs" tone="muted" className="mt-1">
                    {getOptionDescription(option.value)}
                  </Text>
                </Box>
              </Flex>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}
