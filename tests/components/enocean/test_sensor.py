"""Tests for the EnOcean sensor platform."""

from enocean_async import Gateway
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import async_receive_packet, async_setup_yaml_platform, erp1_packet

from tests.common import mock_restore_cache_with_extra_data

SENSOR_ID = [0x01, 0x02, 0x03, 0x04]
OTHER_ID = [0x0A, 0x0B, 0x0C, 0x0D]

TEMPERATURE_CONFIG = {"id": SENSOR_ID, "name": "Room", "device_class": "temperature"}
HUMIDITY_CONFIG = {"id": SENSOR_ID, "name": "Room", "device_class": "humidity"}
POWER_CONFIG = {"id": SENSOR_ID, "name": "Room"}
WINDOW_HANDLE_CONFIG = {"id": SENSOR_ID, "name": "Room", "device_class": "windowhandle"}
TEMPERATURE_HUMIDITY_SCALE = {"range_from": 0, "range_to": 250}

TEMPERATURE_ENTITY_ID = "sensor.temperature_room"
HUMIDITY_ENTITY_ID = "sensor.humidity_room"
POWER_ENTITY_ID = "sensor.power_room"
WINDOW_HANDLE_ENTITY_ID = "sensor.windowhandle_room"

RORG_RPS = 0xF6
RORG_4BS = 0xA5


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("config", "entity_id"),
    [
        pytest.param(TEMPERATURE_CONFIG, TEMPERATURE_ENTITY_ID, id="temperature"),
        pytest.param(HUMIDITY_CONFIG, HUMIDITY_ENTITY_ID, id="humidity"),
        pytest.param(POWER_CONFIG, POWER_ENTITY_ID, id="power"),
        pytest.param(WINDOW_HANDLE_CONFIG, WINDOW_HANDLE_ENTITY_ID, id="window_handle"),
    ],
)
async def test_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    config: ConfigType,
    entity_id: str,
) -> None:
    """Test the registry entry and initial state of each sensor type."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, config)

    assert entity_registry.async_get(entity_id) == snapshot(name=f"{entity_id}-entry")
    assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("scale", "raw", "expected"),
    [
        pytest.param({}, 0x00, "40.0", id="a5_02_05_maximum"),
        pytest.param({}, 0xFF, "0.0", id="a5_02_05_minimum"),
        pytest.param({}, 0xCC, "8.0", id="a5_02_05"),
        pytest.param({"min_temp": -40, "max_temp": 0}, 0xFF, "-40.0", id="a5_02_01"),
        pytest.param({"min_temp": 50, "max_temp": 130}, 0x00, "130.0", id="a5_02_1b"),
        pytest.param(TEMPERATURE_HUMIDITY_SCALE, 125, "20.0", id="a5_04_01"),
        pytest.param(
            {"min_temp": -20, "max_temp": 60, **TEMPERATURE_HUMIDITY_SCALE},
            0,
            "-20.0",
            id="a5_04_02",
        ),
    ],
)
async def test_temperature(
    hass: HomeAssistant,
    mock_gateway: Gateway,
    scale: ConfigType,
    raw: int,
    expected: str,
) -> None:
    """Test the temperature is decoded with the profile matching the configured scale."""
    await async_setup_yaml_platform(
        hass, Platform.SENSOR, {**TEMPERATURE_CONFIG, **scale}
    )

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, 0x00, raw, 0x08], SENSOR_ID)
    )

    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == expected


@pytest.mark.usefixtures("init_integration")
async def test_temperature_unknown_scale(
    hass: HomeAssistant, mock_gateway: Gateway, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a scale matching no profile is decoded as 0 to 40 degrees."""
    await async_setup_yaml_platform(
        hass, Platform.SENSOR, {**TEMPERATURE_CONFIG, "min_temp": 5, "max_temp": 45}
    )

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, 0x00, 0x00, 0x08], SENSOR_ID)
    )

    assert "matches no known profile; decoding as EEP/A5-02-05" in caplog.text
    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == "40.0"


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    "packet_args",
    [
        pytest.param((RORG_4BS, [0x08, 0x28, 0x0B, 0xF0], SENSOR_ID), id="teach_in"),
        pytest.param((RORG_RPS, [0x70], SENSOR_ID, 0x30), id="rps"),
        pytest.param((RORG_4BS, [0x00, 0x00, 0x80, 0x08], OTHER_ID), id="other_sender"),
    ],
)
async def test_temperature_ignored_telegrams(
    hass: HomeAssistant, mock_gateway: Gateway, packet_args: tuple
) -> None:
    """Test telegrams that are not a data telegram of the sensor are ignored."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, TEMPERATURE_CONFIG)

    await async_receive_packet(hass, mock_gateway, erp1_packet(*packet_args))

    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == STATE_UNKNOWN


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(125, "50.0", id="half"),
        pytest.param(250, "100.0", id="full"),
    ],
)
async def test_humidity(
    hass: HomeAssistant, mock_gateway: Gateway, raw: int, expected: str
) -> None:
    """Test the humidity is decoded from the second data byte."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, HUMIDITY_CONFIG)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, raw, 0x00, 0x08], SENSOR_ID)
    )

    assert hass.states.get(HUMIDITY_ENTITY_ID).state == expected


@pytest.mark.usefixtures("init_integration")
async def test_temperature_and_humidity_of_one_device(
    hass: HomeAssistant, mock_gateway: Gateway, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a temperature and a humidity sensor share the device profile."""
    await async_setup_yaml_platform(
        hass,
        Platform.SENSOR,
        {**TEMPERATURE_CONFIG, **TEMPERATURE_HUMIDITY_SCALE},
        HUMIDITY_CONFIG,
    )

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, 125, 125, 0x08], SENSOR_ID)
    )

    assert "already configured" not in caplog.text
    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == "20.0"
    assert hass.states.get(HUMIDITY_ENTITY_ID).state == "50.0"


@pytest.mark.usefixtures("init_integration")
async def test_conflicting_profiles_keep_the_first(
    hass: HomeAssistant, mock_gateway: Gateway, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a second block with an incompatible profile for a device is reported."""
    await async_setup_yaml_platform(
        hass, Platform.SENSOR, TEMPERATURE_CONFIG, HUMIDITY_CONFIG
    )

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, [0x00, 125, 0x00, 0x08], SENSOR_ID)
    )

    assert (
        "01:02:03:04 is already configured with profile A5-02-05;"
        " ignoring profile A5-04-01 of Room" in caplog.text
    )
    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == "40.0"
    assert hass.states.get(HUMIDITY_ENTITY_ID).state == STATE_UNKNOWN


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param([0x00, 0x00, 0x64, 0x0C], "100.0", id="current_value"),
        pytest.param([0x00, 0x04, 0xD2, 0x0D], "123.4", id="current_value_divisor_10"),
        pytest.param([0x00, 0x00, 0x64, 0x08], STATE_UNKNOWN, id="cumulative_ignored"),
    ],
)
async def test_power(
    hass: HomeAssistant, mock_gateway: Gateway, data: list[int], expected: str
) -> None:
    """Test the power is decoded from A5-12-01 current value telegrams only."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, POWER_CONFIG)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_4BS, data, SENSOR_ID)
    )

    assert hass.states.get(POWER_ENTITY_ID).state == expected


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("action", "expected"),
    [
        pytest.param(0xF0, "closed", id="closed"),
        pytest.param(0xE0, "open", id="open"),
        pytest.param(0xC0, "open", id="open_from_tilted"),
        pytest.param(0xD0, "tilt", id="tilted"),
    ],
)
async def test_window_handle(
    hass: HomeAssistant, mock_gateway: Gateway, action: int, expected: str
) -> None:
    """Test the window handle position is decoded from the RPS action byte."""
    await async_setup_yaml_platform(hass, Platform.SENSOR, WINDOW_HANDLE_CONFIG)

    await async_receive_packet(
        hass, mock_gateway, erp1_packet(RORG_RPS, [action], SENSOR_ID, status=0x20)
    )

    assert hass.states.get(WINDOW_HANDLE_ENTITY_ID).state == expected


@pytest.mark.usefixtures("init_integration")
async def test_restore_last_value(hass: HomeAssistant) -> None:
    """Test the last known value is restored at startup."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(TEMPERATURE_ENTITY_ID, "21.5"),
                {"native_value": 21.5, "native_unit_of_measurement": "°C"},
            ),
        ),
    )

    await async_setup_yaml_platform(hass, Platform.SENSOR, TEMPERATURE_CONFIG)

    assert hass.states.get(TEMPERATURE_ENTITY_ID).state == "21.5"


@pytest.mark.usefixtures("init_integration")
async def test_unknown_sensor_type(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a sensor of an unknown type is not created."""
    await async_setup_yaml_platform(
        hass, Platform.SENSOR, {**TEMPERATURE_CONFIG, "device_class": "pressure"}
    )

    assert "Unknown sensor type pressure of Room" in caplog.text
    assert hass.states.async_entity_ids(SENSOR_DOMAIN) == []
