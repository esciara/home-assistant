"""Support for EnOcean switches."""

from typing import Any, override

from enocean_async import DEVICE_TYPES, EURID, Observable, Observation, SetSwitchOutput
import voluptuous as vol

from homeassistant.components.switch import (
    PLATFORM_SCHEMA as SWITCH_PLATFORM_SCHEMA,
    SwitchEntity,
)
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, LOGGER
from .entity import EnOceanEntity, combine_hex
from .helpers import EnOceanDevice, async_add_device, validate_device_id

CONF_CHANNEL = "channel"
DEFAULT_NAME = "EnOcean Switch"

DEVICE_TYPE_ID_SINGLE_CHANNEL = "EEP/D2-01-0F"
DEVICE_TYPE_ID_TWO_CHANNELS = "EEP/D2-01-12"

PLATFORM_SCHEMA = SWITCH_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): vol.All(
            cv.ensure_list, [vol.Coerce(int)], validate_device_id
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_CHANNEL, default=0): cv.positive_int,
    }
)


def generate_unique_id(dev_id: list[int], channel: int) -> str:
    """Generate a valid unique id."""
    return f"{combine_hex(dev_id)}-{channel}"


def _migrate_to_new_unique_id(
    hass: HomeAssistant, dev_id: list[int], channel: int
) -> None:
    """Migrate old unique ids to new unique ids."""
    old_unique_id = f"{combine_hex(dev_id)}"

    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(Platform.SWITCH, DOMAIN, old_unique_id)

    if entity_id is not None:
        new_unique_id = generate_unique_id(dev_id, channel)
        try:
            ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)
        except ValueError:
            LOGGER.warning(
                "Skip migration of id [%s] to [%s] because it already exists",
                old_unique_id,
                new_unique_id,
            )
        else:
            LOGGER.debug(
                "Migrating unique_id from [%s] to [%s]",
                old_unique_id,
                new_unique_id,
            )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the EnOcean switch platform."""
    channel: int = config[CONF_CHANNEL]
    dev_id: list[int] = config[CONF_ID]
    dev_name: str = config[CONF_NAME]

    _migrate_to_new_unique_id(hass, dev_id, channel)
    address = EURID(dev_id)
    device_type_id = (
        DEVICE_TYPE_ID_TWO_CHANNELS if channel else DEVICE_TYPE_ID_SINGLE_CHANNEL
    )
    async_add_device(
        hass,
        EnOceanDevice(
            address=address, device_type=DEVICE_TYPES[device_type_id], name=dev_name
        ),
    )
    async_add_entities([EnOceanSwitch(address, dev_name, channel)])


class EnOceanSwitch(EnOceanEntity, SwitchEntity):
    """Representation of an EnOcean switch device."""

    _attr_is_on = False

    def __init__(self, address: EURID, dev_name: str, channel: int) -> None:
        """Initialize the EnOcean switch device."""
        super().__init__(address)
        self._channel = channel
        self._device_entity = f"ch{channel + 1}_switch_state"
        self._attr_unique_id = generate_unique_id(address.bytelist, channel)
        self._attr_name = dev_name

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self._async_set_output(100)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self._async_set_output(0)

    async def _async_set_output(self, output_value: int) -> None:
        # The library only addresses a single channel by its raw channel number
        await self._async_send_command(
            SetSwitchOutput(output_value=output_value, entity_id=str(self._channel))
        )
        self._attr_is_on = output_value > 0
        self.async_write_ha_state()

    @override
    @callback
    def _async_observation_received(self, observation: Observation) -> None:
        """Update the state from the status reported for the channel."""
        if observation.entity != self._device_entity:
            return
        self._attr_is_on = observation.values[Observable.SWITCH_STATE]
        self.async_write_ha_state()
