# Quran Lamp for Home Assistant

Local Bluetooth control of SQ953 Quran lamps advertising as `XDT_SQ112`.
Requires Home Assistant 2026.11 or newer and a Bluetooth adapter or proxy
supporting active GATT connections.

## Installation

1. Open HACS / Marketplace → Custom repositories.
2. Add `https://github.com/ammarlakis/home-assistant-quran-lamp` as an Integration.
3. Download Quran Lamp and restart Home Assistant.
4. Open Settings → Devices & services → Add integration → Quran Lamp.

Keep the lamp powered and disconnect the Koran Prayer app during setup.
Nearby lamps appear automatically; manual Bluetooth address entry is also available.
Each configured lamp uses one shared connection and reconnects when needed.

For manual installation, copy `custom_components/quran_lamp` into your Home
Assistant configuration's `custom_components` directory and restart.

## Controls

- Light on/off, brightness and RGB color.
- Quran playback, pause, volume, surah, reciter, translation and ayah selection.
- Built-in azan switch, five prayer sound selectors with individual Off options,
  and preview buttons.
- Stored prayer times and the last successful synchronization timestamp.
- Actions for prayer schedules, azan previews and starting a recitation.

Enable prayer synchronization in the integration options and select time sensors
from any integration. Leave a sensor blank to retain that prayer's stored time.
Synchronization preserves the master azan switch and individual prayer sound
settings. Sunrise is excluded from azan playback.

## Limitations

- Available audio depends on the files installed in the lamp.
- Light state is assumed: the lamp acknowledges commands but has no complete
  light-state query.
- After a reload, the translation dropdown can show the saved language even when
  playback was Arabic-only. Selecting Off reapplies Arabic-only playback.
- Tested with a physical SQ953 over an active Bluetooth proxy. Other models and
  adapter combinations are unverified.

## Updates

Update through HACS / Marketplace and restart when prompted. Keep the existing
integration entry to preserve entity IDs, settings and automations. When moving
from a manual installation, remove its files before downloading through Marketplace.
Back up your configuration before changing installation methods.

To roll back, download a previous release through Marketplace and restart.
Downgrading restores code, not configuration backups.

## Development

Run `just package` (requires `just` and `zip`) to build `dist/quran_lamp.zip`.
The archive contains the integration files at its root. The manifest version
must match the release tag without its leading `v`.

Report issues with the lamp model, Home Assistant version, Bluetooth adapter or
proxy type, and redacted logs. Omit credentials and Bluetooth keys.
