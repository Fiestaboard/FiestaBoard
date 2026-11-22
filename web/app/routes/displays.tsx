import { Button, Dialog, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Monitor, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { Outlet } from "react-router";

import { AddDisplayContext } from "@/components/displays/add-display-context";
import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { boardGeometry, boardMeta } from "@/components/home/home-board";
import { SectionShell } from "@/components/section-shell";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { AVAILABLE_OUTPUTS_QUERY_KEY, useOutputs } from "@/components/settings/output-boards";
import type { WizardOutputChoice } from "@/components/wizard/step-output-plugin";
import { useParams, useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * The Displays section (plan D21): its card and header stay mounted while the
 * list (/displays, Displays and Marketplace tabs) and one display's page
 * (/displays/:boardId) swap beneath them. "Add a display" belongs to the
 * list, so it lives on the header here and tucks away while a display is open.
 */
export function DisplaysSection({ children }: { children: React.ReactNode }) {
  const t = useTranslations("displays");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { boardId } = useParams<{ boardId?: string }>();
  const displays = useDisplayBoards();
  const { data: outputs } = useOutputs();
  // true: the add flow from its first step; an output: from that output's setup.
  const [adding, setAdding] = useState<boolean | WizardOutputChoice>(false);
  const openAdd = useCallback((output?: WizardOutputChoice) => setAdding(output ?? true), []);

  // A Marketplace card's link (`/displays?add=<output id>`) opens the flow at
  // that output; closing the dialog drops the parameter and keeps the rest
  // (the tab). Only the list takes it: a display's page has no add flow.
  const addParam = boardId ? null : searchParams.get("add");
  const available = useQuery({
    queryKey: AVAILABLE_OUTPUTS_QUERY_KEY,
    queryFn: () => api.listAvailableOutputs(),
    staleTime: 60_000,
    enabled: !!addParam,
  });
  const linked = addParam ? available.data?.find((o) => o.id === addParam) : undefined;
  const open: false | true | WizardOutputChoice =
    adding !== false ? adding : linked ? { id: linked.id, name: linked.name } : false;
  const close = () => {
    setAdding(false);
    if (addParam) {
      const rest = new URLSearchParams(searchParams.toString());
      rest.delete("add");
      const query = rest.toString();
      router.replace(query ? `/displays?${query}` : "/displays", { scroll: false });
    }
  };

  const board = boardId ? displays.boards.find((b) => b.id === boardId) : undefined;
  const outputId = board?.output ?? "vestaboard";
  const outputName = outputs?.find((o) => o.id === outputId)?.name ?? outputId;
  const name = board ? board.name || t("unnamed") : undefined;
  // 07d `320:18175`: the mono meta line, "FLAGSHIP 22 × 6 · LOCAL API ·
  // FIESTAPI.LOCAL": the size, how the hub reaches it, and its address
  // (BB-FH-5). The connection is the Vestaboard API mode, else the output.
  const tMode = useTranslations("outputSettings.vestaboard.fields.api_mode.cards");
  const config = (board?.output_config ?? {}) as { api_mode?: string; host?: string };
  const connection =
    outputId === "vestaboard"
      ? config.api_mode === "cloud"
        ? tMode("cloud.title")
        : config.api_mode === "local" || config.host
          ? tMode("local.title")
          : null
      : outputName !== name
        ? outputName
        : null;
  const meta = board
    ? [boardMeta(board, boardGeometry(board)), connection, config.host].filter(Boolean).join(" · ")
    : "";
  const detail = boardId
    ? {
        id: boardId,
        // A display the list no longer has is named as not found, never by
        // its raw id (BB-A-20).
        title: name ?? (displays.isLoading ? tCommon("loading") : t("notFoundTitle")),
        // A display named after its output ("Divoom Pixoo 64" on a Divoom
        // Pixoo 64) would read its name three times running; say the output
        // only when it adds something.
        description: meta ? (
          <Text as="span" size="xs" tone="muted" className="block font-mono uppercase tracking-wide">
            {meta}
          </Text>
        ) : undefined,
      }
    : null;

  return (
    <AddDisplayContext.Provider value={openAdd}>
      <SectionShell
        icon={Monitor}
        title={t("title")}
        description={t("description")}
        href="/displays"
        detail={detail}
        compactOnPhone
        action={
          <Button onClick={() => openAdd()} data-testid="add-display">
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t("addDisplay")}
          </Button>
        }
      >
        {children}
        <Dialog open={open !== false} onOpenChange={(isOpen) => !isOpen && close()}>
          {open !== false && (
            <AddDisplayDialog
              key={open === true ? "choose" : open.id}
              initialOutput={open === true ? undefined : open}
              onCancel={close}
              onCreated={(id) => {
                setAdding(false);
                router.push(`/displays/${encodeURIComponent(id)}`);
              }}
            />
          )}
        </Dialog>
      </SectionShell>
    </AddDisplayContext.Provider>
  );
}

export default function DisplaysLayout() {
  return (
    <DisplaysSection>
      <Outlet />
    </DisplaysSection>
  );
}
