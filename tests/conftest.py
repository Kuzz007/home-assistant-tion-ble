"""Test setup that permits isolated imports of integration modules."""

import sys
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType

PACKAGE_NAME = "custom_components.tion_ble"
PACKAGE_PATH = Path(__file__).parents[1] / "custom_components" / "tion_ble"

# Permit the pure unit tests to run without installing all of Home Assistant.
if find_spec("homeassistant") is None:
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    components = ModuleType("homeassistant.components")
    components.__path__ = []
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.components", components)
    sys.modules.setdefault("homeassistant.core", core)

# Unit tests do not use Home Assistant's scanner implementation. Stub it so
# importing the client does not pull optional USB watcher dependencies into the
# isolated test environment.
sys.modules.setdefault(
    "homeassistant.components.bluetooth",
    ModuleType("homeassistant.components.bluetooth"),
)

package = ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
package.TionBleConfigEntry = object
sys.modules.setdefault(PACKAGE_NAME, package)
