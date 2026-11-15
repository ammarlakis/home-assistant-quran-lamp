# Quran Lamp for Home Assistant

Local control of SQ953 Quran lamps advertising as XDT_SQ112.

The integration uses Home Assistant's standard Bluetooth APIs. It can use a
local adapter or a compatible proxy supporting active GATT connections.
The installed device-specific USB relay has been replaced by this transport.
The generic Bumble HA Proxy is one compatible transport option.

## Installation

Copy the complete `custom_components/quran_lamp` directory into your Home Assistant
configuration's `custom_components` directory, then restart Home Assistant.

Ensure Home Assistant has a working Bluetooth adapter or active Bluetooth proxy.
Open Settings → Devices & services and accept the discovered Quran Lamp, or
choose Add integration → Quran Lamp and select a discovered lamp.
Manual Bluetooth address entry is also available.

Keep the lamp powered and disconnect the Koran Prayer phone app during setup.

## Controls

- Light on/off, brightness, and RGB color. Light state is assumed because the
  protocol acknowledges commands without providing a complete light-state query.
- Quran playback, pause, stop, volume, surah, reciter, translation, and ayah.
  Available audio depends on the files installed in the lamp.
- Built-in azan switch, five prayer ringtone selectors with per-prayer Off,
  and preview buttons.
- Stored prayer times and the last successful sensor-based synchronization.
- Actions for prayer times, azan previews, and starting a recitation.

In the integration options, enable prayer synchronization and choose time sensors
from MAWAQIT or another integration. Leave a sensor blank to retain that prayer's
stored time. Synchronization preserves the master azan switch and individual
prayer sound settings. Sunrise is excluded from azan playback.

The lamp keeps one connection shared by all its entities. It reconnects after
a connection is lost. Each configured lamp has its own connection.

## Validation

The current Bluetooth implementation has been exercised on a physical SQ953
through a generic Bumble ESPHome proxy, including light acknowledgments,
play/pause, advancing ayah reports, and proxy restart recovery. Full migration
validation is ongoing. Other adapter/proxy hardware combinations need testing.

The source is kept locally while validation is completed. It is not yet a
published HACS repository.
