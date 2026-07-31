"""Switch platform for Tion Lite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .entity import TionBleEntity
from .protocol import TionLiteState


@dataclass(frozen=True, kw_only=True)
class TionSwitchDescription(SwitchEntityDescription):
    """Describe a Tion Lite switch."""

    value_fn: Callable[[TionLiteState], bool]
    state_field: str
    requires_heater: bool = False


SWITCHES = (
    TionSwitchDescription(
        key="heater",
        translation_key="heater",
        icon="mdi:radiator",
        value_fn=lambda state: state.heater,
        state_field="heater",
        requires_heater=True,
    ),
    TionSwitchDescription(
        key="led",
        translation_key="led",
        icon="mdi:led-on",
        value_fn=lambda state: state.led,
        state_field="led",
    ),
    TionSwitchDescription(
        key="sound",
        translation_key="sound",
        icon="mdi:volume-high",
        value_fn=lambda state: state.sound,
        state_field="sound",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tion Lite switches."""
    state = entry.runtime_data.coordinator.data
    async_add_entities(
        TionLiteSwitch(entry, description)
        for description in SWITCHES
        if not description.requires_heater or state.heater_present
    )


class TionLiteSwitch(TionBleEntity, SwitchEntity):
    """A configurable Tion Lite switch."""

    entity_description: TionSwitchDescription

    def __init__(
        self,
        entry: TionBleConfigEntry,
        description: TionSwitchDescription,
    ) -> None:
        """Initialize a switch."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the switch state."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn on the setting."""
        await self.coordinator.async_set_state(
            **{self.entity_description.state_field: True}
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn off the setting."""
        await self.coordinator.async_set_state(
            **{self.entity_description.state_field: False}
        )
