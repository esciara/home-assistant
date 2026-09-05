"""Tests for the EnOcean switch platform."""

from unittest.mock import Mock

from enocean_async.esp3.packet import ESP3Packet, ESP3PacketType
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.enocean import DOMAIN
from homeassistant.components.enocean.entity import combine_hex
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import async_receive_telegram, async_setup_yaml_platform, erp1_telegram

from tests.common import MockConfigEntry

SWITCH_ID = [0xDE, 0xAD, 0xBE, 0xEF]
CHANNEL = 1
SWITCH_CONFIG = {"id": SWITCH_ID, "channel": CHANNEL, "name": "room0"}
ENTITY_ID = "switch.room0"

RORG_4BS = 0xA5
RORG_VLD = 0xD2


def actuator_set_output(output_value: int) -> ESP3Packet:
    """Return the D2-01 set output command the switch sends for an output value."""
    return ESP3Packet(
        ESP3PacketType.RADIO_ERP1,
        data=bytes([0xD2, 0x01, CHANNEL, output_value, 0x00, 0x00, 0x00, 0x00, 0x00]),
        optional=bytes([0x03, *SWITCH_ID, 0xFF, 0x00]),
    )


def actuator_status_response(channel: int, output_value: int) -> list[int]:
    """Return D2-01 status response data reporting a channel's output value."""
    return [0x04, channel, output_value]


def power_reading(watts: int) -> list[int]:
    """Return A5-12-01 data reporting a current power value."""
    return [*watts.to_bytes(3, "big"), 0x0C]


async def test_unique_id_migration(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test EnOcean switch ID migration."""
    old_unique_id = f"{combine_hex(SWITCH_ID)}"

    entity_entry = entity_registry.async_get_or_create(
        SWITCH_DOMAIN,
        DOMAIN,
        old_unique_id,
        suggested_object_id="room0",
        config_entry=init_integration,
        original_name="room0",
    )

    assert entity_entry.entity_id == ENTITY_ID
    assert entity_entry.unique_id == old_unique_id

    await async_setup_yaml_platform(hass, Platform.SWITCH, SWITCH_CONFIG)

    entity_entry = entity_registry.async_get(ENTITY_ID)
    assert entity_entry.unique_id == f"{combine_hex(SWITCH_ID)}-{CHANNEL}"
    assert (
        entity_registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, old_unique_id)
        is None
    )


@pytest.mark.usefixtures("init_integration")
async def test_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the registry entry and initial state of a switch channel."""
    await async_setup_yaml_platform(hass, Platform.SWITCH, SWITCH_CONFIG)

    assert entity_registry.async_get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-entry")
    assert hass.states.get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-state")


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("service", "output_value", "state"),
    [
        pytest.param(SERVICE_TURN_ON, 0x64, STATE_ON, id="turn_on"),
        pytest.param(SERVICE_TURN_OFF, 0x00, STATE_OFF, id="turn_off"),
    ],
)
async def test_turn_on_off(
    hass: HomeAssistant,
    mock_gateway: Mock,
    service: str,
    output_value: int,
    state: str,
) -> None:
    """Test switching sends a set output command addressed to the actuator."""
    await async_setup_yaml_platform(hass, Platform.SWITCH, SWITCH_CONFIG)

    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    mock_gateway.send_esp3_packet.assert_awaited_once_with(
        actuator_set_output(output_value)
    )
    assert hass.states.get(ENTITY_ID).state == state


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("telegrams", "state"),
    [
        pytest.param([actuator_status_response(CHANNEL, 0x64)], STATE_ON, id="on"),
        pytest.param(
            [
                actuator_status_response(CHANNEL, 0x64),
                actuator_status_response(CHANNEL, 0x00),
            ],
            STATE_OFF,
            id="off",
        ),
        pytest.param(
            [actuator_status_response(CHANNEL + 1, 0x64)], STATE_OFF, id="other_channel"
        ),
        pytest.param([[0x01, CHANNEL, 0x64]], STATE_OFF, id="other_command"),
    ],
)
async def test_actuator_status(
    hass: HomeAssistant, mock_gateway: Mock, telegrams: list[list[int]], state: str
) -> None:
    """Test the state follows the status responses for the configured channel."""
    await async_setup_yaml_platform(hass, Platform.SWITCH, SWITCH_CONFIG)

    for data in telegrams:
        await async_receive_telegram(
            hass, mock_gateway, erp1_telegram(RORG_VLD, data, SWITCH_ID)
        )

    assert hass.states.get(ENTITY_ID).state == state


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("telegrams", "state"),
    [
        pytest.param([power_reading(100)], STATE_ON, id="above_one_watt_turns_on"),
        pytest.param([power_reading(1)], STATE_OFF, id="one_watt_stays_off"),
        pytest.param(
            [power_reading(100), power_reading(0)],
            STATE_ON,
            id="zero_watts_never_turns_off",
        ),
    ],
)
async def test_power_reading_turns_on_but_never_off_quirk(
    hass: HomeAssistant, mock_gateway: Mock, telegrams: list[list[int]], state: str
) -> None:
    """Test a power reading above 1 W turns the switch on and no reading turns it off."""
    await async_setup_yaml_platform(hass, Platform.SWITCH, SWITCH_CONFIG)

    for data in telegrams:
        await async_receive_telegram(
            hass, mock_gateway, erp1_telegram(RORG_4BS, data, SWITCH_ID)
        )

    assert hass.states.get(ENTITY_ID).state == state
