"use client";

import { Input, Label, PageSection, Skeleton, Stack } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function InstanceNameCard() {
  const t = useTranslations("profile");
  const queryClient = useQueryClient();

  const [instanceName, setInstanceName] = useState("");

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  // Mirror the server value into the input during render rather than from an
  // effect, so the field is populated in the first commit instead of the
  // second (react-hooks/set-state-in-effect, issue #1568).
  const general = allSettings?.general;
  if (useDepsChanged([general]) && general) {
    setInstanceName(general.instance_name ?? "");
  }

  const updateGeneralMutation = useMutation({
    mutationFn: api.updateGeneralConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const handleBlur = useCallback(() => {
    const current = allSettings?.general?.instance_name ?? "";
    if (instanceName !== current) {
      updateGeneralMutation.mutate({ instance_name: instanceName });
    }
  }, [instanceName, allSettings?.general?.instance_name, updateGeneralMutation]);

  return (
    <PageSection icon={<Tag />} title={t("instanceNameTitle")} description={t("instanceNameDescription")}>
      {isLoading ? (
        <Skeleton className="h-10 w-full max-w-sm" />
      ) : (
        <Stack gap="2" className="max-w-sm">
          <Label htmlFor="instance-name">{t("instanceNameTitle")}</Label>
          <Input
            id="instance-name"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            onBlur={handleBlur}
            placeholder={t("instanceNamePlaceholder")}
            maxLength={50}
          />
        </Stack>
      )}
    </PageSection>
  );
}
