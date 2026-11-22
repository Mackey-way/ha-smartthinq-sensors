"""Exercise recovery through the Home Assistant config-entry lifecycle."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from custom_components import smartthinq_sensors as lg

from .test_config_flow import CONFIG_RESULT


@pytest.mark.parametrize("failure", ["connect", "empty", "discovery", "missing"])
async def test_recover_after_outage(hass, failure):
    """Retry consecutive failures, then resume discovery with a single client."""
    entry = MockConfigEntry(domain=lg.DOMAIN, data=CONFIG_RESULT)
    entry.add_to_hass(hass)
    client = AsyncMock(has_devices=True)
    failed_client = AsyncMock(has_devices=failure != "empty")
    failed_connection = ConnectionError() if failure == "connect" else failed_client
    discovery = ({}, {}, {})
    discoveries = {
        "discovery": [ConnectionError(), ConnectionError()],
        "missing": [({}, {}, None), ({}, {}, None)],
    }
    with (
        patch.object(
            lg.LGEAuthentication,
            "create_client_from_token",
            side_effect=[failed_connection, failed_connection, client, client],
        ) as connect,
        patch.object(
            lg,
            "lge_devices_setup",
            side_effect=[*discoveries.get(failure, []), discovery, discovery],
        ),
        patch.object(lg, "start_devices_discovery") as start_discovery,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        for expected_calls in (2, 3):
            assert lg.CLIENT not in hass.data[lg.DOMAIN]
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
            await hass.async_block_till_done()
            assert connect.await_count == expected_calls
        assert hass.data[lg.DOMAIN][lg.CLIENT] is client
        start_discovery.assert_called_once()
        assert failed_client.close.await_count == (0 if failure == "connect" else 2)

        # Two appliances can report expired credentials during the same poll.
        async_dispatcher_send(hass, lg.SIGNAL_RELOAD_ENTRY)
        async_dispatcher_send(hass, lg.SIGNAL_RELOAD_ENTRY)
        await hass.async_block_till_done()
        assert connect.await_count == 4
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_cancels_recovery(hass):
    """A disabled entry must stay unloaded after its retry deadline."""
    entry = MockConfigEntry(domain=lg.DOMAIN, data=CONFIG_RESULT)
    entry.add_to_hass(hass)
    with patch.object(
        lg.LGEAuthentication, "create_client_from_token", side_effect=ConnectionError
    ) as connect:
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
        await hass.async_block_till_done()
        connect.assert_awaited_once()
