"""Constants for the EnOcean integration."""

import logging

from homeassistant.const import Platform

DOMAIN = "enocean"

MANUFACTURER = "EnOcean"

ERROR_INVALID_DONGLE_PATH = "invalid_dongle_path"

SIGNAL_OBSERVATION = f"{DOMAIN}_observation_{{address}}"

LOGGER = logging.getLogger(__package__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]
