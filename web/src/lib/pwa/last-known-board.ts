/**
 * The last frame each board was seen showing, kept in IndexedDB so the app
 * can still say "this is what was on the wall" when the hub can't be reached
 * or this device is offline (WEB-16; 07 `59:69165` "Last known").
 *
 * Privacy rules (2.8):
 * - Only what the board itself shows publicly is stored: the frame and the
 *   board's display settings. No tokens, cookies, page templates or account
 *   data.
 * - Each record names the account it was recorded for (`owner`). A record is
 *   only read back for that same owner, and the whole store is wiped on sign
 *   out, on the sign-in page, and as soon as a different account is seen.
 */

import { getBasePath } from "@/lib/base-path";

export const LAST_KNOWN_DB = "fiestaboard-offline";
const STORE = "last-known-boards";
const DB_VERSION = 2;
const META = "session";
interface Session {
  generation: number;
  owner: string | null;
  active: boolean;
}
const emptySession: Session = { generation: 0, owner: null, active: false };

/** The board's own display settings, enough to draw the frame as that device. */
export interface LastKnownBoardInfo {
  name?: string | null;
  device_type?: string | null;
  board_color?: string | null;
  notes_wide?: number | null;
  notes_tall?: number | null;
  grid_rows?: number | null;
  grid_cols?: number | null;
  code62_glyph?: string | null;
  led_layout?: unknown;
  device_model?: string | null;
  device_model_spec?: unknown;
}

export interface LastKnownBoard {
  boardId: string;
  /** Account username it was recorded for; null on an install with sign-in off. */
  owner: string | null;
  message: string;
  cells?: unknown;
  rows: number;
  cols: number;
  board: LastKnownBoardInfo | null;
  /** When the hub last reported this frame (ms since epoch). */
  savedAt: number;
}

const revokedScopes = new Map<string, string>();
function revocationKey() {
  return `fiestaboard-offline-revoked:${getBasePath()}`;
}
function revocation(): string | null {
  try {
    return localStorage.getItem(revocationKey());
  } catch {
    return revokedScopes.get(getBasePath()) ?? null;
  }
}
function revoke() {
  const marker = `${Date.now()}:${Math.random()}`;
  revokedScopes.set(getBasePath(), marker);
  try {
    localStorage.setItem(revocationKey(), marker);
  } catch {
    /* IndexedDB still enforces the generation. */
  }
}
function permit(marker: string | null): boolean {
  if (revocation() !== marker) return false;
  revokedScopes.delete(getBasePath());
  try {
    localStorage.removeItem(revocationKey());
  } catch {
    /* storage disabled */
  }
  return true;
}

function idb(): IDBFactory | null {
  try {
    return typeof indexedDB === "undefined" ? null : indexedDB;
  } catch {
    return null;
  }
}

function open(): Promise<IDBDatabase | null> {
  const factory = idb();
  if (!factory) return Promise.resolve(null);
  return new Promise((resolve) => {
    let request: IDBOpenDBRequest;
    try {
      request = factory.open(`${LAST_KNOWN_DB}${getBasePath()}`, DB_VERSION);
    } catch {
      resolve(null);
      return;
    }
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "boardId" });
      if (!db.objectStoreNames.contains(META)) {
        db.createObjectStore(META);
        // Legacy records had no durable account isolation. Fail closed on migration.
        request.transaction!.objectStore(STORE).clear();
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
}

function done(tx: IDBTransaction): Promise<boolean> {
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => resolve(false);
    tx.onabort = () => resolve(false);
  });
}

/** Run session checks and frame changes in one transaction, shared by every tab. */
async function sessionTransaction<T>(operation: (session: Session, tx: IDBTransaction) => T, fallback: T): Promise<T> {
  const db = await open();
  if (!db) return fallback;
  try {
    const tx = db.transaction([STORE, META], "readwrite");
    const completion = done(tx);
    let result = fallback;
    const request = tx.objectStore(META).get("current");
    request.onsuccess = () => {
      result = operation(request.result ?? { ...emptySession }, tx);
    };
    return (await completion) ? result : fallback;
  } catch {
    return fallback;
  } finally {
    db.close();
  }
}

export async function readBoardSessionGeneration(): Promise<number> {
  return sessionTransaction((session) => session.generation, -1);
}

/** A verified auth response can establish an owner only in the generation it started in. */
export async function establishBoardOwner(
  owner: string | null,
  generation: number,
  cached = false,
): Promise<number | null> {
  const marker = revocation();
  if (cached && marker) return null;
  const result = await sessionTransaction<number | null>((session, tx) => {
    if (session.generation !== generation || (cached && (!session.active || session.owner !== owner))) return null;
    if (session.active && (marker || session.owner !== owner)) {
      tx.objectStore(STORE).clear();
      session.generation++;
    }
    session.owner = owner;
    session.active = true;
    tx.objectStore(META).put(session, "current");
    return session.generation;
  }, null);
  return result !== null && permit(marker) ? result : null;
}

/** Store a frame only if its recorder still owns the active session. */
export async function saveLastKnownBoard(record: LastKnownBoard, generation: number): Promise<boolean> {
  if (revocation()) return false;
  return sessionTransaction((session, tx) => {
    if (revocation() || generation !== session.generation || !session.active || session.owner !== record.owner)
      return false;
    tx.objectStore(STORE).put(record);
    return true;
  }, false);
}

async function readAll(): Promise<LastKnownBoard[]> {
  const db = await open();
  if (!db) return [];
  try {
    const tx = db.transaction(STORE, "readonly");
    const request = tx.objectStore(STORE).getAll();
    return await new Promise((resolve) => {
      request.onsuccess = () => resolve((request.result as LastKnownBoard[]) ?? []);
      request.onerror = () => resolve([]);
    });
  } catch {
    return [];
  } finally {
    db.close();
  }
}

/**
 * The newest frame recorded for `owner`, or for any owner when `owner` is
 * `undefined` (offline, where the account can't be checked: the store only
 * ever holds the last signed-in account's records, see the rules above).
 */
export async function readLastKnownBoard(owner?: string | null): Promise<LastKnownBoard | null> {
  if (revocation()) return null;
  const records = (await readAll()).filter((r) => owner === undefined || r.owner === owner);
  if (revocation() || records.length === 0) return null;
  return records.reduce((newest, r) => (r.savedAt > newest.savedAt ? r : newest));
}

/** The owner the stored records belong to, or undefined when the store is empty. */
export async function lastKnownOwner(): Promise<string | null | undefined> {
  if (revocation()) return undefined;
  const [first] = await readAll();
  return revocation() || first === undefined ? undefined : first.owner;
}

/** Wipe every stored frame. Never throws. */
export async function clearLastKnownBoards(): Promise<boolean> {
  // Synchronous and durable even if navigation interrupts a blocked IndexedDB clear.
  revoke();
  return sessionTransaction((session, tx) => {
    tx.objectStore(STORE).clear();
    tx.objectStore(META).put({ generation: session.generation + 1, owner: null, active: false }, "current");
    return true;
  }, false);
}
