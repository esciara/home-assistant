"""Tests for the EnOcean binary sensor platform."""

from unittest.mock import Mock

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import async_receive_telegram, async_setup_yaml_platform, erp1_telegram

from tests.common import async_capture_events

ROCKER_ID = [0x01, 0x02, 0x03, 0x04]
OTHER_ID = [0x0A, 0x0B, 0x0C, 0x0D]
ROCKER_CONFIG = {"id": ROCKER_ID, "name": "Rocker"}
ENTITY_ID = "binary_sensor.rocker"

EVENT_BUTTON_PRESSED = "button_pressed"

RORG_RPS = 0xF6
STATUS_PRESSED = 0x30
STATUS_RELEASED = 0x20


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
    ("action", "which", "onoff"),
    [
        pytest.param(0x70, 0, 0, id="button_0_off"),
        pytest.param(0x50, 0, 1, id="button_0_on"),
        pytest.param(0x30, 1, 0, id="button_1_off"),
        pytest.param(0x10, 1, 1, id="button_1_on"),
        pytest.param(0x37, 10, 0, id="both_buttons_off"),
        pytest.param(0x15, 10, 1, id="both_buttons_on"),
    ],
)
async def test_button_pressed_event(
    hass: HomeAssistant, mock_gateway: Mock, action: int, which: int, onoff: int
) -> None:
    """Test a press fires a bus event and leaves the entity state unknown."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_telegram(
        hass,
        mock_gateway,
        erp1_telegram(RORG_RPS, [action], ROCKER_ID, status=STATUS_PRESSED),
    )

    assert [event.data for event in events] == [
        {"id": ROCKER_ID, "pushed": 1, "which": which, "onoff": onoff}
    ]
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN


@pytest.mark.usefixtures("init_integration")
async def test_release_event_repeats_last_pressed_button_quirk(
    hass: HomeAssistant, mock_gateway: Mock
) -> None:
    """Test a release event carries the button of the preceding press."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_telegram(
        hass,
        mock_gateway,
        erp1_telegram(RORG_RPS, [0x30], ROCKER_ID, status=STATUS_PRESSED),
    )
    await async_receive_telegram(
        hass,
        mock_gateway,
        erp1_telegram(RORG_RPS, [0x00], ROCKER_ID, status=STATUS_RELEASED),
    )

    assert [event.data for event in events] == [
        {"id": ROCKER_ID, "pushed": 1, "which": 1, "onoff": 0},
        {"id": ROCKER_ID, "pushed": 0, "which": 1, "onoff": 0},
    ]


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("status", "pushed"),
    [
        pytest.param(STATUS_RELEASED, 0, id="release"),
        pytest.param(0x00, None, id="unknown_status"),
    ],
)
async def test_event_before_any_press_quirk(
    hass: HomeAssistant, mock_gateway: Mock, status: int, pushed: int | None
) -> None:
    """Test events before any press report -1 for the button and its state."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_telegram(
        hass, mock_gateway, erp1_telegram(RORG_RPS, [0x00], ROCKER_ID, status=status)
    )

    assert [event.data for event in events] == [
        {"id": ROCKER_ID, "pushed": pushed, "which": -1, "onoff": -1}
    ]


@pytest.mark.usefixtures("init_integration")
async def test_other_sender_ignored(hass: HomeAssistant, mock_gateway: Mock) -> None:
    """Test telegrams from another device fire no event."""
    await async_setup_yaml_platform(hass, Platform.BINARY_SENSOR, ROCKER_CONFIG)
    events = async_capture_events(hass, EVENT_BUTTON_PRESSED)

    await async_receive_telegram(
        hass,
        mock_gateway,
        erp1_telegram(RORG_RPS, [0x70], OTHER_ID, status=STATUS_PRESSED),
    )

    assert events == []
