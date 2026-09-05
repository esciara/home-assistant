"""Support for EnOcean light sources."""

from typing import Any, override

from enocean_async import (
    DEVICE_TYPES,
    EURID,
    CentralDim,
    CentralDimOff,
    Observable,
    Observation,
)
import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA as LIGHT_PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
)
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import LOGGER
from .entity import EnOceanEntity, combine_hex
from .helpers import (
    EnOceanDevice,
    async_add_device,
    sender_address,
    validate_device_id,
    validate_sender_id,
)

CONF_SENDER_ID = "sender_id"

DEFAULT_NAME = "EnOcean Light"
DEVICE_TYPE_ID = "ELTAKO/FUD61NPN"

BRIGHTNESS_SCALE = (1, 100)

PLATFORM_SCHEMA = LIGHT_PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_ID, default=[]): vol.All(
            cv.ensure_list, [vol.Coerce(int)], vol.Any([], validate_device_id)
        ),
        vol.Required(CONF_SENDER_ID): vol.All(
            cv.ensure_list, [vol.Coerce(int)], validate_sender_id
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the EnOcean light platform."""
    sender_id: list[int] = config[CONF_SENDER_ID]
    dev_name: str = config[CONF_NAME]
    dev_id: list[int] = config[CONF_ID]

    if not dev_id:
        LOGGER.warning(
            "Light %s is not created: the address of the dimmer (id) is required",
            dev_name,
        )
        return

    address = EURID(dev_id)
    async_add_device(
        hass,
        EnOceanDevice(
            address=address,
            device_type=DEVICE_TYPES[DEVICE_TYPE_ID],
            name=dev_name,
            sender=sender_address(sender_id),
        ),
    )
    async_add_entities([EnOceanLight(address, dev_id, dev_name)])


class EnOceanLight(EnOceanEntity, LightEntity):
    """Representation of an EnOcean light source."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_brightness = 255
    _attr_is_on = False

    def __init__(self, address: EURID, dev_id: list[int], dev_name: str) -> None:
        """Initialize the EnOcean light source."""
        super().__init__(address)
        self._attr_unique_id = str(combine_hex(dev_id))
        self._attr_name = dev_name

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light source on or sets a specific dimmer value."""
        brightness: int = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
        # The lowest brightness must stay a visible level rather than round to off
        dim_value = max(1, round(brightness_to_value(BRIGHTNESS_SCALE, brightness)))
        await self._async_send_command(CentralDim(dim_value=dim_value))
        self._attr_brightness = brightness
        self._attr_is_on = True
        self.async_write_ha_state()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light source off."""
        await self._async_send_command(CentralDimOff())
        self._attr_is_on = False
        self.async_write_ha_state()

    @override
    @callback
    def _async_observation_received(self, observation: Observation) -> None:
        """Update the state from the status reported by the dimmer."""
        if observation.entity == "dimmer_state":
            self._attr_is_on = observation.values[Observable.SWITCH_STATE]
        elif (
            observation.entity == "light"
            and (output := observation.values[Observable.OUTPUT_VALUE]) > 0
        ):
            # A dimmer that is off reports 0; keep the level turn_on returns to
            self._attr_brightness = value_to_brightness(BRIGHTNESS_SCALE, output)
        else:
            return
        self.async_write_ha_state()
