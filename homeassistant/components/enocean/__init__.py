"""Support for EnOcean devices."""

from enocean_async import Gateway, Observation
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SIGNAL_OBSERVATION
from .helpers import async_register_devices

type EnOceanConfigEntry = ConfigEntry[Gateway]

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_DEVICE): cv.string})}, extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the EnOcean component."""
    # support for text-based configuration (legacy)
    if DOMAIN not in config:
        return True

    if hass.config_entries.async_entries(DOMAIN):
        # We can only have one gateway. If there is already one in the config,
        # there is no need to import the yaml based config.
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
        )
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: EnOceanConfigEntry
) -> bool:
    """Set up an EnOcean gateway for the given entry."""
    gateway = Gateway(port=config_entry.data[CONF_DEVICE])

    @callback
    def _async_observation_received(observation: Observation) -> None:
        async_dispatcher_send(
            hass, SIGNAL_OBSERVATION.format(address=observation.device), observation
        )

    gateway.add_observation_callback(_async_observation_received)

    try:
        await gateway.start()
    except ConnectionError as err:
        await gateway.stop()
        raise ConfigEntryNotReady(f"Failed to start EnOcean gateway: {err}") from err

    async_register_devices(hass, gateway)
    config_entry.runtime_data = gateway
    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: EnOceanConfigEntry
) -> bool:
    """Unload EnOcean config entry: stop the gateway."""

    await config_entry.runtime_data.stop()
    return True
