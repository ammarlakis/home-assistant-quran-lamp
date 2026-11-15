# Changelog

## 0.2.3

- Add HACS and Hassfest validation for shared catalog submission.
- Standardize integration manifest ordering.
- No device behavior changes.

## 0.2.2

- Use neutral prayer synchronization labels and internal names.
- Remove setup-history references and shorten documentation.
- Remove an unused connection helper and standardize code formatting.
- Build release archives with `just package`.
- Preserve existing entity identifiers, stored settings, and device behavior.

## 0.2.1

- Document Marketplace upgrades and rollback while preserving existing device entries.
- Document reproducible release packaging for maintainers.
- No device protocol or entity identifier changes.

## 0.2.0

- First standalone HACS / Marketplace release.
- Uses Home Assistant standard Bluetooth discovery and connections.
- Includes light controls, Quran recitation, translations, ayah selection,
  built-in azan settings, previews and sensor-based prayer synchronization.
- Preserves configuration entry and entity identifiers across upgrades.
- Translation Off wakes a sleeping player and restores paused playback afterward.
