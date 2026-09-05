"""Test the EnOcean integration."""

from unittest.mock import patch

from enocean_async import Gateway

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import async_receive_packet, async_setup_yaml_platform, erp1_packet

from tests.common import MockConfigEntry

SENSOR_ID = [0x01, 0x02, 0x03, 0x04]
TEMPERATURE_CONFIG = {"id": SENSOR_ID, "name": "Room", "device_class": "temperature"}
TEMPERATURE_ENTITY_ID = "sensor.temperature_room"

RORG_4BS = 0xA5


async def test_device_not_connected(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a config entry is not ready if the device is not connected."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.enocean.Gateway.start",
        side_effect=ConnectionError("Device not found"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the config entry unloads and stops the gateway."""
    assert init_integration.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_yaml_devices_registered_when_gateway_starts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_gateway: Gateway
) -> None:
    """Test devices configured before the hub is set up are registered with it."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, TEMPERATURE_CONFIG)
    assert mock_gateway.device_specs == {}

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, 0x00, 0x00, 0x08], SENSOR_ID)
    )

    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == "40.0"
