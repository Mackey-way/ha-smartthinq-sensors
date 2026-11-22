"""Regression tests for registry and temperature API migration."""

from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import device_registry as dr

from custom_components.smartthinq_sensors import DOMAIN, cleanup_orphan_lge_devices
from custom_components.smartthinq_sensors.climate import LGEACClimate
from custom_components.smartthinq_sensors.wideq import TemperatureUnit


async def test_orphan_cleanup_is_scoped_to_entry(hass):
    """Preserve known appliances and devices belonging to a different entry."""
    entry = MockConfigEntry(domain=DOMAIN)
    other = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    registry = dr.async_get(hass)
    devices = [
        registry.async_get_or_create(
            config_entry_id=owner.entry_id, identifiers={(DOMAIN, name)}
        )
        for owner, name in [(entry, "ac"), (entry, "removed"), (other, "fridge")]
    ]
    cleanup_orphan_lge_devices(hass, entry.entry_id, ["ac"])
    assert [registry.async_get(device.id) is not None for device in devices] == [
        True,
        False,
        True,
    ]


def test_ac_temperature_properties_use_device_units():
    """Preserve the AC's native readings on both temperature scales."""
    ac = object.__new__(LGEACClimate)
    for unit, expected, current, target in [
        (TemperatureUnit.CELSIUS, UnitOfTemperature.CELSIUS, 26, 22),
        (TemperatureUnit.FAHRENHEIT, UnitOfTemperature.FAHRENHEIT, 78, 72),
    ]:
        ac._device = SimpleNamespace(temperature_unit=unit)
        ac._api = SimpleNamespace(
            state=SimpleNamespace(current_temp=current, target_temp=target)
        )
        assert ac.native_temperature_unit == expected
        assert ac.native_current_temperature == current
        assert ac.native_target_temperature == target
