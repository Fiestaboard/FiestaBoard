// Clock skew for the whole suite: `TEST_NOW=2026-11-21T12:00:00Z npm test`
// starts the wall clock at that instant (it keeps ticking from there).
//
// CI's "UI Tests (clock skew)" job runs the suite on a Saturday and at a
// month/year boundary, so a test that only passes on the day it was written
// fails on its PR instead of on everyone's PR that weekend (#2571, fixed by
// #2611). Without TEST_NOW this module does nothing.
//
// Only `Date` moves. Timers, `performance.now()` and the event loop are real,
// so nothing runs faster or slower. A test that pins its own clock with
// `vi.useFakeTimers()` / `vi.setSystemTime()` still wins: the fake clock
// replaces this `Date` while installed and `vi.useRealTimers()` restores it.
// setup.ts imports this first, before any module reads the time.

const raw = process.env.TEST_NOW;

if (raw) {
  const target = Date.parse(raw);
  if (Number.isNaN(target)) {
    throw new Error(`TEST_NOW is not a date: ${JSON.stringify(raw)}`);
  }
  const RealDate = Date;
  const realNow = RealDate.now.bind(RealDate);
  const offset = target - realNow();
  const now = () => realNow() + offset;

  // A plain property, so `vi.spyOn(Date, "now")` can still replace and
  // restore it.
  RealDate.now = now;
  globalThis.Date = new Proxy(RealDate, {
    // `new Date()` is "now"; every other form (`new Date(ms)`, strings,
    // fields) is an explicit instant and stays as it is.
    construct(Target, args, newTarget) {
      return Reflect.construct(Target, args.length === 0 ? [now()] : args, newTarget);
    },
    // `Date()` called as a function returns the current time as a string.
    apply() {
      return new RealDate(now()).toString();
    },
  });
}

export {};
