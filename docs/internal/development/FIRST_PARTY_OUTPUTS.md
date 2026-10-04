# First-Party Outputs (Vestaboard, FiestaPanel)

How FiestaBoard gets the code that drives a Vestaboard or a FiestaPanel, and how to work on it.

## Where the code lives

Each first-party output is an output plugin in its own public repository:

| Output | Repository |
| --- | --- |
| `vestaboard` | [Fiestaboard/fiestaboard-output--vestaboard](https://github.com/Fiestaboard/fiestaboard-output--vestaboard) |
| `fiestapanel` | [Fiestaboard/fiestaboard-output--fiestapanel](https://github.com/Fiestaboard/fiestaboard-output--fiestapanel) |

Core holds no copy of either. `outputs.lock.json` pins each one (repository, commit, `output_api`, `tree_sha256`), and the image build fetches those commits into the **output seed** at `/opt/fiestaboard/seed/outputs` (`scripts/seed_outputs.py build`), verifying each commit and digest. FiestaBoard never fetches them at runtime.

`src/outputs/first_party.py` loads both from the seed, imported as `plugins.vestaboard` and `plugins.fiestapanel`.

## The trust rule

- An output is first-party only when core drives it itself (`FIRST_PARTY_OUTPUTS` in `src/outputs/registry.py`) **and** the seed's lock pins it as `loadable: true`. An id the lock does not list loads nothing, and its boards stay down with the reason in the log.
- The seed copy's tree digest is checked against the lock's `tree_sha256` every time it loads. A corrupted or edited copy is refused, never run. Only that output is left out; the other still loads.
- Their registry entries are never beta-gated and never replaceable. The plugin loader refuses an installed plugin with either id before importing its code, and the seed never installs them into `external_plugins/`.
- They update only when core's pin moves (see [Releasing a new version](#releasing-a-new-version)). There is no in-app update for them. Rolling back means rolling back the image.

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

1. Merge the change in the output's repository, keeping `package.json` and `manifest.json` at the same version.
2. Open a FiestaBoard pull request that bumps the output's `commit` in `outputs.lock.json`, and its `tree_sha256` to the digest of a clean checkout of that commit:

   ```bash
   python scripts/seed_outputs.py digest /path/to/clean/checkout
   ```

3. Rebuild your seed and run the suite. The wire goldens (`tests/test_wire_goldens.py`) must stay byte-identical unless the change means to alter what the device receives.
