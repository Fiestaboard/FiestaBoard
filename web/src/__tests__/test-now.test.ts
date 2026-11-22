/**
 * The TEST_NOW clock shim (test-now.ts, installed by setup.ts). CI's clock-skew
 * job runs this file under each instant before the suite, so a shim that
 * stopped moving the clock fails loudly instead of letting every leg pass.
 * Without TEST_NOW (plain `npm test`) it checks the shim stays out of the way.
 */
import { describe, expect, it } from "vitest";

// The real wall clock, independent of `Date`.
const realNow = () => performance.timeOrigin + performance.now();
const raw = process.env.TEST_NOW;
// Generous: a loaded CI worker can take a while between setup and here.
const SLACK_MS = 60_000;

describe.runIf(raw)("with TEST_NOW set", () => {
  const target = Date.parse(raw ?? "");

  it("starts Date.now() at TEST_NOW", () => {
    expect(Math.abs(Date.now() - target)).toBeLessThan(SLACK_MS);
  });

  it("starts new Date() at TEST_NOW", () => {
    expect(Math.abs(new Date().getTime() - target)).toBeLessThan(SLACK_MS);
  });

  it("starts Date() (called as a function) at TEST_NOW", () => {
    // Date() strings have second precision.
    expect(Math.abs(Date.parse(Date()) - target)).toBeLessThan(SLACK_MS);
  });

  it("keeps the clock ticking", async () => {
    const before = Date.now();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(Date.now()).toBeGreaterThan(before);
  });

  it("leaves explicit instants and the static helpers alone", () => {
    expect(new Date(0).getTime()).toBe(0);
    expect(new Date("2001-02-03T04:05:06Z").getTime()).toBe(981173106000);
    expect(Date.parse("2001-02-03T04:05:06Z")).toBe(981173106000);
    expect(Date.UTC(2001, 1, 3, 4, 5, 6)).toBe(981173106000);
    expect(new Date()).toBeInstanceOf(Date);
  });
});

describe.skipIf(raw)("without TEST_NOW", () => {
  it("leaves Date native", () => {
    // Under the shim `Date` is a Proxy, so a fresh date's constructor is the
    // real Date, not the global one (documented in test-now.ts).
    expect(new Date().constructor).toBe(Date);
    expect(Math.abs(Date.now() - realNow())).toBeLessThan(SLACK_MS);
  });
});
