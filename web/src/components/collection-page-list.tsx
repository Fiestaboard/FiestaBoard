import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Flex,
  Kbd,
  ListRow,
  ListRowGroup,
  SortableList,
  SortableListHandle,
  type SortableListLabels,
  SortableListMoveButtons,
  Text,
  useSortableItem,
} from "@fiestaboard/ui";
import { ArrowDown, ArrowUp, Ellipsis, Trash2, X } from "lucide-react";
import { useMemo } from "react";

import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { useTranslations } from "@/i18n/translations";
import type { CollectionSelectionMode, Page } from "@/lib/api";

type Translate = ReturnType<typeof useTranslations>;

export interface CollectionPageListProps {
  /** The Collection's members, in rotation order. */
  pageIds: string[];
  /** Every page, to name the members. A member that is gone is named by its id. */
  pages: Page[];
  /** Only time-based rotation has an order; random and variable lists have no handles. */
  mode: CollectionSelectionMode;
  /** Move the member at `from` to `to` (SortableList's controlled `onMove`). */
  onMove: (from: number, to: number) => void;
  onRemove: (index: number) => void;
}

interface Member {
  id: string;
  name: string;
  shape: string | null;
}

/** "Flagship", "Note", "Note Array 2×2", "Panel 12×29": the row's meta (07 `57:66920`). */
function shapeLabel(page: Page | undefined, t: Translate): string | null {
  switch (page?.device_type) {
    case "flagship":
      return t("pageShapeFlagship");
    case "note":
      return t("pageShapeNote");
    case "note_array":
      return t("pageShapeNoteArray", { wide: page.notes_wide ?? 1, tall: page.notes_tall ?? 1 });
    case "panel":
      return page.grid_rows && page.grid_cols
        ? t("pageShapePanel", { rows: page.grid_rows, cols: page.grid_cols })
        : t("pageShapePanelPlain");
    default:
      return null;
  }
}

/**
 * The pages in a Collection (WEB-06).
 *
 * Time-based rotation is a FiestaUI SortableList (08 P7 `61:53985`): drag
 * the grip, or focus a row and press Space, ↑ ↓, Space (Esc cancels). Move
 * up / Move down sit on the focused or lifted row from md up (07c
 * `312:74870`) and always in the row's ••• menu (07 `57:66920`). Random and
 * variable lists have no order, so they are one inset group with an × per
 * page and no handles (07c `312:76483`).
 */
export function CollectionPageList({ pageIds, pages, mode, onMove, onRemove }: CollectionPageListProps) {
  const t = useTranslations("collections");
  const coarse = useCoarsePointer();
  const size = coarse ? "touch" : "default";

  const members = useMemo<Member[]>(
    () =>
      pageIds.map((id) => {
        const page = pages.find((p) => p.id === id);
        return { id, name: page?.name || id, shape: shapeLabel(page, t) };
      }),
    [pageIds, pages, t],
  );

  const labels = useMemo<SortableListLabels>(
    () => ({
      lifted: (name, position, total) => t("sortLifted", { name, position, total }),
      moving: (name, position, total) => t("sortMoving", { name, position, total }),
      dropped: (name, position, total) => t("sortDropped", { name, position, total }),
      cancelled: (name, position, total) => t("sortCancelled", { name, position, total }),
      moved: (name, position, total) => t("sortMoved", { name, position, total }),
      instructions: t("sortInstructions"),
      moveUp: t("sortMoveUp"),
      moveDown: t("sortMoveDown"),
    }),
    [t],
  );

  if (mode !== "time") {
    return (
      <ListRowGroup variant="inset" size={size}>
        {members.map((member, index) => (
          <ListRow
            key={member.id}
            title={member.name}
            meta={member.shape}
            trailing={
              // TODO(#385): Button size="touch" for the 44px target once FiestaUI #385 is on alpha.
              <Button
                type="button"
                variant="ghost"
                size={coarse ? "icon-lg" : "icon-sm"}
                aria-label={t("removePage", { name: member.name })}
                onClick={() => onRemove(index)}
              >
                <X aria-hidden="true" />
              </Button>
            }
          />
        ))}
      </ListRowGroup>
    );
  }

  return (
    <Flex direction="col" gap="3">
      <SortableList
        items={members}
        getKey={(member) => member.id}
        getLabel={(member) => member.name}
        onMove={onMove}
        labels={labels}
        size={size}
        renderItem={(member, index) => (
          <SortableRow member={member} index={index} size={size} onRemove={onRemove} t={t} />
        )}
      />
      <Flex
        align="center"
        gap="2"
        wrap
        className="max-md:hidden text-xs text-muted-foreground"
        data-testid="collection-reorder-keys"
      >
        <Kbd keys={["space"]} />
        <Text as="span" size="xs" tone="muted">
          {t("reorderKeysLift")}
        </Text>
        <Kbd keys={["up", "down"]} />
        <Text as="span" size="xs" tone="muted">
          {t("reorderKeysMove")}
        </Text>
        <Kbd keys={["esc"]} />
        <Text as="span" size="xs" tone="muted">
          {t("reorderKeysCancel")}
        </Text>
      </Flex>
    </Flex>
  );
}

function SortableRow({
  member,
  index,
  size,
  onRemove,
  t,
}: {
  member: Member;
  index: number;
  size: "default" | "touch";
  onRemove: (index: number) => void;
  t: Translate;
}) {
  const item = useSortableItem();
  return (
    <ListRow
      variant="card"
      size={size}
      leading={
        <>
          <SortableListHandle />
          <Text as="span" size="sm" tone="muted" className="max-md:hidden w-4 text-center tabular-nums">
            {index + 1}
          </Text>
        </>
      }
      title={member.name}
      description={member.shape}
      trailing={
        <>
          <SortableListMoveButtons className="max-md:hidden" />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              {/* TODO(#385): Button size="touch" for the 44px target once FiestaUI #385 is on alpha. */}
              <Button
                type="button"
                variant="ghost"
                size={size === "touch" ? "icon-lg" : "icon-sm"}
                aria-label={t("pageActions", { name: member.name })}
              >
                <Ellipsis aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem disabled={!item.canMoveUp} onClick={item.moveUp}>
                <ArrowUp aria-hidden="true" />
                {t("sortMoveUp")}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!item.canMoveDown} onClick={item.moveDown}>
                <ArrowDown aria-hidden="true" />
                {t("sortMoveDown")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={() => onRemove(index)}>
                <Trash2 aria-hidden="true" />
                {t("removePage", { name: member.name })}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      }
    />
  );
}
