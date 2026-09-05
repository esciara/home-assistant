"""Support for EnOcean binary sensors."""

from typing import override

from enocean_async import (
    DEVICE_TYPES,
    EURID,
    Observable,
    Observation,
    ObservationSource,
)
from enocean_async.semantics.observers.button import HELD, PRESSED
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA as BINARY_SENSOR_PLATFORM_SCHEMA,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .entity import EnOceanEntity, combine_hex
from .helpers import EnOceanDevice, async_add_device, validate_device_id

DEFAULT_NAME = "EnOcean binary sensor"
DEPENDENCIES = ["enocean"]
DEVICE_TYPE_ID = "EEP/F6-02-01"
EVENT_BUTTON_PRESSED = "button_pressed"

# Button of the device spec -> (which, onoff) values of the button_pressed event
BUTTONS = {"b0": (0, 0), "b1": (0, 1), "a0": (1, 0), "a1": (1, 1)}

PLATFORM_SCHEMA = BINARY_SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): vol.All(
            cv.ensure_list, [vol.Coerce(int)], validate_device_id
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Binary Sensor platform for EnOcean."""
    dev_name: str = config[CONF_NAME]
    device_class: BinarySensorDeviceClass | None = config.get(CONF_DEVICE_CLASS)

    address = EURID(config[CONF_ID])
    async_add_device(
        hass,
        EnOceanDevice(
            address=address, device_type=DEVICE_TYPES[DEVICE_TYPE_ID], name=dev_name
        ),
    )
    async_add_entities([EnOceanBinarySensor(address, dev_name, device_class)])


class EnOceanBinarySensor(EnOceanEntity, BinarySensorEntity):
    """Representation of EnOcean binary sensors such as wall switches.

    Supported EEPs (EnOcean Equipment Profiles):
    - F6-02-01 (Light and Blind Control - Application Style 2)
    - F6-02-02 (Light and Blind Control - Application Style 1)
    """

    _attr_is_on = False

    def __init__(
        self,
        address: EURID,
        dev_name: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Initialize the EnOcean binary sensor."""
        super().__init__(address)
        self._attr_device_class = device_class
        self._attr_unique_id = f"{combine_hex(address.bytelist)}-{device_class}"
        self._attr_name = dev_name
        self._pressed: set[str] = set()

    @override
    @callback
    def _async_observation_received(self, observation: Observation) -> None:
        """Track the pressed buttons and fire an event for each telegram."""
        if (button := BUTTONS.get(observation.entity)) is None:
            return

        event: str = observation.values[Observable.BUTTON_EVENT]
        if event in (PRESSED, HELD):
            self._pressed.add(observation.entity)
        else:
            self._pressed.discard(observation.entity)
        self._attr_is_on = bool(self._pressed)
        self.async_write_ha_state()

        # held comes from a timer; the event mirrors received telegrams only
        if event == HELD or observation.source is not ObservationSource.TELEGRAM:
            return
        which, onoff = button
        self.hass.bus.async_fire(
            EVENT_BUTTON_PRESSED,
            {
                "id": self._address.bytelist,
                "pushed": int(event == PRESSED),
                "which": which,
                "onoff": onoff,
            },
        )
