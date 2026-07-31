"""Test setup that permits isolated imports of integration modules."""

import sys
from pathlib import Path
from types import ModuleType

PACKAGE_NAME = "custom_components.tion_ble"
PACKAGE_PATH = Path(__file__).parents[1] / "custom_components" / "tion_ble"

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
