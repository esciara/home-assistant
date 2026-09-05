"""Test the EnOcean integration."""

from unittest.mock import patch

from enocean_async import Gateway
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import async_receive_packet, async_setup_yaml_platform, erp1_packet

from tests.common import MockConfigEntry

SENSOR_ID = [0x01, 0x02, 0x03, 0x04]
THREE_BYTE_ID = [0x01, 0x02, 0x03]
BASE_ADDRESS_ID = [0xFF, 0x80, 0x00, 0x00]
SENDER_ID = [0xFF, 0x9A, 0x88, 0x01]
TEMPERATURE_CONFIG = {"id": SENSOR_ID, "name": "Room", "device_class": "temperature"}
TEMPERATURE_ENTITY_ID = "sensor.temperature_room"

RORG_4BS = 0xA5

ERROR_NOT_FOUR_BYTES = "Byte sequence must have exactly 4 elements"
ERROR_NOT_A_DEVICE = "Device address must be in the range 00:00:00:00 to FF:7F:FF:FF"


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


@pytest.mark.parametrize(
    ("platform", "config", "message"),
    [
        pytest.param(
            Platform.SENSOR,
            {**TEMPERATURE_CONFIG, "id": THREE_BYTE_ID},
            ERROR_NOT_FOUR_BYTES,
            id="sensor_three_byte_id",
        ),
        pytest.param(
            Platform.BINARY_SENSOR,
            {"id": BASE_ADDRESS_ID, "name": "Rocker"},
            ERROR_NOT_A_DEVICE,
            id="binary_sensor_base_address_id",
        ),
        pytest.param(
            Platform.SWITCH,
            {"id": BASE_ADDRESS_ID, "name": "Switch"},
            ERROR_NOT_A_DEVICE,
            id="switch_base_address_id",
        ),
        pytest.param(
            Platform.LIGHT,
            {"id": THREE_BYTE_ID, "sender_id": SENDER_ID, "name": "Dimmer"},
            ERROR_NOT_FOUR_BYTES,
            id="light_three_byte_id",
        ),
        pytest.param(
            Platform.LIGHT,
            {"id": BASE_ADDRESS_ID, "sender_id": SENDER_ID, "name": "Dimmer"},
            ERROR_NOT_A_DEVICE,
            id="light_base_address_id",
        ),
        pytest.param(
            Platform.LIGHT,
            {"id": SENSOR_ID, "sender_id": [0xFF, 0x9A, 0x88], "name": "Dimmer"},
            ERROR_NOT_FOUR_BYTES,
            id="light_three_byte_sender",
        ),
        pytest.param(
            Platform.LIGHT,
            {"sender_id": SENDER_ID, "name": "Dimmer"},
            "required key 'id' not provided",
            id="light_without_id",
        ),
    ],
)
async def test_invalid_device_configuration(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    platform: Platform,
    config: ConfigType,
    message: str,
) -> None:
    """Test a device block with an invalid address fails configuration validation."""
    await async_setup_yaml_platform(hass, platform, config)

    assert f"Invalid config for '{platform}' from integration 'enocean'" in caplog.text
    assert message in caplog.text
    assert hass.states.async_entity_ids(platform) == []
