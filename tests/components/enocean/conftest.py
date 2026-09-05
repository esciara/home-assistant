"""Fixtures for EnOcean integration tests."""

from collections.abc import Generator
from typing import Final
from unittest.mock import AsyncMock, patch

from enocean_async import Gateway
from enocean_async.gateway import SendResult
import pytest

from homeassistant.components.enocean.const import DOMAIN
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant

from . import BASE_ID

from tests.common import MockConfigEntry

ENTRY_CONFIG: Final[dict[str, str]] = {
    CONF_DEVICE: "/dev/ttyUSB0",
}


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="device_chip_id",
        data=ENTRY_CONFIG,
    )


@pytest.fixture
def mock_gateway() -> Generator[Gateway]:
    """Return the gateway of the integration, kept away from the serial port."""
    gateway = Gateway(port=ENTRY_CONFIG[CONF_DEVICE])
    # start() is replaced, so seed the base id it would have fetched from the dongle
    gateway._Gateway__base_id = BASE_ID
    with (
        patch("homeassistant.components.enocean.Gateway", return_value=gateway),
        patch.object(gateway, "start", AsyncMock()),
        patch.object(
            gateway,
            "send_esp3_packet",
            AsyncMock(return_value=SendResult(response=None, duration_ms=None)),
        ),
    ):
        yield gateway


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_gateway: Gateway
) -> MockConfigEntry:
    """Set up the EnOcean hub config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
