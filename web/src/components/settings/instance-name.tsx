"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag } from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
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
          <div className="space-y-2 max-w-sm">
            <Label htmlFor="instance-name">{t("instanceNameTitle")}</Label>
            <Input
              id="instance-name"
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              onBlur={handleBlur}
              placeholder={t("instanceNamePlaceholder")}
              maxLength={50}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
