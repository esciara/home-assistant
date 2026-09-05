"""Support for EnOcean sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from enocean_async import DEVICE_TYPES, EURID, DeviceType, Observable, Observation
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ID,
    CONF_NAME,
    PERCENTAGE,
    STATE_CLOSED,
    STATE_OPEN,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, StateType

from .const import LOGGER
from .entity import EnOceanEntity, combine_hex
from .helpers import EnOceanDevice, async_add_device, validate_device_id

CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_RANGE_FROM = "range_from"
CONF_RANGE_TO = "range_to"

DEFAULT_NAME = "EnOcean sensor"

SENSOR_TYPE_HUMIDITY = "humidity"
SENSOR_TYPE_POWER = "powersensor"
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_WINDOWHANDLE = "windowhandle"

# Temperature scale of the 8 bit A5-02 profiles, all reported over raw values 255..0
A5_02_DEVICE_TYPE_IDS = {
    (-40, 0): "EEP/A5-02-01",
    (-30, 10): "EEP/A5-02-02",
    (-20, 20): "EEP/A5-02-03",
    (-10, 30): "EEP/A5-02-04",
    (0, 40): "EEP/A5-02-05",
    (10, 50): "EEP/A5-02-06",
    (20, 60): "EEP/A5-02-07",
    (30, 70): "EEP/A5-02-08",
    (40, 80): "EEP/A5-02-09",
    (50, 90): "EEP/A5-02-0A",
    (60, 100): "EEP/A5-02-0B",
    (-60, 20): "EEP/A5-02-10",
    (-50, 30): "EEP/A5-02-11",
    (-40, 40): "EEP/A5-02-12",
    (-30, 50): "EEP/A5-02-13",
    (-20, 60): "EEP/A5-02-14",
    (-10, 70): "EEP/A5-02-15",
    (0, 80): "EEP/A5-02-16",
    (10, 90): "EEP/A5-02-17",
    (20, 100): "EEP/A5-02-18",
    (30, 110): "EEP/A5-02-19",
    (40, 120): "EEP/A5-02-1A",
    (50, 130): "EEP/A5-02-1B",
}
# Temperature scale of the A5-04 profiles, reported over raw values 0..250
A5_04_DEVICE_TYPE_IDS = {(0, 40): "EEP/A5-04-01", (-20, 60): "EEP/A5-04-02"}
DEFAULT_TEMPERATURE_DEVICE_TYPE_ID = "EEP/A5-02-05"

WINDOW_STATES = {"closed": STATE_CLOSED, "open": STATE_OPEN, "tilted": "tilt"}


def _temperature_device_type(config: ConfigType) -> DeviceType:
    """Return the profile whose temperature scale matches the configuration."""
    scale = (config[CONF_MIN_TEMP], config[CONF_MAX_TEMP])
    raw_range = (config[CONF_RANGE_FROM], config[CONF_RANGE_TO])
    device_type_id = None
    if raw_range == (255, 0):
        device_type_id = A5_02_DEVICE_TYPE_IDS.get(scale)
    elif raw_range == (0, 250):
        device_type_id = A5_04_DEVICE_TYPE_IDS.get(scale)
    if device_type_id is None:
        LOGGER.warning(
            "Temperature range %s..%s over raw values %s..%s of %s matches no"
            " known profile; decoding as %s",
            *scale,
            *raw_range,
            config[CONF_NAME],
            DEFAULT_TEMPERATURE_DEVICE_TYPE_ID,
        )
        device_type_id = DEFAULT_TEMPERATURE_DEVICE_TYPE_ID
    return DEVICE_TYPES[device_type_id]


@dataclass(frozen=True, kw_only=True)
class EnOceanSensorEntityDescription(SensorEntityDescription):
    """Describes EnOcean sensor entity."""

    device_entity: str
    observable: Observable
    device_type_fn: Callable[[ConfigType], DeviceType]
    value_fn: Callable[[Any], StateType] = lambda value: value


SENSOR_DESC_TEMPERATURE = EnOceanSensorEntityDescription(
    key=SENSOR_TYPE_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    device_entity="temperature",
    observable=Observable.TEMPERATURE,
    device_type_fn=_temperature_device_type,
)

SENSOR_DESC_HUMIDITY = EnOceanSensorEntityDescription(
    key=SENSOR_TYPE_HUMIDITY,
    name="Humidity",
    native_unit_of_measurement=PERCENTAGE,
    device_class=SensorDeviceClass.HUMIDITY,
    state_class=SensorStateClass.MEASUREMENT,
    device_entity="humidity",
    observable=Observable.HUMIDITY,
    device_type_fn=lambda config: DEVICE_TYPES["EEP/A5-04-01"],
)

SENSOR_DESC_POWER = EnOceanSensorEntityDescription(
    key=SENSOR_TYPE_POWER,
    name="Power",
    native_unit_of_measurement=UnitOfPower.WATT,
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    device_entity="power",
    observable=Observable.POWER,
    device_type_fn=lambda config: DEVICE_TYPES["EEP/A5-12-01"],
)

SENSOR_DESC_WINDOWHANDLE = EnOceanSensorEntityDescription(
    key=SENSOR_TYPE_WINDOWHANDLE,
    name="WindowHandle",
    translation_key="window_handle",
    device_entity="window_state",
    observable=Observable.WINDOW_STATE,
    device_type_fn=lambda config: DEVICE_TYPES["EEP/F6-10-00"],
    value_fn=lambda value: WINDOW_STATES[value],
)

SENSOR_DESCRIPTIONS = {
    description.key: description
    for description in (
        SENSOR_DESC_TEMPERATURE,
        SENSOR_DESC_HUMIDITY,
        SENSOR_DESC_POWER,
        SENSOR_DESC_WINDOWHANDLE,
    )
}

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): vol.All(
            cv.ensure_list, [vol.Coerce(int)], validate_device_id
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS, default=SENSOR_TYPE_POWER): cv.string,
        vol.Optional(CONF_MAX_TEMP, default=40): vol.Coerce(int),
        vol.Optional(CONF_MIN_TEMP, default=0): vol.Coerce(int),
        vol.Optional(CONF_RANGE_FROM, default=255): cv.positive_int,
        vol.Optional(CONF_RANGE_TO, default=0): cv.positive_int,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up an EnOcean sensor device."""
    dev_name: str = config[CONF_NAME]
    sensor_type: str = config[CONF_DEVICE_CLASS]

    if (description := SENSOR_DESCRIPTIONS.get(sensor_type)) is None:
        LOGGER.warning("Unknown sensor type %s of %s", sensor_type, dev_name)
        return

    address = EURID(config[CONF_ID])
    async_add_device(
        hass,
        EnOceanDevice(
            address=address,
            device_type=description.device_type_fn(config),
            name=dev_name,
        ),
    )
    async_add_entities([EnOceanSensor(address, dev_name, description)])


class EnOceanSensor(EnOceanEntity, RestoreSensor):
    """Representation of an EnOcean sensor device such as a power meter."""

    entity_description: EnOceanSensorEntityDescription

    def __init__(
        self,
        address: EURID,
        dev_name: str,
        description: EnOceanSensorEntityDescription,
    ) -> None:
        """Initialize the EnOcean sensor device."""
        super().__init__(address)
        self.entity_description = description
        self._attr_name = f"{description.name} {dev_name}"
        self._attr_unique_id = f"{combine_hex(address.bytelist)}-{description.key}"

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last known value."""
        await super().async_added_to_hass()
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = sensor_data.native_value

    @override
    @callback
    def _async_observation_received(self, observation: Observation) -> None:
        """Update the value from an observation of the sensor."""
        if observation.entity != self.entity_description.device_entity:
            return
        self._attr_native_value = self.entity_description.value_fn(
            observation.values[self.entity_description.observable]
        )
        self.async_write_ha_state()
