"""Tests of the EnOcean integration."""

import asyncio
from collections.abc import Sequence

from enocean_async import BaseAddress, Gateway
from enocean_async.protocol.esp3.packet import ESP3Packet, ESP3PacketType

from homeassistant.components.enocean.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component

BASE_ID = BaseAddress("FF:9A:88:00")
BROADCAST = (0xFF, 0xFF, 0xFF, 0xFF)

# Sub-telegram count, broadcast destination, RSSI and security level as a dongle reports them.
TELEGRAM_OPTIONAL = bytes([0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x2D, 0x00])


def erp1_packet(
    rorg: int, data: list[int], sender: list[int], status: int = 0x00
) -> ESP3Packet:
    """Build a received ERP1 radio packet from its wire representation."""
    return ESP3Packet(
        ESP3PacketType.RADIO_ERP1,
        data=bytes([rorg, *data, *sender, status]),
        optional=TELEGRAM_OPTIONAL,
    )


def sent_packet(
    rorg: int,
    data: list[int],
    sender: list[int],
    destination: Sequence[int] = BROADCAST,
) -> ESP3Packet:
    """Build the ERP1 radio packet the gateway sends for a telegram."""
    return ESP3Packet(
        ESP3PacketType.RADIO_ERP1,
        data=bytes([rorg, *data, *sender, 0x00]),
        optional=bytes([0x03, *destination, 0xFF, 0x00]),
    )


async def async_receive_packet(
    hass: HomeAssistant, gateway: Gateway, packet: ESP3Packet
) -> None:
    """Feed a packet to the gateway as if the dongle had received it."""
    gateway.process_esp3_packet(packet)
    # The gateway hands observations over through two rounds of call_soon
    for _ in range(3):
        await asyncio.sleep(0)
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
