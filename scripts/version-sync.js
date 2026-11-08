#!/usr/bin/env node

/**
 * Version Sync Script
 *
 * Copies the version in the root package.json into every other file that
 * records it:
 * - package-lock.json (root version fields only)
 * - web/package.json
 * - web/package-lock.json (root version fields only)
 * - src/__init__.py
 *
 * Changesets owns the version: `npm run version-packages` runs
 * `changeset version` (which bumps the root package.json and writes
 * CHANGELOG.md) and then this script. Prerelease versions from the alpha
 * branch (`10.4.0-beta.0`) are committed like any other, so the running app's
 * `__version__` is the truth on every channel.
 *
 * Usage:
 *   node scripts/version-sync.js
 */

const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.join(__dirname, '..');
const ROOT_PACKAGE_JSON = path.join(ROOT_DIR, 'package.json');
const ROOT_PACKAGE_LOCK = path.join(ROOT_DIR, 'package-lock.json');
const WEB_PACKAGE_JSON = path.join(ROOT_DIR, 'web', 'package.json');
const WEB_PACKAGE_LOCK = path.join(ROOT_DIR, 'web', 'package-lock.json');
const PYTHON_INIT_FILE = path.join(ROOT_DIR, 'src', '__init__.py');

/** X.Y.Z or X.Y.Z-pre.N — what the update checker's _parse_version accepts. */
const VERSION_RE = /^\d+\.\d+\.\d+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$/;

function readJsonFile(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJsonFile(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

/**
 * Update the root version fields in a package-lock.json.
 *
 * npm records the manifest's own version twice in the lockfile — at the top
 * level and again under packages[""] — and leaving them behind makes the
 * lockfile disagree with the manifest it was generated from. Only those two
 * fields are touched; the dependency tree is npm's to write, so this never
 * needs an install.
 */
function updateLockVersion(filePath, newVersion) {
  const lock = readJsonFile(filePath);
  const oldVersion = lock.version;
  lock.version = newVersion;
  if (lock.packages && lock.packages['']) {
    lock.packages[''].version = newVersion;
  }
  writeJsonFile(filePath, lock);
  return oldVersion;
}

function updatePackageVersion(filePath, newVersion) {
  const pkg = readJsonFile(filePath);
  const oldVersion = pkg.version;
  pkg.version = newVersion;
  writeJsonFile(filePath, pkg);
  return oldVersion;
}

/** Update `__version__ = "x.y.z"` in a Python module. */
function updatePythonVersion(filePath, newVersion) {
  let content = fs.readFileSync(filePath, 'utf8');
  const versionRegex = /__version__\s*=\s*["']([^"']+)["']/;
  const match = content.match(versionRegex);
  if (!match) {
    throw new Error(`Could not find __version__ in ${filePath}`);
  }
  content = content.replace(versionRegex, `__version__ = "${newVersion}"`);
  fs.writeFileSync(filePath, content, 'utf8');
  return match[1];
}

function report(filePath, oldVersion, newVersion) {
  const rel = path.relative(ROOT_DIR, filePath);
  if (oldVersion !== newVersion) {
    console.log(`✅ Updated ${rel}: ${oldVersion} → ${newVersion}`);
  } else {
    console.log(`✓  ${rel}: ${newVersion} (unchanged)`);
  }
}

function main() {
  if (process.argv.length > 2) {
    throw new Error(
      'version-sync.js no longer bumps versions. Add a changeset (`npx changeset`) ' +
        'and let the Release workflow open the Version PR. See docs/internal/development/RELEASING.md.',
    );
  }

  const version = readJsonFile(ROOT_PACKAGE_JSON).version;
  if (!VERSION_RE.test(version)) {
    throw new Error(`Invalid version in package.json: ${version}`);
  }
  console.log(`🔄 Syncing version ${version}\n`);

  report(ROOT_PACKAGE_LOCK, updateLockVersion(ROOT_PACKAGE_LOCK, version), version);
  report(WEB_PACKAGE_JSON, updatePackageVersion(WEB_PACKAGE_JSON, version), version);
  report(WEB_PACKAGE_LOCK, updateLockVersion(WEB_PACKAGE_LOCK, version), version);
  report(PYTHON_INIT_FILE, updatePythonVersion(PYTHON_INIT_FILE, version), version);

  console.log(`\n✨ Version sync complete: ${version}`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(`❌ ${error.message}`);
    process.exit(1);
  }
}

module.exports = { VERSION_RE };
