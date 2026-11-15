"""Pair a lamp and configure prayer time sensors."""

import asyncio
import logging
import re
from contextlib import aclosing

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import DOMAIN
from .connection import Lamp
from .protocol import MODEL, PRAYERS, frame

_LOGGER = logging.getLogger(__name__)


class QuranLampConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak):
        self.address = discovery_info.address.upper()
        await self.async_set_unique_id(self.address)
        self._abort_if_unique_id_configured()
        return await self.async_step_confirm()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "manual":
                return await self.async_step_manual()
            self.address = address
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return await self.async_step_confirm()

        configured = self._async_current_ids()
        addresses = {
            info.address.upper(): f"Quran Lamp ({info.address.upper()})"
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.name == "XDT_SQ112"
        }
        choices = [
            {"value": address, "label": label}
            for address, label in sorted(addresses.items())
            if address not in configured
        ]
        if not choices:
            if addresses:
                return await self.async_step_no_new_lamps()
            return await self.async_step_no_lamps()

        default_address = choices[0]["value"]
        choices.append({"value": "manual", "label": "Enter Bluetooth address manually"})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=default_address): SelectSelector(
                        SelectSelectorConfig(
                            options=choices, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_no_lamps(self, user_input=None):
        return self.async_show_menu(
            step_id="no_lamps", menu_options=["retry", "manual"]
        )

    async def async_step_no_new_lamps(self, user_input=None):
        return self.async_show_menu(
            step_id="no_new_lamps", menu_options=["retry", "manual"]
        )

    async def async_step_retry(self, user_input=None):
        return await self.async_step_user()

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address):
                self.address = address
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                if (error := await self._async_check_lamp()) is None:
                    return self._create_lamp_entry(user_input.get(CONF_NAME))
                errors["base"] = error
            else:
                errors[CONF_ADDRESS] = "invalid_address"
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {vol.Required(CONF_ADDRESS): str, vol.Optional(CONF_NAME): str}
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            if (error := await self._async_check_lamp()) is None:
                return self._create_lamp_entry(user_input.get(CONF_NAME))
            if error == "unsupported_model":
                return self.async_abort(reason=error)
            errors["base"] = error
        return self.async_show_form(
            step_id="confirm",
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_NAME, default=self._default_name): str}),
                user_input or {},
            ),
            description_placeholders={"address": self.address},
        )

    async def _async_check_lamp(self):
        try:
            async with asyncio.timeout(45):
                for attempt in range(3):
                    if attempt:
                        await asyncio.sleep(attempt)
                    try:
                        async with (
                            aclosing(Lamp(self.hass, self.address)) as lamp,
                            lamp.session() as session,
                        ):
                            reply = await session.request(frame(MODEL))
                        break
                    except HomeAssistantError as err:
                        _LOGGER.debug(
                            "Lamp setup connection attempt %s failed: %s",
                            attempt + 1,
                            err,
                        )
                else:
                    return "cannot_connect"
        except TimeoutError:
            return "cannot_connect"
        if reply.rstrip(b"\0 ") != b"SQ953":
            return "unsupported_model"
        return None

    @property
    def _default_name(self):
        suffix = self.address.replace(":", "")[-4:]
        return f"Quran Lamp {suffix}"

    def _create_lamp_entry(self, name):
        return self.async_create_entry(
            title=(name or "").strip() or self._default_name,
            data={CONF_ADDRESS: self.address},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return QuranLampOptionsFlow()


class QuranLampOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required("sync_prayer_times", default=False): bool,
                **{
                    vol.Optional(key): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    )
                    for key in PRAYERS
                },
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                self.config_entry.options,
            ),
        )
