# Plugin uninstall: commit and recovery boundaries

External-plugin uninstall coordinates three kinds of state: saved configuration,
installed code and live plugin objects. The registry owns the operation; the
service supplies connection cleanup after acceptance. The existing built-in,
first-party and in-use-output guards still refuse before mutation.
Output usage is checked again after waiting for the mutation locks, with a
failed second read refusing removal. Board creation does not share this fence;
this recheck is not complete concurrent board-lifecycle serialization.

## Caught-failure contract

The per-plugin directory lock fences staging, the config commit, live retirement
and connection cleanup. Other threads using registry/config metadata APIs wait
during acceptance and its atomic write. Reentrant callbacks, running provider
fetches and the complete install/update load sequence are not one transaction.

1. Verify the installed source against the loader's trusted location. Rename its
   directory into an owned, hidden sibling cache. This preserves a rollback copy
   without needing space for a second full code tree. No registry objects or
   credentials are retired yet.
2. Atomically write config removal for the base and all `base:instance` keys,
   together with the base removal tombstone. Publish the candidate and generation
   only when the write succeeds. Unrelated plugin/settings/marker values remain.
3. Mark the operation committed immediately. Unload/retire the live objects and
   evict modules using the original trusted source root, even though that path
   was staged. Then forget the committed connection IDs outside the registry
   lock, while the directory fence remains held. The service does not purge
   config again afterward.
4. Remove the hidden committed cache outside the registry lock. A failure here
   logs a warning and retains the cache: the plugin is logically uninstalled,
   but this disk cleanup remains pending. Plugin-authored cleanup is also
   asynchronous; it is never awaited under these locks.

A staging or config-write exception before the commit restores the code path,
leaving live objects, modules, saved values, generation and connections unchanged.
It cannot leak rejected config deletions into a later unrelated save.

If restoring code fails, or another directory occupies its original location,
the operation reports recovery needed and preserves its copy. It never overwrites
the replacement. A pending staging cache fences another uninstall until inspected.
Ownership checks also prevent cleanup of a replaced staging directory.

An exception after the config commit cannot roll back the uninstall. The error
states that it committed; a recovery cache is retained and logged. This includes
connection-storage cleanup failures. It is not a transaction across arbitrary
plugin callbacks, connection stores, another process or concurrent provider I/O.

## Operator inspection

The server log identifies a cache named `.<plugin-id>.uninstall-<suffix>` next to
the installed directory. Its child with the plugin's name holds the code tree.
Do not infer whether it should be restored or deleted from its name alone.

- Stop the application and its workers through the supported launcher before
  manual repair. Preserve the cache and relevant logs. Do not print connection
  secrets or full config values into a support report.
- Check only the target's config-key presence, removal marker, current installed
  path and logged operation phase. An unrelated replacement must be preserved.
- For a confirmed precommit failure with original config retained and no new
  installed directory, an operator can restore the retained child to the original
  path, remove only its now-empty staging directory, then restart normally.
- For a confirmed committed uninstall, do not restore old code/settings as a
  substitute for completing cleanup. Inspect the retained cache before removing
  only that verified cache. Connection cleanup may still need attention.
- If phase or provenance is ambiguous, preserve both versions and use a verified
  backup/explicit recovery decision. Do not overwrite a newer installation or
  recursively remove an unfamiliar directory.

There is no automatic startup interpretation or durable journal for these
caches. Process death or power loss between staging and the config commit needs
inspection; directory-entry durability, multiprocess coordination and complete
crash recovery are not established by the caught-failure tests. The old algorithm
deleted code before saving config; staging retains a recoverable copy but does
not constitute release signoff for those remaining gates.
