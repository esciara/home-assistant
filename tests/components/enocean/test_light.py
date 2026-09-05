"""Tests for the EnOcean light platform."""

from enocean_async import Gateway
from enocean_async.protocol.esp3.packet import ESP3Packet
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

from . import async_receive_packet, async_setup_yaml_platform, erp1_packet, sent_packet

LIGHT_ID = [0x01, 0x02, 0x03, 0x04]
OTHER_ID = [0x0A, 0x0B, 0x0C, 0x0D]
SENDER_ID = [0xFF, 0x9A, 0x88, 0x01]
LIGHT_CONFIG = {"id": LIGHT_ID, "sender_id": SENDER_ID, "name": "Dimmer"}
ENTITY_ID = "light.dimmer"

RORG_RPS = 0xF6
RORG_4BS = 0xA5

DIMMER_OFF = [0x02, 0x00, 0x00, 0x08]


def central_dim(dim_value: int, sender: list[int]) -> ESP3Packet:
    """Return the central command dimming to a value that the light sends."""
    return sent_packet(RORG_4BS, [0x02, dim_value, 0x01, 0x09], sender)


def dimmer_status(dim_value: int, on: bool) -> list[int]:
    """Return the data of the status telegram of an Eltako dimmer."""
    return [0x02, dim_value, 0x00, 0x09 if on else 0x08]


async def async_turn_on(hass: HomeAssistant, **service_data: int) -> None:
    """Turn the dimmer on."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, **service_data},
        blocking=True,
    )
    await hass.async_block_till_done()


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
        pytest.param({}, 100, 255, id="default_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 255}, 100, 255, id="full_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 128}, 50, 128, id="half_brightness"),
        pytest.param({ATTR_BRIGHTNESS: 1}, 1, 1, id="minimum_brightness"),
    ],
)
async def test_turn_on(
    hass: HomeAssistant,
    mock_gateway: Gateway,
    service_data: dict[str, int],
    dim_value: int,
    brightness: int,
) -> None:
    """Test turning on sends a central dim command scaled to 1..100 percent."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await async_turn_on(hass, **service_data)

    mock_gateway.send_esp3_packet.assert_awaited_once_with(
        central_dim(dim_value, SENDER_ID)
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == brightness


@pytest.mark.usefixtures("init_integration")
async def test_turn_on_from_device_address(
    hass: HomeAssistant, mock_gateway: Gateway
) -> None:
    """Test the command is sent from a sender id in the device address range."""
    sender_id = [0x01, 0x9A, 0x88, 0x01]
    await async_setup_yaml_platform(
        hass, Platform.LIGHT, {**LIGHT_CONFIG, "sender_id": sender_id}
    )

    await async_turn_on(hass)

    mock_gateway.send_esp3_packet.assert_awaited_once_with(central_dim(100, sender_id))


@pytest.mark.usefixtures("init_integration")
async def test_turn_off(hass: HomeAssistant, mock_gateway: Gateway) -> None:
    """Test turning off sends the dim off command of the dimmer."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    mock_gateway.send_esp3_packet.assert_awaited_once_with(
        sent_packet(RORG_4BS, DIMMER_OFF, SENDER_ID)
    )
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("data", "state", "brightness"),
    [
        pytest.param(dimmer_status(50, on=True), STATE_ON, 128, id="half"),
        pytest.param(dimmer_status(100, on=True), STATE_ON, 255, id="full"),
        pytest.param(dimmer_status(1, on=True), STATE_ON, 3, id="minimum"),
        pytest.param(dimmer_status(0, on=False), STATE_OFF, None, id="off"),
        pytest.param(dimmer_status(50, on=False), STATE_OFF, None, id="switched_off"),
    ],
)
async def test_dimmer_status(
    hass: HomeAssistant,
    mock_gateway: Gateway,
    data: list[int],
    state: str,
    brightness: int | None,
) -> None:
    """Test the state follows the status reported by the dimmer."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, data, LIGHT_ID)
    )

    light = hass.states.get(ENTITY_ID)
    assert light.state == state
    assert light.attributes.get(ATTR_BRIGHTNESS) == brightness


@pytest.mark.usefixtures("init_integration")
async def test_turn_on_returns_to_last_level(
    hass: HomeAssistant, mock_gateway: Gateway
) -> None:
    """Test turning on without a brightness uses the level the dimmer had before."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)
    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, dimmer_status(50, on=True), LIGHT_ID)
    )
    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, dimmer_status(0, on=False), LIGHT_ID)
    )

    await async_turn_on(hass)

    mock_gateway.send_esp3_packet.assert_awaited_once_with(central_dim(50, SENDER_ID))
    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] == 128


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("rorg", "data", "sender"),
    [
        pytest.param(RORG_RPS, [0x70], LIGHT_ID, id="rps_telegram"),
        pytest.param(RORG_4BS, dimmer_status(50, on=True), OTHER_ID, id="other_sender"),
    ],
)
async def test_ignored_telegrams(
    hass: HomeAssistant,
    mock_gateway: Gateway,
    rorg: int,
    data: list[int],
    sender: list[int],
) -> None:
    """Test telegrams that are not a dimmer status of this light are ignored."""
    await async_setup_yaml_platform(hass, Platform.LIGHT, LIGHT_CONFIG)

    await async_receive_packet(hass, mock_gateway, erp1_packet(rorg, data, sender))

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_light_without_id_is_not_created(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a light needs the address of its dimmer."""
    await async_setup_yaml_platform(
        hass, Platform.LIGHT, {"sender_id": SENDER_ID, "name": "First"}
    )

    assert "Light First is not created" in caplog.text
    assert hass.states.async_entity_ids(LIGHT_DOMAIN) == []
