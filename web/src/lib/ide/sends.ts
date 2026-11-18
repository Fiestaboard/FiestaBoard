import type { SentLogItem } from "@fiestaboard/ui";

import type { PageSendEntry } from "@/lib/api/page-history";

export interface SendLogModel {
  /** Outcomes the kit's SentLog draws: shown, held, paused (newest first). */
  items: (SentLogItem & { boardName: string | null; count: number })[];
  /** Outcomes SentLog has no state for (failed, silenced): shown as ProblemItems. */
  notShown: (PageSendEntry & { id: string })[];
}

const LOGGED = { sent: "shown", held: "held", paused: "paused" } as const;

/**
 * H9b send history mapped onto C44 SentLog. SentLog draws shown/held/paused;
 * a failed write and a Show now refused by Silence have no SentLog state
 * (FiestaUI gap, DD-W), so they surface as warnings beside the log instead of
 * being mislabelled "Paused".
 */
export function sendLogModel(sends: readonly PageSendEntry[], formatTime: (iso: string) => string): SendLogModel {
  const items: SendLogModel["items"] = [];
  const notShown: SendLogModel["notShown"] = [];
  sends.forEach((send, index) => {
    const id = `${send.at}-${send.outcome}-${send.board_id ?? "none"}-${index}`;
    if (send.outcome === "failed" || send.outcome === "silenced") {
      notShown.push({ ...send, id });
      return;
    }
    items.push({
      id,
      at: formatTime(send.last_at ?? send.at),
      dateTime: send.last_at ?? send.at,
      outcome: LOGGED[send.outcome],
      boardName: send.board_name ?? null,
      count: send.count ?? 1,
    });
  });
  return { items, notShown };
}
