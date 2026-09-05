"""Tests for the EnOcean light platform."""

from unittest.mock import Mock

from enocean_async.esp3.packet import ESP3Packet, ESP3PacketType
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.light import ATTR_BRIGHTNESS, DOMAIN as LIGHT_DOMAIN
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

LIGHT_ID = [0x01, 0x02, 0x03, 0x04]
OTHER_ID = [0x0A, 0x0B, 0x0C, 0x0D]
SENDER_ID = [0xFF, 0x9A, 0x88, 0x01]
LIGHT_CONFIG = {"id": LIGHT_ID, "sender_id": SENDER_ID, "name": "Dimmer"}
ENTITY_ID = "light.dimmer"

RORG_RPS = 0xF6
RORG_4BS = 0xA5


def central_command(dim_value: int) -> ESP3Packet:
    """Return the 4BS central command the light sends for a dim value."""
    return ESP3Packet(
        ESP3PacketType.RADIO_ERP1,
        data=bytes([0xA5, 0x02, dim_value, 0x01, 0x09, *SENDER_ID, 0x00]),
        optional=b"",
    )


@pytest.mark.usefixtures("init_integration")
async def test_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the registry entry and initial state of a dimmer."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    assert entity_registry.async_get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-entry")
    assert hass.states.get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-state")


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("service_data", "dim_value", "brightness"),
    [
        pytest.param({}, 19, 50, id="default_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 255}, 99, 255, id="full_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 128}, 50, 128, id="half_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 1}, 1, 1, id="minimum_brightness"),
    ],
)
async def test_turn_on(
    hass: HomeAssistant,
    mock_gateway: Mock,
    service_data: dict[str, int],
    dim_value: int,
    brightness: int,
) -> None:
    """Test turning on sends a central dim command scaled to 1..99 percent."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, **service_data},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_gateway.send_esp3_packet.assert_awaited_once_with(central_command(dim_value))
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == brightness


@pytest.mark.usefixtures("init_integration")
async def test_turn_off(hass: HomeAssistant, mock_gateway: Mock) -> None:
    """Test turning off sends a central dim command with value zero."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    mock_gateway.send_esp3_packet.assert_awaited_once_with(central_command(0))
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("dim_value", "state", "brightness"),
    [
        pytest.param(50, STATE_ON, 128, id="half"),
        pytest.param(1, STATE_ON, 2, id="minimum"),
        pytest.param(100, STATE_ON, 256, id="full_exceeds_255_quirk"),
        pytest.param(0, STATE_OFF, None, id="off"),
    ],
)
async def test_dimmer_status(
    hass: HomeAssistant,
    mock_gateway: Mock,
    dim_value: int,
    state: str,
    brightness: int | None,
) -> None:
    """Test the state follows the dim value reported by the dimmer."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await async_receive_telegram(
        hass,
        mock_gateway,
        erp1_telegram(RORG_4BS, [0x02, dim_value, 0x00, 0x08], LIGHT_ID),
    )

    light = hass.states.get(ENTITY_ID)
    assert light.state == state
    assert light.attributes.get(ATTR_BRIGHTNESS) == brightness


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("rorg", "data", "sender"),
    [
        pytest.param(RORG_4BS, [0x01, 0x32, 0x00, 0x08], LIGHT_ID, id="other_command"),
        pytest.param(RORG_RPS, [0x70], LIGHT_ID, id="rps_telegram"),
        pytest.param(RORG_4BS, [0x02, 0x32, 0x00, 0x08], OTHER_ID, id="other_sender"),
    ],
)
async def test_ignored_telegrams(
    hass: HomeAssistant,
    mock_gateway: Mock,
    rorg: int,
    data: list[int],
    sender: list[int],
) -> None:
    """Test telegrams that are not a dimmer status of this light are ignored."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await async_receive_telegram(hass, mock_gateway, erp1_telegram(rorg, data, sender))

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_lights_without_id_collide_quirk(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test every light without an id gets unique id 0, so only the first is created."""
    await async_setup_yaml_platform(
        hass,
        Platform.LIGHT,
        {"sender_id": SENDER_ID, "name": "First"},
        {"sender_id": SENDER_ID, "name": "Second"},
    )

    assert entity_registry.async_get("light.first").unique_id == "0"
    assert hass.states.get("light.second") is None
