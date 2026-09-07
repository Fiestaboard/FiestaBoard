#!/usr/bin/env node

/**
 * Version Sync Script
 * 
 * Synchronizes version across multiple files:
 * - package.json (root)
 * - web/package.json
 * - web/package-lock.json (root version fields only)
 * - src/__init__.py
 * 
 * Usage:
 *   node scripts/version-sync.js               # Just sync versions
 *   node scripts/version-sync.js patch         # Bump patch version
 *   node scripts/version-sync.js minor         # Bump minor version
 *   node scripts/version-sync.js major         # Bump major version
 */

const fs = require('fs');
const path = require('path');

// File paths
const ROOT_DIR = path.join(__dirname, '..');
const ROOT_PACKAGE_JSON = path.join(ROOT_DIR, 'package.json');
const WEB_PACKAGE_JSON = path.join(ROOT_DIR, 'web', 'package.json');
const WEB_PACKAGE_LOCK = path.join(ROOT_DIR, 'web', 'package-lock.json');
const PYTHON_INIT_FILE = path.join(ROOT_DIR, 'src', '__init__.py');

/**
 * Parse semver version string
 */
function parseVersion(version) {
  const match = version.match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!match) {
    throw new Error(`Invalid version format: ${version}`);
  }
  return {
    major: parseInt(match[1], 10),
    minor: parseInt(match[2], 10),
    patch: parseInt(match[3], 10),
  };
}

/**
 * Format version object to string
 */
function formatVersion(version) {
  return `${version.major}.${version.minor}.${version.patch}`;
}

/**
 * Bump version according to type
 */
function bumpVersion(currentVersion, bumpType) {
  const version = parseVersion(currentVersion);
  
  switch (bumpType) {
    case 'major':
      version.major += 1;
      version.minor = 0;
      version.patch = 0;
      break;
    case 'minor':
      version.minor += 1;
      version.patch = 0;
      break;
    case 'patch':
      version.patch += 1;
      break;
    default:
      throw new Error(`Invalid bump type: ${bumpType}. Use: major, minor, or patch`);
  }
  
  return formatVersion(version);
}

/**
 * Read and parse JSON file
 */
function readJsonFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  return JSON.parse(content);
}

/**
 * Write JSON file with formatting
 */
function writeJsonFile(filePath, data) {
  const content = JSON.stringify(data, null, 2) + '\n';
  fs.writeFileSync(filePath, content, 'utf8');
}

/**
 * Update the root version fields in web/package-lock.json.
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

/**
 * Update Python __init__.py file with new version
 */
function updatePythonVersion(filePath, newVersion) {
  let content = fs.readFileSync(filePath, 'utf8');
  
  // Match __version__ = "x.y.z" with various quote styles
  const versionRegex = /__version__\s*=\s*["']([^"']+)["']/;
  const match = content.match(versionRegex);
  
  if (!match) {
    throw new Error(`Could not find __version__ in ${filePath}`);
  }
  
  // Replace with new version, preserving quote style
  content = content.replace(versionRegex, `__version__ = "${newVersion}"`);
  
  fs.writeFileSync(filePath, content, 'utf8');
  
  return match[1]; // Return old version
}

/**
 * Main function
 */
function main() {
  const args = process.argv.slice(2);
  const bumpType = args[0]; // undefined, 'major', 'minor', or 'patch'
  
  console.log('🔄 Version Sync Script\n');
  
  // Read current version from root package.json
  const rootPackage = readJsonFile(ROOT_PACKAGE_JSON);
  let currentVersion = rootPackage.version;
  
  console.log(`📦 Current version: ${currentVersion}`);
  
  // Bump version if requested
  let newVersion = currentVersion;
  if (bumpType) {
    try {
      newVersion = bumpVersion(currentVersion, bumpType);
      console.log(`⬆️  Bumping ${bumpType} version: ${currentVersion} → ${newVersion}\n`);
    } catch (error) {
      console.error(`❌ Error: ${error.message}`);
      process.exit(1);
    }
  } else {
    console.log('ℹ️  No bump requested, syncing current version\n');
  }
  
  // Update root package.json
  if (newVersion !== currentVersion) {
    rootPackage.version = newVersion;
    writeJsonFile(ROOT_PACKAGE_JSON, rootPackage);
    console.log(`✅ Updated ${path.relative(ROOT_DIR, ROOT_PACKAGE_JSON)}: ${newVersion}`);
  } else {
    console.log(`✓  ${path.relative(ROOT_DIR, ROOT_PACKAGE_JSON)}: ${newVersion} (unchanged)`);
  }
  
  // Update web/package.json
  const webPackage = readJsonFile(WEB_PACKAGE_JSON);
  const oldWebVersion = webPackage.version;
  webPackage.version = newVersion;
  writeJsonFile(WEB_PACKAGE_JSON, webPackage);
  
  if (oldWebVersion !== newVersion) {
    console.log(`✅ Updated ${path.relative(ROOT_DIR, WEB_PACKAGE_JSON)}: ${oldWebVersion} → ${newVersion}`);
  } else {
    console.log(`✓  ${path.relative(ROOT_DIR, WEB_PACKAGE_JSON)}: ${newVersion} (unchanged)`);
  }

  // Update web/package-lock.json
  const oldLockVersion = updateLockVersion(WEB_PACKAGE_LOCK, newVersion);

  if (oldLockVersion !== newVersion) {
    console.log(`✅ Updated ${path.relative(ROOT_DIR, WEB_PACKAGE_LOCK)}: ${oldLockVersion} → ${newVersion}`);
  } else {
    console.log(`✓  ${path.relative(ROOT_DIR, WEB_PACKAGE_LOCK)}: ${newVersion} (unchanged)`);
  }
  
  // Update src/__init__.py
  try {
    const oldPythonVersion = updatePythonVersion(PYTHON_INIT_FILE, newVersion);
    if (oldPythonVersion !== newVersion) {
      console.log(`✅ Updated ${path.relative(ROOT_DIR, PYTHON_INIT_FILE)}: ${oldPythonVersion} → ${newVersion}`);
    } else {
      console.log(`✓  ${path.relative(ROOT_DIR, PYTHON_INIT_FILE)}: ${newVersion} (unchanged)`);
    }
  } catch (error) {
    console.error(`❌ Error updating Python file: ${error.message}`);
    process.exit(1);
  }
  
  console.log(`\n✨ Version sync complete: ${newVersion}`);
  
  // Output for CI/CD
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `version=${newVersion}\n`);
    console.log(`\n📤 Exported to GITHUB_OUTPUT: version=${newVersion}`);
  }
}

// Run if called directly
if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(`\n❌ Fatal error: ${error.message}`);
    process.exit(1);
  }
}

