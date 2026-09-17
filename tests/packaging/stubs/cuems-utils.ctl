# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
#
# equivs template for a STUB cuems-utils, instantiated per version by
# tests/packaging/release-gate-demo.sh (@VERSION@ is substituted). Only the
# version relationship is under test, so the stub carries nothing but a version
# and the one path the counterpart's maintainer scripts require before they will
# configure: /usr/lib/cuems/bin/python3 (cuems-common's postinst exits 1 without
# it, and this package's own venv is rooted at the same prefix).
#
# Adapted from ../cuems-common/tests/packaging/stubs/cuems-utils.ctl, which ran
# the same demonstration for flow 03 on 2026-09-17. A real cuems-utils .deb at
# >= 0.1.0rc16 does not exist: PyPI stops at 0.1.0rc14 and the library is built
# from a sibling checkout, so the versions this repository's bound names can only
# be represented by a stub.
Section: misc
Priority: optional
Standards-Version: 4.6.0

Package: cuems-utils
Version: @VERSION@
Maintainer: CUEMS release-gate demonstration <noreply@stagelab.coop>
Architecture: all
Depends: python3
Links: /usr/bin/python3 /usr/lib/cuems/bin/python3
Description: STUB cuems-utils for the release-gate demonstration — not the real package
 Built by tests/packaging/release-gate-demo.sh inside a disposable environment.
 It provides no library; it exists so dpkg and apt can be watched judging the
 version relationships cuems-nodeconf declares against cuems-utils.
