"""Tests of the EnOcean integration."""

from unittest.mock import Mock

from enocean_async import ERP1Telegram
from enocean_async.esp3.packet import ESP3Packet, ESP3PacketType

from homeassistant.components.enocean.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component

# Sub-telegram count, broadcast destination, RSSI and security level as a dongle reports them.
TELEGRAM_OPTIONAL = bytes([0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x2D, 0x00])


def erp1_telegram(
    rorg: int, data: list[int], sender: list[int], status: int = 0x00
) -> ERP1Telegram:
    """Build an ERP1 telegram from its wire representation."""
    packet = ESP3Packet(
        ESP3PacketType.RADIO_ERP1,
        data=bytes([rorg, *data, *sender, status]),
        optional=TELEGRAM_OPTIONAL,
    )
    return ERP1Telegram.from_esp3(packet)


async def async_receive_telegram(
    hass: HomeAssistant, mock_gateway: Mock, telegram: ERP1Telegram
) -> None:
    """Deliver a telegram through the callback the integration registered on the gateway."""
    receive = mock_gateway.add_erp1_received_callback.call_args.args[0]
    receive(telegram)
    await hass.async_block_till_done()


async def async_setup_yaml_platform(
    hass: HomeAssistant, platform: Platform, *devices: ConfigType
) -> None:
    """Set up EnOcean devices from legacy YAML platform configuration."""
    assert await async_setup_component(
        hass,
        platform,
        {platform: [{"platform": DOMAIN, **device} for device in devices]},
    )
    await hass.async_block_till_done()
