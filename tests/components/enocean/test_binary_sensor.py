"""Tests for the EnOcean binary sensor platform."""

from enocean_async import Gateway
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import async_receive_packet, async_setup_yaml_platform, erp1_packet

from tests.common import async_capture_events

ROCKER_ID = [0x01, 0x02, 0x03, 0x04]
OTHER_ID = [0x0A, 0x0B, 0x0C, 0x0D]
ROCKER_CONFIG = {"id": ROCKER_ID, "name": "Rocker"}
ENTITY_ID = "binary_sensor.rocker"

EVENT_BUTTON_PRESSED = "button_pressed"

RORG_RPS = 0xF6
STATUS_PRESSED = 0x30
STATUS_RELEASED = 0x20


def button_event(pushed: int, which: int, onoff: int) -> dict[str, int | list[int]]:
    """Return the data of a button_pressed event of the rocker."""
    return {"id": ROCKER_ID, "pushed": pushed, "which": which, "onoff": onoff}


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    "config",
    [
        pytest.param(ROCKER_CONFIG, id="without_device_class"),
        pytest.param(
            {**ROCKER_CONFIG, "device_class": "opening"}, id="with_device_class"
        ),
    ],
)
async def test_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    config: ConfigType,
) -> None:
    """Test the registry entry and initial state of a rocker switch."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, config)

    assert entity_registry.async_get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-entry")
    assert hass.states.get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-state")


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("action", "buttons"),
    [
        pytest.param(0x70, [(0, 0)], id="button_0_off"),
        pytest.param(0x50, [(0, 1)], id="button_0_on"),
        pytest.param(0x30, [(1, 0)], id="button_1_off"),
        pytest.param(0x10, [(1, 1)], id="button_1_on"),
        pytest.param(0x37, [(1, 0), (0, 0)], id="both_buttons_off"),
        pytest.param(0x15, [(1, 1), (0, 1)], id="both_buttons_on"),
    ],
)
async def test_button_pressed_event(
    hass: HomeAssistant,
    mock_gateway: Gateway,
    action: int,
    buttons: list[tuple[int, int]],
) -> None:
    """Test a press and its release fire a bus event for every button involved."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [action], ROCKER_ID, STATUS_PRESSED)
    )
    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [0x00], ROCKER_ID, STATUS_RELEASED)
    )

    assert [event.data for event in events] == [
        *(button_event(1, which, onoff) for which, onoff in buttons),
        *(button_event(0, which, onoff) for which, onoff in buttons),
    ]


@pytest.mark.usefixtures("init_integration")
async def test_state_follows_the_button(
    hass: HomeAssistant, mock_gateway: Gateway
) -> None:
    """Test the sensor is on while a button is pressed."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [0x30], ROCKER_ID, STATUS_PRESSED)
    )
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [0x00], ROCKER_ID, STATUS_RELEASED)
    )
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    "status",
    [
        pytest.param(STATUS_RELEASED, id="release"),
        pytest.param(0x00, id="unknown_status"),
    ],
)
async def test_release_before_any_press(
    hass: HomeAssistant, mock_gateway: Gateway, status: int
) -> None:
    """Test a release without a preceding press fires no event."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [0x00], ROCKER_ID, status)
    )

    assert events == []
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_other_sender_ignored(hass: HomeAssistant, mock_gateway: Gateway) -> None:
    """Test telegrams from another device fire no event."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [0x70], OTHER_ID, STATUS_PRESSED)
    )

    assert events == []
