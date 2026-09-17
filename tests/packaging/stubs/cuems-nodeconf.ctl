# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
#
# equivs template for a STUB cuems-nodeconf at the PRE-CUTOVER release, used by
# tests/packaging/release-gate-demo.sh ONLY as a fallback: the demonstration
# builds the real 0.1.0-7 package from 478bc49 first, and falls back to this stub
# just if that build fails (its older packaging may no longer build here). The
# evidence file records which of the two was used, per scenario.
#
# The relationships below are 478bc49's exactly (debian/control:18-19 at that
# commit) — the release before the discovery cutover, whose bound on
# cuems-common is a bare floor that does NOT refuse a renamed counterpart. That
# is the half-renamed combination this repository's own
# Breaks: cuems-common (<< 1.3.0-23~) closes from the other side.
Section: misc
Priority: optional
Standards-Version: 4.6.0

Package: cuems-nodeconf
Version: @VERSION@
Maintainer: CUEMS release-gate demonstration <noreply@stagelab.coop>
Architecture: all
Depends: cuems-utils (>= 0.1.0rc5), cuems-common (>= 1.0.0)
Description: STUB pre-cutover cuems-nodeconf for the release-gate demonstration — not the real package
 Built by tests/packaging/release-gate-demo.sh inside a disposable environment.
 It provides no daemon; it exists so dpkg and apt can be watched judging the
 Breaks that cuems-common declares against cuems-nodeconf, when the real
 pre-cutover package cannot be rebuilt.
