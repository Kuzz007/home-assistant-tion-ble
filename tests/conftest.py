"""Test setup that permits isolated imports of integration modules."""

import sys
from pathlib import Path
from types import ModuleType

PACKAGE_NAME = "custom_components.tion_ble"
PACKAGE_PATH = Path(__file__).parents[1] / "custom_components" / "tion_ble"

package = ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
package.TionBleConfigEntry = object
sys.modules.setdefault(PACKAGE_NAME, package)
