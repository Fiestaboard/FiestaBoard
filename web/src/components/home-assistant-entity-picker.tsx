"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";
import { api, HomeAssistantEntity } from "@/lib/api";

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
      const entityIdForTemplate = selectedEntity.entity_id.replace(/\./g, '_');
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
  
  const availableAttributes = selectedEntity
    ? ["state", ...Object.keys(selectedEntity.attributes).sort()]
    : [];
  
  const filteredEntities = entitiesData?.entities.filter((entity) => {
    const query = searchQuery.toLowerCase();
    return (
      entity.entity_id.toLowerCase().includes(query) ||
      entity.friendly_name.toLowerCase().includes(query) ||
      entity.state.toLowerCase().includes(query)
    );
  }) || [];
  
  return (
    <AlertDialog open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
      <AlertDialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <AlertDialogHeader>
          <AlertDialogTitle>{t("title")}</AlertDialogTitle>
          <AlertDialogDescription className="sr-only">
            {t("description")}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="text-sm text-muted-foreground">{t("loadingEntities")}</div>
          </div>
        ) : (
          <div className="space-y-3 flex-1 overflow-y-auto">
            {!selectedEntity ? (
              <div className="space-y-2">
                <Input
                  placeholder={t("searchPlaceholder")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  autoFocus
                  className="h-9"
                />
                <ScrollArea className="h-[400px] border rounded-md">
                  <div className="p-1">
                    {filteredEntities.length === 0 ? (
                      <div className="text-sm text-muted-foreground text-center py-3">
                        {t("noEntities")}
                      </div>
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
                          <span className="font-mono text-sm flex-1">{entity.entity_id}</span>
                          <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                            {entity.friendly_name !== entity.entity_id ? entity.friendly_name : ""}
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </div>
            ) : (
              <>
                <div className="space-y-1.5">
                  <div className="px-2 py-1.5 bg-muted rounded flex items-center justify-between gap-2">
                    <span className="font-mono text-sm flex-1 truncate">{selectedEntity.entity_id}</span>
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
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground px-1">{t("selectAttribute")}</label>
                  <ScrollArea className="h-[250px] border rounded-md">
                    <div className="p-1">
                      {availableAttributes.map((attr) => {
                        const value = attr === "state" 
                          ? selectedEntity.state 
                          : selectedEntity.attributes[attr];
                        const displayValue = typeof value === "object" 
                          ? JSON.stringify(value).slice(0, 50) 
                          : String(value).slice(0, 50);
                        
                        return (
                          <button
                            key={attr}
                            onClick={() => setSelectedAttribute(attr)}
                            className={cn(
                              "w-full text-left px-2 py-1 rounded hover:bg-muted transition-colors",
                              selectedAttribute === attr && "bg-primary/10 border border-primary"
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-mono text-xs font-medium">{attr}</span>
                              {displayValue && (
                                <span className="text-xs text-muted-foreground truncate max-w-[150px]">
                                  {displayValue}
                                </span>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </ScrollArea>
                </div>
              </>
            )}
            
            {selectedEntity && selectedAttribute && (
              <div className="px-2 py-1.5 bg-muted rounded space-y-1">
                <code className="text-xs font-mono block">
                  {`{{home_assistant.${selectedEntity.entity_id.replace(/\./g, '_')}.${selectedAttribute}}}`}
                </code>
                <div className="text-xs text-muted-foreground">
                  {t("valueLabel")}: {
                    selectedAttribute === "state"
                      ? selectedEntity.state
                      : String(selectedEntity.attributes[selectedAttribute] || "N/A")
                  }
                </div>
              </div>
            )}
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <Button
            onClick={handleInsert}
            disabled={!selectedEntity || !selectedAttribute || isLoading}
            size="sm"
          >
            {t("insert")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

