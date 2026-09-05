"""Representation of an EnOcean device."""

from typing import override

from enocean_async import EURID, Instruction, Observation

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import SIGNAL_OBSERVATION
from .helpers import async_get_gateway


def combine_hex(dev_id: list[int]) -> int:
    """Combine list of integer values to one big integer.

    This function replaces the previously used function from the
    enocean library and is considered tech debt that will have
    to be replaced.
    """
    value = 0
    for byte in dev_id:
        value = (value << 8) | (byte & 0xFF)
    return value


class EnOceanEntity(Entity):
    """Parent class for all entities associated with the EnOcean component."""

    _attr_should_poll = False

    def __init__(self, address: EURID) -> None:
        """Initialize the device."""
        self._address = address

    @override
    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_OBSERVATION.format(address=self._address),
                self._async_observation_received,
            )
        )

    @callback
    def _async_observation_received(self, observation: Observation) -> None:
        """Update the entity from an observation of its device."""

    async def _async_send_command(self, command: Instruction) -> None:
        """Send a command to the device through the gateway."""
        gateway = async_get_gateway(self.hass)
        try:
            await gateway.send_command(self._address, command)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(
                f"Cannot send command to EnOcean device {self._address}: {err}"
            ) from err
