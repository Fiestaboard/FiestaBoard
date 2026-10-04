# First-Party Outputs (Vestaboard, FiestaPanel)

How FiestaBoard gets the code that drives a Vestaboard or a FiestaPanel, and how to work on it.

## Where the code lives

Each first-party output is an output plugin in its own public repository:

| Output | Repository |
| --- | --- |
| `vestaboard` | [Fiestaboard/fiestaboard-output--vestaboard](https://github.com/Fiestaboard/fiestaboard-output--vestaboard) |
| `fiestapanel` | [Fiestaboard/fiestaboard-output--fiestapanel](https://github.com/Fiestaboard/fiestaboard-output--fiestapanel) |

Core holds no copy of either. `outputs.lock.json` pins each one (repository, commit, `output_api`, `tree_sha256`), and the image build fetches those commits into the **output seed** at `/opt/fiestaboard/seed/outputs` (`scripts/seed_outputs.py build`), verifying each commit and digest. Booting never needs the network.

Each also has an **installed copy** in the external plugins directory (`data/external_plugins/<id>`): a checkout of its repository, copied from the seed at boot, that the Integrations page updates in-app. `src/outputs/first_party.py` loads whichever of the two runs (see [Which copy runs](#which-copy-runs)), imported as `plugins.vestaboard` and `plugins.fiestapanel`.

## The trust rule

- An output is first-party only when core drives it itself (`FIRST_PARTY_OUTPUTS` in `src/outputs/registry.py`) **and** the seed's lock pins it as `loadable: true`. An id the lock does not list loads nothing, and its boards stay down with the reason in the log.
- The seed copy's tree digest is checked against the lock's `tree_sha256` every time it loads. A corrupted or edited copy is refused, never run. Only that output is left out; the other still loads.
- Their registry entries are never beta-gated and never replaceable: the output registry holds them as first-party entries (`plugin=False`), whichever copy runs, and refuses a plugin entry with either id.
- Only a checkout of the output's own repository (the lock's `repository`, read from the checkout's `origin`) ever runs. Installing a plugin with either id from the registry or a git URL is refused, and at boot a copy from another repository is set aside as `.<id>.set-aside-<time>` (kept, never run) and replaced by the seed's.
- They can be updated, never uninstalled (`DELETE /plugins/{id}/uninstall` answers 400; `GET /plugins` marks them `required: true`, and the Integrations page offers no Uninstall).

## In-app updates

Like any output plugin, they update from **Integrations** through the three `output_api` gates (plan D8):

1. **Update check** (`check_plugin_update_available`): compares the installed copy's HEAD with its repository's default branch and reads the incoming manifest before anything is pulled; an unsupported `output_api` is held back with the reason. First-party outputs are always checked, whether or not a board uses them.
2. **Update** (`update_external_plugin`): pulls, verifies and reloads; a release that fails verification or does not load (including one that only runs by falling back to the seed) is rolled back to the commit it replaced and not offered again.
3. **Load**: see below.

An applied (or rolled-back) update rebuilds the board runtimes, so boards run the code that now loads: a board's runtime signature includes its output's plugin class.

### Which copy runs

`load_first_party` picks, in order:

1. The dev override (`FIESTABOARD_DEV_OUTPUT_<ID>`), if set.
2. The installed copy, when it is **valid and newer than the seed's pin**: a checkout of the output's repository, a manifest version greater than the seed copy's, a supported `output_api`, a passing install self-check, and a working import.
3. The seed's copy, digest-checked against the lock.

An installed copy at the pinned tree or older runs the seed's copy, silently: boot replaces an older copy with the seed's, so upgrading the image never runs older code than it shipped. An installed copy that is newer but not valid is refused and the seed's copy runs as a **fallback**: an error in `GET /plugins/errors`, and the reason an update that caused it rolls back.

Offline boot needs nothing but the seed: boot copies it into place, and with no installed copy at all the seed's runs.

## Running the tests

The suite needs a built seed. Building one needs the network, so the tests never build it; they read it from `FIESTABOARD_OUTPUT_SEED_DIR` (`tests/conftest.py`).

- **Dev container**: the image already has a seed, so `docker compose -f docker-compose.dev.yml exec fiestaboard pytest` uses it.
- **CI**: the Platform Tests job builds the seed first, then runs each seeded package's own tests (conformance included) against the checkout, then the platform suite.
- **Anywhere else**: build a seed once, then point the variable at it:

  ```bash
  python scripts/seed_outputs.py build --lock outputs.lock.json --dest /tmp/fb-seed
  FIESTABOARD_OUTPUT_SEED_DIR=/tmp/fb-seed pytest
  ```

  Rebuild it after `outputs.lock.json` changes; `tests/test_first_party_seed.py` fails when the seed and the lock disagree.

## Working on a first-party output (dev override)

Point an output at a local checkout of its repository with `FIESTABOARD_DEV_OUTPUT_<ID>`:

```bash
FIESTABOARD_DEV_OUTPUT_VESTABOARD=/path/to/fiestaboard-output--vestaboard
FIESTABOARD_DEV_OUTPUT_FIESTAPANEL=/path/to/fiestaboard-output--fiestapanel
```

That checkout loads instead of the seed's copy, with no digest check, and the log warns that it did. It works for the dev container and for the test suite. In the dev container, mount the checkout first (see the comment in `docker-compose.dev.yml`), then set the variable in `.env` to the path inside the container.

Run the output's own tests from its checkout against your core checkout:

```bash
./run_tests.sh /path/to/FiestaBoard
```

## Releasing a new version

A merged release in the output's repository reaches running installs at once, as an in-app update. **Bump the version on every release** (`manifest.json` and `package.json` together): an installed copy runs only when its version is greater than the seed's.

To make a release what new images ship with (and what offline installs boot):

1. Merge the change in the output's repository, keeping `package.json` and `manifest.json` at the same version.
2. Open a FiestaBoard pull request that bumps the output's `commit` in `outputs.lock.json`, and its `tree_sha256` to the digest of a clean checkout of that commit:

   ```bash
   python scripts/seed_outputs.py digest /path/to/clean/checkout
   ```

3. Rebuild your seed and run the suite. The wire goldens (`tests/test_wire_goldens.py`) must stay byte-identical unless the change means to alter what the device receives.
