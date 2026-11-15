"""BLE commands used by Koran Prayer 3.1 for the SQ953."""

from datetime import datetime, time

WRITE_UUID = "0000ae01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ae02-0000-1000-8000-00805f9b34fb"
PRAYERS = ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha")

MODEL = 0x00
POWER_TOGGLE = 0x01
PLAY_PAUSE = 0x02
PREVIOUS = 0x03
NEXT = 0x04
PLAYBACK_MODE = 0x07
NEXT_TRANSLATION = 0x08
MP3 = 0x0A
GET_CHAPTER = 0x13
SET_LIGHT_LEVEL = 0x1E
LIGHT_RGB = 0x33
SET_RECITER = 0x37
SET_TRANSLATION = 0x38
VOLUME = 0x41
SET_VOLUME = 0x42
PLAY_STATUS = 0x60
GET_RECITER = 0x16
GET_TRANSLATION = 0x17
GET_RECITER_IDS = 0x72
GET_TRANSLATION_IDS = 0x75
GET_RECITER_NAME = 0x76
GET_TRANSLATION_NAME = 0x77
CLOCK = 0x90
SET_SCHEDULE = 0x92
SCHEDULE = 0x91
DISPLAY_SCHEDULE = 0x93
AZAN_ENABLE = 0x94
AZAN_STATUS = 0x95
AZAN_SLOT_ENABLE = 0x98
AZAN_SLOT_STATUS = 0x99
AZAN_TONE = 0x9E
GET_AZAN_TONE = 0x9F
STOP_PREVIEW = 0xA0


# The vendor app uses these labels for standard IDs without querying names.
TRANSLATION_NAMES = dict(
    zip(
        (*range(1, 15), *range(16, 27)),
        (
            "English",
            "Urdu",
            "French",
            "Bengali",
            "Dari",
            "Indonesian",
            "Malay",
            "Pashto",
            "Farsi",
            "Somali",
            "Swahili",
            "Turkish",
            "Hindi",
            "Tamil",
            "Russian",
            "Uzbek",
            "Azerbaijani",
            "Gujarati",
            "Kazakh",
            "Spanish",
            "Bosnian",
            "Malayalam",
            "Persian",
            "German",
            "Kurdish",
        ),
        strict=True,
    )
)


def frame(command: int, *data: int) -> bytes:
    return bytes((0xEA, command, *data, 0, 0xAE))


def notification(packet: bytes) -> tuple[int, bytes] | None:
    if len(packet) >= 4 and packet[0] == 0xEB and packet[-2:] == b"\x00\xae":
        return packet[1], bytes(packet[2:-2])
    return None


def clock(now: datetime) -> bytes:
    return frame(
        CLOCK,
        now.year >> 8,
        now.year & 255,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second,
    )


def schedule(original: bytes, times: tuple[time | None, ...]) -> bytes:
    if len(times) != len(PRAYERS):
        raise ValueError("Supply all six prayer slots")
    payload = bytearray(original)
    for offset, prayer_time in enumerate(times):
        if prayer_time is not None:
            start = 1 + 2 * offset
            payload[start : start + 2] = (prayer_time.hour, prayer_time.minute)
    return frame(SET_SCHEDULE, *payload)


def surah(number: int, ayah: int) -> bytes:
    if not 1 <= number <= 114 or not 1 <= ayah <= 286:
        raise ValueError("Surah must be 1–114 and ayah must be 1–286")
    # The app sends zero-based chapter and verse indexes.
    index = ayah - 1
    return frame(0x15, number - 1, index >> 8, index & 255)
