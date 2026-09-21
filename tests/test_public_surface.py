"""The shipped daemon reaches cuemsutils through public paths only (SC-001, FR-001).

`cuemsutils.config` declares `__all__ == []` and `cuemsutils.xml` is internal
machinery; the constitution requires this repository to reach library
functionality through public paths (`cuemsutils.tools.*`, `ConfigManager`).
Feature 001 removed two `cuemsutils.xml` imports and, for want of a public way
to obtain a network-map document, introduced one into `cuemsutils.config`.
Feature 002 removes it: the document now comes from `ConfigManager.network_map`,
which has returned a live one all along.

Two exemptions, neither of them shipped code, and both deliberate:

* **The tests.** They import `CuemsNetworkMapType` to patch its `save` and keep
  writes off the real filesystem (feature 002, FR-007). A test patching a
  collaborator is not the daemon consuming an API.
* **The vendored yardstick** (`specs/planning/yardstick/`). It is cuems-utils'
  own file, byte-identical to their copy, and editing it from this side would
  destroy the equivalence guarantee feature 001 rests on.

Only `cuemsnodeconf/` is scanned, because that is what ships.
"""
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / 'cuemsnodeconf'

# `from cuemsutils.config...` / `import cuemsutils.config...`, and the same for
# .xml — matched only at the start of a line (plus indentation), so that prose
# in a docstring or comment naming the old path does not fail the test.
INTERNAL = re.compile(
    r'^\s*(?:from|import)\s+cuemsutils\.(config|xml)\b', re.MULTILINE
)


def _shipped_modules():
    return sorted(PACKAGE.glob('*.py'))


def test_the_package_exists_where_this_test_expects():
    """Guard: a rename must not turn this test silently green."""
    modules = _shipped_modules()
    assert modules, f'no shipped modules found under {PACKAGE}'
    assert (PACKAGE / 'CuemsNodeConf.py') in modules


@pytest.mark.parametrize('module', _shipped_modules(), ids=lambda p: p.name)
def test_no_internal_cuemsutils_import(module):
    """No shipped module imports from cuemsutils.config or cuemsutils.xml."""
    offenders = INTERNAL.findall(module.read_text())
    assert not offenders, (
        f'{module.name} imports cuemsutils.{offenders[0]} — internal. '
        'Obtain the network-map document from ConfigManager.network_map; see '
        'specs/002-public-network-map-path/contracts/library-surface.md'
    )
