"""Fixtures for EnOcean integration tests."""

from collections.abc import Generator
from typing import Final
from unittest.mock import Mock, patch

from enocean_async import Gateway
import pytest

from homeassistant.components.enocean.const import DOMAIN
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant

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
def mock_gateway() -> Generator[Mock]:
    """Replace the EnOcean gateway with a mock that never opens a serial port."""
    gateway = Mock(spec=Gateway)
    with patch("homeassistant.components.enocean.Gateway", return_value=gateway):
        yield gateway


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_gateway: Mock
) -> MockConfigEntry:
    """Set up the EnOcean hub config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
