# Release channel chooser polish

The chooser must keep radio selection separate from installing a channel. Arrow
keys move focus and selection; Switch channel or Enter/Space opens the existing
explicit confirmation. Cancellation keeps the candidate selected and the running
channel badge remains tied to the actual running build.

Return local channel state without remote version discovery. Fetch versions
independently with bounded, cached discovery; render loading and unavailable
states in each row. Confirm a major upgrade only when the target major exceeds
the running version. Translate active base strings and delete unused keys.

Regression checks cover keyboard exploration, explicit activation, cancellation,
version loading/failure, 10-to-11 confirmation and same-major/downgrade switches.
Backend checks cover local-only status, discovery timeout, cache expiry and
concurrent callers. Run full Python and web coverage, static checks, production
build and the channel layout flow with axe, one worker and one spec at a time.
Port the reviewed patch to the existing alpha PR using normal commits. Neither
PR will be merged.
