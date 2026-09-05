"""Helpers for the EnOcean integration."""

from dataclasses import dataclass

from enocean_async import EURID, BaseAddress, DeviceType, Gateway, SenderAddress
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, LOGGER


@dataclass(frozen=True, kw_only=True)
class EnOceanDevice:
    """A device from the YAML configuration."""

    address: EURID
    device_type: DeviceType
    name: str
    sender: SenderAddress | None = None
    # Set by platforms that send commands, which need the device's own profile
    controllable: bool = False


# The library keeps no device registry, so every gateway that starts gets these
DATA_DEVICES: HassKey[dict[EURID, EnOceanDevice]] = HassKey(f"{DOMAIN}_devices")


def validate_device_id(value: list[int]) -> list[int]:
    """Validate a list of bytes as an EnOcean device address."""
    try:
        EURID(value)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err
    return value


def sender_address(value: list[int]) -> SenderAddress:
    """Return the base address or device address represented by a list of bytes."""
    try:
        return BaseAddress(value)
    except ValueError:
        return EURID(value)


def validate_sender_id(value: list[int]) -> list[int]:
    """Validate a list of bytes as an address a telegram can be sent from."""
    try:
        sender_address(value)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err
    return value


@callback
def async_get_gateway(hass: HomeAssistant) -> Gateway:
    """Return the gateway of the loaded hub entry."""
    if not (entries := hass.config_entries.async_loaded_entries(DOMAIN)):
        raise HomeAssistantError("The EnOcean gateway is not connected")
    return entries[0].runtime_data


@callback
def async_add_device(hass: HomeAssistant, device: EnOceanDevice) -> None:
    """Remember a YAML device and register it with the running gateway."""
    devices = hass.data.setdefault(DATA_DEVICES, {})
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if (known := devices.get(device.address)) is not None:
        known_eep = known.device_type.eep
        eep = device.device_type.eep
        if (known_eep.rorg, known_eep.func) == (eep.rorg, eep.func):
            return
        # Whichever platform sets up first, keep the profile that controls the device
        if device.controllable and not known.controllable:
            kept, dropped = device, known
        else:
            kept, dropped = known, device
        LOGGER.error(
            "EnOcean device %s is configured as %s (%s) and as %s (%s);"
            " %s is ignored and will not work",
            device.address,
            kept.device_type.eep,
            kept.name,
            dropped.device_type.eep,
            dropped.name,
            dropped.name,
        )
        if kept is known:
            return
        for entry in entries:
            entry.runtime_data.remove_device(device.address)
    devices[device.address] = device
    for entry in entries:
        _register_device(entry.runtime_data, device)


def register_devices(hass: HomeAssistant, gateway: Gateway) -> None:
    """Register every YAML device with a gateway that just started."""
    for device in hass.data.get(DATA_DEVICES, {}).values():
        _register_device(gateway, device)


def _register_device(gateway: Gateway, device: EnOceanDevice) -> None:
    gateway.add_device(
        address=device.address,
        device_type=device.device_type,
        sender=device.sender,
        name=device.name,
    )
