"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Skeleton, Stack } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

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

  useEffect(() => {
    const general = allSettings?.general;
    if (general) setInstanceName(general.instance_name ?? "");
  }, [allSettings?.general]);

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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Tag className="h-4 w-4" />
          {t("instanceNameTitle")}
        </CardTitle>
        <CardDescription>{t("instanceNameDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
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
      </CardContent>
    </Card>
  );
}
