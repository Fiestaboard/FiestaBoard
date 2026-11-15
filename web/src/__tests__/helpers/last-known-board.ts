import {
  establishBoardOwner,
  type LastKnownBoard,
  readBoardSessionGeneration,
  saveLastKnownBoard,
} from "@/lib/pwa/last-known-board";

/** Seed through the same owner verification and generation guard as production. */
export async function seedLastKnownBoard(record: LastKnownBoard): Promise<boolean> {
  const generation = await establishBoardOwner(record.owner, await readBoardSessionGeneration());
  return generation === null ? false : saveLastKnownBoard(record, generation);
}
