/**
 * When to offer "install this app" (07 note `58:34443`): after value, never on
 * load. The offer comes after the 3rd send or the first saved page, shows
 * once, and "Not now" snoozes it for 30 days. "Don't show again" (the Safari
 * sheet) and a finished install end it for good.
 *
 * State lives in localStorage under one versioned key. It holds counts and
 * timestamps only, never board or account data.
 */

export type InstallSuccess = "send" | "save";

export const SENDS_BEFORE_OFFER = 3;
export const SNOOZE_MS = 30 * 24 * 60 * 60 * 1000;
export const INSTALL_TRIGGER_KEY = "fiestaboard.install-offer.v1";

export interface InstallTriggerState {
  sends: number;
  saves: number;
  /** When the offer was last shown or snoozed (ms). Null: never. */
  snoozedAt: number | null;
  /** Never offer again. */
  never: boolean;
}

const EMPTY: InstallTriggerState = { sends: 0, saves: 0, snoozedAt: null, never: false };

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function storage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readInstallTrigger(store: StorageLike | null = storage()): InstallTriggerState {
  try {
    const raw = store?.getItem(INSTALL_TRIGGER_KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<InstallTriggerState>;
    return {
      sends: Number.isFinite(parsed.sends) ? Number(parsed.sends) : 0,
      saves: Number.isFinite(parsed.saves) ? Number(parsed.saves) : 0,
      snoozedAt: Number.isFinite(parsed.snoozedAt) ? Number(parsed.snoozedAt) : null,
      never: parsed.never === true,
    };
  } catch {
    return { ...EMPTY };
  }
}

function write(state: InstallTriggerState, store: StorageLike | null): void {
  try {
    store?.setItem(INSTALL_TRIGGER_KEY, JSON.stringify(state));
  } catch {
    // Private mode or a full quota: the offer just may come back sooner.
  }
}

/** True when the counts say "this person gets value here" and nothing holds the offer back. */
export function isOfferDue(state: InstallTriggerState, now: number): boolean {
  if (state.never) return false;
  if (state.snoozedAt !== null && now - state.snoozedAt < SNOOZE_MS) return false;
  return state.sends >= SENDS_BEFORE_OFFER || state.saves >= 1;
}

/**
 * Count one success. Returns true when the offer is due now; the caller then
 * shows it and calls {@link markOffered}.
 */
export function recordInstallSuccess(
  kind: InstallSuccess,
  now: number = Date.now(),
  store: StorageLike | null = storage(),
): boolean {
  const state = readInstallTrigger(store);
  const next = kind === "send" ? { ...state, sends: state.sends + 1 } : { ...state, saves: state.saves + 1 };
  write(next, store);
  return isOfferDue(next, now);
}

/**
 * The offer was shown, or "Not now" was pressed: hold it for 30 days. Counts
 * restart, so the next offer also follows fresh value.
 */
export function markOffered(now: number = Date.now(), store: StorageLike | null = storage()): void {
  const state = readInstallTrigger(store);
  write({ ...state, sends: 0, saves: 0, snoozedAt: now }, store);
}

/** "Don't show again", or the app was installed. */
export function markNeverOffer(store: StorageLike | null = storage()): void {
  write({ ...readInstallTrigger(store), never: true }, store);
}
