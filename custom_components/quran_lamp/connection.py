"""Serial access to the lamp through Home Assistant Bluetooth."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from bleak import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError

from . import protocol as p

class Session:
    def __init__(self, send, is_connected=None, on_notification=None):
        self.send = send
        self._on_notification = on_notification
        self.pending = None
        self._translation_ids = bytearray()
        self._is_connected = is_connected
        self._disconnected = False

    @property
    def connected(self):
        return not self._disconnected and (
            self._is_connected is None or self._is_connected()
        )

    def disconnect(self):
        self._disconnected = True
        if self.pending and not self.pending[1].done():
            self.pending[1].set_exception(HomeAssistantError("The lamp disconnected"))

    def receive(self, _sender, data):
        # The translation catalog can span multiple notifications. Its trailer
        # is 01 ae on intermediate packets and 00 ae on the last packet.
        if (
            self.pending
            and self.pending[0] == p.GET_TRANSLATION_IDS
            and data[:2] == bytes((0xEB, p.GET_TRANSLATION_IDS))
            and data[-2:] == b"\x01\xae"
        ):
            self._translation_ids.extend(data[2:-2])
            return
        packet = p.notification(data)
        if packet is None:
            return
        if self._on_notification:
            self._on_notification(*packet)
        if self.pending:
            opcode, future = self.pending
            if packet[0] == opcode and not future.done():
                if opcode == p.GET_TRANSLATION_IDS:
                    future.set_result(bytes(self._translation_ids) + packet[1])
                else:
                    future.set_result(packet[1])

    async def write(self, packet):
        if not self.connected:
            raise HomeAssistantError("The lamp disconnected")
        try:
            await self.send(packet)
        except (BleakError, OSError, TimeoutError) as err:
            self._disconnected = True
            raise HomeAssistantError(f"Quran lamp Bluetooth error: {err}") from err
        await asyncio.sleep(0.1)

    async def read_azan_tone(self, slot):
        response = await self.request(p.frame(p.GET_AZAN_TONE, slot))
        if len(response) != 2 or response[0] != slot:
            raise HomeAssistantError(
                "The lamp did not report the ringtone for this prayer"
            )
        return response[1]

    async def request(self, packet, *, optional=False):
        result = asyncio.get_running_loop().create_future()
        self.pending = (packet[1], result)
        try:
            await self.write(packet)
            return await asyncio.wait_for(result, timeout=2)
        except asyncio.CancelledError:
            self._disconnected = True
            raise
        except TimeoutError:
            if optional:
                return None
            self._disconnected = True
            raise HomeAssistantError(
                f"The lamp did not answer BLE command 0x{packet[1]:02x}"
            ) from None
        finally:
            self.pending = None
            self._translation_ids.clear()
            if result.done() and not result.cancelled():
                result.exception()
            result.cancel()


class Lamp:
    def __init__(self, hass, address, on_notification=None):
        self.hass = hass
        self.address = address
        self._on_notification = on_notification
        self.playing_before_preview: bool | None = None
        self.lock = asyncio.Lock()
        self._connection = AsyncExitStack()
        self._session = None
        self._closed = False

    async def aclose(self):
        async with self.lock:
            self._closed = True
            self._session = None
            await self._connection.aclose()

    @asynccontextmanager
    async def session(self):
        async with self.lock:
            if self._closed:
                raise HomeAssistantError("The Quran lamp integration is unloading")
            if self._session is None or not self._session.connected:
                self._session = None
                await self._connection.aclose()
                self._session = await self._connection.enter_async_context(
                    self._open_session()
                )
            yield self._session

    @asynccontextmanager
    async def _open_session(self):
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise HomeAssistantError("Quran lamp is outside Bluetooth range")
        client = None
        try:
            client = await establish_connection(
                BleakClientWithServiceCache, device, self.address, max_attempts=3
            )
            characteristic = client.services.get_characteristic(p.WRITE_UUID)
            if characteristic is None:
                raise HomeAssistantError(
                    "The lamp's BLE write characteristic is missing"
                )

            async def send(packet):
                await client.write_gatt_char(
                    characteristic,
                    packet,
                    response="write" in characteristic.properties,
                )

            session = Session(send, lambda: client.is_connected, self._on_notification)
            await client.start_notify(p.NOTIFY_UUID, session.receive)
            yield session
        except (BleakError, OSError, TimeoutError) as err:
            raise HomeAssistantError(f"Quran lamp Bluetooth error: {err}") from err
        finally:
            if client is not None and client.is_connected:
                try:
                    await client.disconnect()
                except (BleakError, OSError, TimeoutError):
                    pass

    async def send(self, packet):
        async with self.session() as session:
            await session.write(packet)
