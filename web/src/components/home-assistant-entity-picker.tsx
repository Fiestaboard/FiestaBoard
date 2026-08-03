"use client";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Button,
  Code,
  Flex,
  Input,
  ScrollArea,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { HomeAssistantEntity } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (variable: string) => void;
}

export function HomeAssistantEntityPicker({ open, onClose, onSelect }: Props) {
  const t = useTranslations("homeAssistantPicker");
  const tCommon = useTranslations("common");
  const [selectedEntity, setSelectedEntity] = useState<HomeAssistantEntity | null>(null);
  const [selectedAttribute, setSelectedAttribute] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");

  const { data: entitiesData, isLoading } = useQuery({
    queryKey: ["home-assistant-entities"],
    queryFn: () => api.getHomeAssistantEntities(),
    enabled: open,
  });

  const handleInsert = () => {
    if (selectedEntity && selectedAttribute) {
      const entityIdForTemplate = selectedEntity.entity_id.replace(/\./g, "_");
      const variable = `{{home_assistant.${entityIdForTemplate}.${selectedAttribute}}}`;
      onSelect(variable);
      handleClose();
    }
  };

  const handleClose = () => {
    onClose();
    setSelectedEntity(null);
    setSelectedAttribute("");
  };

  const availableAttributes = selectedEntity ? ["state", ...Object.keys(selectedEntity.attributes).sort()] : [];

  const filteredEntities =
    entitiesData?.entities.filter((entity) => {
      const query = searchQuery.toLowerCase();
      return (
        entity.entity_id.toLowerCase().includes(query) ||
        entity.friendly_name.toLowerCase().includes(query) ||
        entity.state.toLowerCase().includes(query)
      );
    }) || [];

  return (
    <AlertDialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) handleClose();
      }}
    >
      <AlertDialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <AlertDialogHeader>
          <AlertDialogTitle>{t("title")}</AlertDialogTitle>
          <AlertDialogDescription className="sr-only">{t("description")}</AlertDialogDescription>
        </AlertDialogHeader>

        {isLoading ? (
          <Flex align="center" justify="center" className="py-8">
            <Text tone="muted">{t("loadingEntities")}</Text>
          </Flex>
        ) : (
          <Flex direction="col" gap="3" className="flex-1 min-h-0">
            {!selectedEntity ? (
              <Flex direction="col" gap="2" className="flex-1 min-h-0">
                <Input
                  placeholder={t("searchPlaceholder")}
                  aria-label={t("searchAriaLabel")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  autoFocus
                  className="h-9"
                />
                <ScrollArea className="flex-1 min-h-[200px] border rounded-md">
                  <Box className="p-1">
                    {filteredEntities.length === 0 ? (
                      <Text tone="muted" className="text-center py-3">
                        {t("noEntities")}
                      </Text>
                    ) : (
                      filteredEntities.map((entity) => (
                        <button
                          key={entity.entity_id}
                          onClick={() => {
                            setSelectedEntity(entity);
                            setSelectedAttribute("");
                          }}
                          className="w-full text-left px-3 py-1.5 rounded hover:bg-muted transition-colors flex items-center gap-2"
                        >
                          <Text as="span" size="sm" className="font-mono flex-1">
                            {entity.entity_id}
                          </Text>
                          <Text as="span" size="xs" tone="muted" className="truncate max-w-[200px]">
                            {entity.friendly_name !== entity.entity_id ? entity.friendly_name : ""}
                          </Text>
                        </button>
                      ))
                    )}
                  </Box>
                </ScrollArea>
              </Flex>
            ) : (
              <>
                <Stack gap="1.5">
                  <Flex align="center" justify="between" gap="2" className="px-2 py-1.5 bg-muted rounded">
                    <Text as="span" size="sm" className="font-mono flex-1 truncate">
                      {selectedEntity.entity_id}
                    </Text>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setSelectedEntity(null);
                        setSelectedAttribute("");
                        setSearchQuery("");
                      }}
                      className="h-7 px-2 text-xs"
                    >
                      {t("change")}
                    </Button>
                  </Flex>
                </Stack>

                <Stack gap="1.5">
                  <Text size="xs" weight="medium" tone="muted" className="px-1">
                    {t("selectAttribute")}
                  </Text>
                  <ScrollArea className="h-[250px] border rounded-md">
                    <Box className="p-1">
                      {availableAttributes.map((attr) => {
                        const value = attr === "state" ? selectedEntity.state : selectedEntity.attributes[attr];
                        const displayValue =
                          typeof value === "object" ? JSON.stringify(value).slice(0, 50) : String(value).slice(0, 50);

                        return (
                          <button
                            key={attr}
                            onClick={() => setSelectedAttribute(attr)}
                            className={cn(
                              "w-full text-left px-2 py-1 rounded hover:bg-muted transition-colors",
                              selectedAttribute === attr && "bg-primary/10 border border-primary",
                            )}
                          >
                            <Flex align="center" justify="between" gap="2">
                              <Text as="span" size="xs" weight="medium" className="font-mono">
                                {attr}
                              </Text>
                              {displayValue && (
                                <Text as="span" size="xs" tone="muted" className="truncate max-w-[150px]">
                                  {displayValue}
                                </Text>
                              )}
                            </Flex>
                          </button>
                        );
                      })}
                    </Box>
                  </ScrollArea>
                </Stack>
              </>
            )}

            {selectedEntity && selectedAttribute && (
              <Stack gap="1" className="px-2 py-1.5 bg-muted rounded">
                <Code className="text-xs font-mono block">
                  {`{{home_assistant.${selectedEntity.entity_id.replace(/\./g, "_")}.${selectedAttribute}}}`}
                </Code>
                <Text size="xs" tone="muted">
                  {t("valueLabel")}:{" "}
                  {selectedAttribute === "state"
                    ? selectedEntity.state
                    : String(selectedEntity.attributes[selectedAttribute] || "N/A")}
                </Text>
              </Stack>
            )}
          </Flex>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <Button onClick={handleInsert} disabled={!selectedEntity || !selectedAttribute || isLoading} size="sm">
            {t("insert")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
