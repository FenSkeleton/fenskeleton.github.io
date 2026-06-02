# Changelog

All notable changes to FenSkeleton are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned

- Spinner visible in more main windows
- Additional visual polish passes
- Cleanup of remaining legacy naming and unused assets
- Improved first-run and newcomer guidance

---

## [0.0.14] — Cleanup in the code tunnels

### Fixed

- Repaired UTF-8 encoding artifacts in add-on metadata
- Corrected repository path display in the installation guide: `zips → repository.fenskeleton`
- Renamed remaining live asset references from `fenlight_*` to `fenskeleton_*`
- Rebuilt the plugin package using Kodi-safe archiving with consistent forward-slash paths

### Removed

- Duplicate legacy FenLight asset folders
- Older plugin zip files from the live repository

### Verified

| Component | Version | Status |
| --- | --- | --- |
| FenSkeleton plugin | `0.0.14` | ✓ |
| Fen-Mage skin | `0.0.9` | ✓ |
| FenSkeleton Repository | `1.0.2` | ✓ |

---

## [0.0.13] — Stable Android checkpoint

First overnight-tested Android TV build.

### Fixed

- Prevented Random Next Up from firing during menu browsing and widget configuration
- Preserved the normal Next Episodes binge-watching flow

### Verified

- Menus remained stable throughout extended browsing sessions
- Overnight playback completed without random episode interruptions
- Loading spinner displayed correctly during all tested actions

---

## [0.0.x] — Foundation

> *Version numbers for these milestones were not formally tracked. Add them as they are recovered.*

### Added

- **Random Next Up** — opt-in shuffle mode that keeps the normal Next Episodes binge flow intact
- Home-screen search with consistent FenSkeleton labelling and normal keyboard and result browsing
- Fen-Mage as the matching lightweight companion skin
- Skin configuration controls accessible directly from the skin settings panel
- GitHub Pages repository for straightforward repository installation

### Fixed

- Metadata and MD5 mismatches in the repository
- Windows packaging standardised on `tar.exe` or 7-Zip

### Removed

- Unnecessary helper add-on dependencies

---

## Packaging rule — permanent reminder

| Tool | Safe for Kodi? |
| --- | --- |
| `tar.exe` on Windows 10+ | ✅ Yes |
| 7-Zip | ✅ Yes |
| `Compress-Archive` in PowerShell | ❌ No — backslash paths |
| Windows right-click → Send to Zip | ❌ No |
