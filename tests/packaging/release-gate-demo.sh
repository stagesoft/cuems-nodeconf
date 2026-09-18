#!/bin/bash
# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
#
# release-gate-demo.sh — watch dpkg/apt refuse out-of-order CUEMS installs
# (feature 001, T047 / SC-007, quickstart.md §4).
#
# "A gate that has never been demonstrated is a claim." This builds the REAL
# cuems-nodeconf package — this release and the one before the discovery cutover
# — builds the REAL counterpart cuems-common at both sides of its own cutover,
# and replays install scenarios inside an unprivileged, disposable bookworm
# system:
#
#   mmdebstrap --mode=unshare — a user-namespace chroot built as the calling
#   user. Nothing runs as real root, maintainer scripts cannot reach host
#   services, and the /dev/null target leaves nothing behind.
#
# Only RELATIONSHIPS are under test. cuems-utils is an equivs stub: no .deb of
# it exists at >= 0.1.0rc16 (PyPI stops at 0.1.0rc14 and the library is built
# from a sibling checkout), so the versions this package's bound names can only
# be represented by a stub. Every refusal is apt or dpkg refusing the REAL
# cuems-nodeconf or the REAL cuems-common. The evidence file says which.
#
# Adapted from ../cuems-common/tests/packaging/release-gate-demo.sh, which ran
# the same demonstration for flow 03 on 2026-09-17. What differs here is the
# build: this package needs dh-virtualenv, which is not installed on the host and
# must not be installed as root, so the .debs are built inside a second
# unprivileged mmdebstrap run.
#
# Usage:  tests/packaging/release-gate-demo.sh
# Env:    WORK=<dir>      build/scratch directory (default: a new mktemp dir)
#         OUT=<file>      evidence file (default: the feature's evidence/ file)
#         OLD_REF=<ref>   this repo's pre-cutover release (default: 478bc49, 0.1.0-7)
#         COMMON=<path>   cuems-common checkout (default: ../cuems-common)
#         COMMON_NEW=<ref> its renamed release (default: 1a00159, 1.3.0-23). Its debian/
#                  is identical to the merge-gate tag xml-refactor-merge-candidate
#                  (f2fc0f5), so evidence built from either describes the same packages.
#         COMMON_OLD=<ref> its released predecessor (default: rc_1, 1.3.0-22)
#         UTILS=<path>    cuems-utils checkout for the wheel (default: ../cuems-utils)
#         MIRROR=<url>    Debian mirror (default: http://deb.debian.org/debian)
# Needs:  mmdebstrap, uidmap (newuidmap/newgidmap), equivs, dpkg-dev, debhelper,
#         fakeroot, git, uv or pip; /etc/subuid and /etc/subgid ranges for the
#         calling user; network access to the mirror and to PyPI.
# Exit:   0 if every scenario's observed outcome matches its expectation.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
FEATURE="$REPO/specs/001-network-map-object-adoption"
WORK="${WORK:-$(mktemp -d -t cuems-nodeconf-gate-XXXXXX)}"
OUT="${OUT:-$FEATURE/evidence/out-of-order-refusal.txt}"
OLD_REF="${OLD_REF:-478bc49}"
COMMON="${COMMON:-$REPO/../cuems-common}"
COMMON_NEW="${COMMON_NEW:-1a00159}"
COMMON_OLD="${COMMON_OLD:-rc_1}"
UTILS="${UTILS:-$REPO/../cuems-utils}"
MIRROR="${MIRROR:-http://deb.debian.org/debian}"

UTILS_VERSIONS=(0.1.0rc15 0.1.0rc16 0.1.1~rc1)

log() { printf '[release-gate] %s\n' "$*" >&2; }

for tool in mmdebstrap equivs-build dpkg-buildpackage dpkg-parsechangelog dpkg-deb \
            newuidmap newgidmap fakeroot git tar dh; do
    command -v "$tool" >/dev/null 2>&1 || { log "missing required tool: $tool"; exit 2; }
done
command -v uv >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1 \
    || { log "need uv or pip3 to build the cuemsutils wheel"; exit 2; }
grep -q "^$(id -un):" /etc/subuid && grep -q "^$(id -un):" /etc/subgid \
    || { log "no /etc/subuid or /etc/subgid range for $(id -un)"; exit 2; }
[ -d "$COMMON/.git" ] || { log "no cuems-common checkout at $COMMON"; exit 2; }
[ -d "$UTILS/.git" ] || { log "no cuems-utils checkout at $UTILS"; exit 2; }

mkdir -p "$WORK"/{wheels,new/src,old/src,common-new/src,common-old/src,stubs,debs,build}
log "work directory: $WORK"

# --- 1. the library wheel ----------------------------------------------------
# dh_virtualenv's pip must resolve cuemsutils >= 0.1.0rc16, which PyPI does not
# carry (it stops at 0.1.0rc14). The wheel is built from the sibling checkout and
# offered to pip through PIP_FIND_LINKS — see §2 for why that is the supported
# route rather than a debian/rules edit.
UTILS_COMMIT="$(git -C "$UTILS" rev-parse HEAD)"
# Relative to the repository, so the evidence reads the same on any development
# machine. realpath --relative-to turns /.../cuems-nodeconf/../cuems-utils into
# ../cuems-utils; the fallback keeps whatever was given if realpath is absent.
UTILS_REL="$(realpath --relative-to="$REPO" "$UTILS" 2>/dev/null || printf '%s' "$UTILS")"
UTILS_DIRTY=""
[ -n "$(git -C "$UTILS" status --porcelain)" ] && UTILS_DIRTY=" (+ uncommitted changes)"
log "building the cuemsutils wheel from $UTILS_REL @ ${UTILS_COMMIT:0:7}$UTILS_DIRTY"
if command -v uv >/dev/null 2>&1; then
    (cd "$UTILS" && uv build --wheel --out-dir "$WORK/wheels") > "$WORK/wheel.log" 2>&1 \
        || { log "wheel build failed — see $WORK/wheel.log"; exit 1; }
    WHEEL_TOOL="uv build --wheel"
else
    (cd "$UTILS" && pip3 wheel --no-deps -w "$WORK/wheels" .) > "$WORK/wheel.log" 2>&1 \
        || { log "wheel build failed — see $WORK/wheel.log"; exit 1; }
    WHEEL_TOOL="pip3 wheel --no-deps"
fi
WHEEL="$(basename "$(ls "$WORK"/wheels/cuemsutils-*.whl | head -1)")"
log "wheel: $WHEEL"

# --- 2. the real cuems-nodeconf packages, built in an unprivileged chroot -----
# This package Build-Depends on dh-virtualenv, python3-all, python3-dev and
# python3-setuptools; none of the first are on the host, and installing them
# would need root. So the build happens inside its own mmdebstrap --mode=unshare
# run, which needs nothing from the host but the mirror.
#
# HOW cuemsutils REACHES pip: PIP_FIND_LINKS, set for the build only.
# dh-virtualenv 1.2.2 composes its pip command in
# /usr/lib/python3/dist-packages/dh_virtualenv/deployment.py:182
# (pip_prefix + pip_args + args) and runs it at :196 with
# subprocess.check_call(cmd) — with no env= argument anywhere on that path, so
# the child inherits os.environ and PIP_* is honoured. Verified by inspection and
# by `pip config debug`, which reports PIP_FIND_LINKS under env_var. Its
# --extra-pip-arg option would have been the alternative; it is not needed, and
# debian/rules is therefore unchanged by this demonstration.
git -C "$REPO" ls-files -co --exclude-standard -z \
    | tar -C "$REPO" --null -T - -cf - | tar -C "$WORK/new/src" -xf -
NEW_VERSION="$(cd "$WORK/new/src" && dpkg-parsechangelog -SVersion)"
git -C "$REPO" archive "$OLD_REF" | tar -C "$WORK/old/src" -xf -
OLD_VERSION="$(cd "$WORK/old/src" && dpkg-parsechangelog -SVersion)"
log "building cuems-nodeconf $NEW_VERSION (working tree) and $OLD_VERSION ($OLD_REF)"

cp -r "$WORK/new/src" "$WORK/build/new"
cp -r "$WORK/old/src" "$WORK/build/old"
cp "$WORK/wheels/$WHEEL" "$WORK/build/"

cat > "$WORK/build/build.sh" <<'BUILD'
#!/bin/sh
# Runs inside the build chroot. Builds both cuems-nodeconf packages with the
# local cuemsutils wheel on pip's search path.
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get -y --no-install-recommends install \
    dh-virtualenv debhelper dpkg-dev fakeroot build-essential \
    python3-all python3-dev python3-pip python3-setuptools python3-venv \
    python3-netifaces python3-dbus python3-zeroconf python3-systemd \
    > /tmp/build/apt.log 2>&1
dpkg-query -W -f='dh-virtualenv ${Version}\n' dh-virtualenv > /tmp/build/versions.txt
for which in new old; do
    ( cd "/tmp/build/$which" \
      && PIP_FIND_LINKS=/tmp/build PIP_DISABLE_PIP_VERSION_CHECK=1 \
         dpkg-buildpackage -b -us -uc -rfakeroot ) > "/tmp/build/$which.log" 2>&1 \
      && echo "$which OK" >> /tmp/build/result.txt \
      || echo "$which FAILED" >> /tmp/build/result.txt
done
mkdir -p /tmp/build/out
cp /tmp/build/*.deb /tmp/build/out/ 2>/dev/null || true
exit 0
BUILD

mmdebstrap --mode=unshare --variant=apt --include=ca-certificates \
    --customize-hook='mkdir -p "$1/tmp/build"' \
    --customize-hook="copy-in $WORK/build/new $WORK/build/old $WORK/build/$WHEEL $WORK/build/build.sh /tmp/build" \
    --customize-hook='chroot "$1" sh /tmp/build/build.sh' \
    --customize-hook="copy-out /tmp/build/out /tmp/build/result.txt /tmp/build/versions.txt /tmp/build/new.log /tmp/build/old.log $WORK/build" \
    bookworm /dev/null "$MIRROR" > "$WORK/build/mmdebstrap.log" 2>&1 \
    || { log "build chroot failed — see $WORK/build/mmdebstrap.log"; exit 1; }

DHV_VERSION="$(cat "$WORK/build/versions.txt" 2>/dev/null || echo 'dh-virtualenv unknown')"
NEW_DEB="$(ls "$WORK"/build/out/cuems-nodeconf_"$NEW_VERSION"_*.deb 2>/dev/null | head -1 || true)"
OLD_DEB="$(ls "$WORK"/build/out/cuems-nodeconf_"$OLD_VERSION"_*.deb 2>/dev/null | head -1 || true)"
[ -n "$NEW_DEB" ] || { log "cuems-nodeconf $NEW_VERSION did not build — see $WORK/build/new.log"; exit 1; }
cp "$NEW_DEB" "$WORK/debs/cuems-nodeconf_new.deb"

# The pre-cutover release is built for real when it can be; an equivs stub
# carrying 478bc49's exact relationships is the recorded fallback.
OLD_KIND="REAL package built from $OLD_REF"
if [ -n "$OLD_DEB" ]; then
    cp "$OLD_DEB" "$WORK/debs/cuems-nodeconf_old.deb"
else
    log "cuems-nodeconf $OLD_VERSION did not build — falling back to an equivs stub"
    sed "s/@VERSION@/$OLD_VERSION/" "$REPO/tests/packaging/stubs/cuems-nodeconf.ctl" > "$WORK/stubs/nodeconf_old.ctl"
    (cd "$WORK/stubs" && equivs-build nodeconf_old.ctl) > "$WORK/stubs/nodeconf_old.log" 2>&1
    cp "$WORK"/stubs/cuems-nodeconf_"$OLD_VERSION"_all.deb "$WORK/debs/cuems-nodeconf_old.deb"
    OLD_KIND="equivs STUB (the real $OLD_REF build failed; relationships as of that commit)"
fi

# --- 2b. what actually ships -------------------------------------------------
# The local wheel must not leak into the package: debian/rules strips
# site-packages to cuemsnodeconf* and the venv's bin/ to the entry point.
CONTENTS="$WORK/debs/new-contents.txt"
dpkg-deb -c "$WORK/debs/cuems-nodeconf_new.deb" > "$CONTENTS"
LEAKED="$(grep -cE "site-packages/(cuemsutils|peewee|lxml|playhouse|pynng|zeroconf|dbus|systemd|pip|setuptools|wheel)" "$CONTENTS" || true)"
SHIPPED_TESTS="$(grep -cE "/tests/|/specs/" "$CONTENTS" || true)"
HAS_PKG="$(grep -cE "site-packages/cuemsnodeconf" "$CONTENTS" || true)"
HAS_ENTRY="$(grep -cE "usr/lib/cuems/bin/cuems-nodeconf$" "$CONTENTS" || true)"

# --- 3. the real counterparts ------------------------------------------------
log "building cuems-common $COMMON_NEW and $COMMON_OLD (no dh-virtualenv needed)"
COMMON_NEW_COMMIT="$(git -C "$COMMON" rev-parse "$COMMON_NEW")"
COMMON_OLD_COMMIT="$(git -C "$COMMON" rev-parse "$COMMON_OLD")"
git -C "$COMMON" archive "$COMMON_NEW" | tar -C "$WORK/common-new/src" -xf -
git -C "$COMMON" archive "$COMMON_OLD" | tar -C "$WORK/common-old/src" -xf -
COMMON_NEW_VERSION="$(cd "$WORK/common-new/src" && dpkg-parsechangelog -SVersion)"
COMMON_OLD_VERSION="$(cd "$WORK/common-old/src" && dpkg-parsechangelog -SVersion)"
(cd "$WORK/common-new/src" && dpkg-buildpackage -b -us -uc -rfakeroot) > "$WORK/common-new/build.log" 2>&1 \
    || { log "cuems-common $COMMON_NEW build failed — see $WORK/common-new/build.log"; exit 1; }
(cd "$WORK/common-old/src" && dpkg-buildpackage -b -us -uc -rfakeroot) > "$WORK/common-old/build.log" 2>&1 \
    || { log "cuems-common $COMMON_OLD build failed — see $WORK/common-old/build.log"; exit 1; }
cp "$WORK"/common-new/cuems-common_*_all.deb "$WORK/debs/cuems-common_new.deb"
cp "$WORK"/common-old/cuems-common_*_all.deb "$WORK/debs/cuems-common_old.deb"

# --- 4. the library stubs ----------------------------------------------------
for v in "${UTILS_VERSIONS[@]}"; do
    log "stub cuems-utils $v"
    sed "s/@VERSION@/$v/" "$REPO/tests/packaging/stubs/cuems-utils.ctl" > "$WORK/stubs/cuems-utils_$v.ctl"
    (cd "$WORK/stubs" && equivs-build "cuems-utils_$v.ctl") > "$WORK/stubs/cuems-utils_$v.log" 2>&1
    cp "$WORK/stubs/cuems-utils_${v}_all.deb" "$WORK/debs/cuems-utils_$v.deb"
done

# --- 5. the scenarios --------------------------------------------------------
cat > "$WORK/debs/scenarios.sh" <<'SCENARIOS'
#!/bin/sh
# Runs inside the scenario chroot. Never exits non-zero: a failed hook would
# abort mmdebstrap and lose the transcript, and verdicts are compared outside.
G=/tmp/gate/debs
T=/tmp/gate/transcript.txt
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -y --no-remove -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
: > "$T"

# No daemon may start in here: this user-namespace system shares the host's
# network, and avahi-daemon (or this daemon) on unprivileged UDP 5353 would
# announce on the real LAN. Assert the denial rather than assume it, and refuse
# to run any scenario if it is not in force.
if [ -x /usr/sbin/policy-rc.d ]; then
    /usr/sbin/policy-rc.d avahi-daemon start; guard_rc=$?
else
    guard_rc=missing
fi
if [ "$guard_rc" != 101 ]; then
    echo "ABORT: /usr/sbin/policy-rc.d does not deny service starts (exit 101); no scenario was run" >> "$T"
    echo "VERDICT GUARD expected=ACCEPTED observed=ABORTED" >> "$T"
    exit 0
fi
echo "guard: /usr/sbin/policy-rc.d denies service starts (exit 101)" >> "$T"

attempt() { # id expected(ACCEPTED|REFUSED|BREAKS-UNCONFIGURED) title -- command...
    id=$1; expected=$2; title=$3; shift 4
    {
        echo
        echo "=== $id — $title"
        echo "expected: $expected"
        echo "\$ $*"
    } >> "$T"
    "$@" > /tmp/gate/cmd.log 2>&1
    rc=$?
    # A relationship refusal happens before anything is unpacked. A failure after
    # unpacking (a maintainer script erroring) is NOT a refusal and is classed apart,
    # so a broken postinst can never pass as the gate working.
    if [ "$rc" -eq 0 ]; then observed=ACCEPTED; tail -n 15 /tmp/gate/cmd.log >> "$T"
    elif grep -qE "breaks .* and is installed|conflicting packages" /tmp/gate/cmd.log; then
        # dpkg -i unpacks BEFORE it resolves relationships, so a Breaks it does
        # enforce appears as a refusal to configure, not as a pre-unpack refusal.
        # It is still the relationship being enforced — dpkg names it — but it is
        # a different observable outcome from apt's, and is kept distinct rather
        # than folded into REFUSED.
        observed=BREAKS-UNCONFIGURED; tail -n 25 /tmp/gate/cmd.log >> "$T"
    elif grep -qE "installed .* script subprocess returned error|Sub-process /usr/bin/dpkg returned an error|dpkg: error processing package" /tmp/gate/cmd.log; then
        observed=CONFIGURE-FAILED; tail -n 40 /tmp/gate/cmd.log >> "$T"
    else observed=REFUSED; grep -vE "^(Reading|Building|Get:|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing)" /tmp/gate/cmd.log | tail -n 30 >> "$T"; fi
    echo "exit: $rc — observed: $observed" >> "$T"
    echo "VERDICT $id expected=$expected observed=$observed" >> "$T"
}

state() { # label -- command...
    label=$1; shift 2
    { echo "--- $label"; echo "\$ $*"; "$@" 2>&1; echo; } >> "$T"
}

versions() {
    dpkg-query -W -f='${Package} ${Version} ${db:Status-Abbrev}\n' \
        cuems-common cuems-utils cuems-nodeconf 2>&1 || true
}

# --- N1: this package's own reverse guard, Breaks: cuems-common (<< 1.3.0-23~).
# The library stub is put in place first so the only thing left to judge is the
# relationship between the two real packages.
$APT --allow-downgrades install $G/cuems-utils_0.1.0rc16.deb > /dev/null 2>&1
attempt N1 REFUSED "cuems-nodeconf 0.1.0-8 together with cuems-common 1.3.0-22 (un-renamed) — this package's Breaks" -- \
    $APT install $G/cuems-nodeconf_new.deb $G/cuems-common_old.deb
state "nothing installed after N1" -- versions

# --- N2: the forward edge, cuems-common's Breaks: cuems-nodeconf (<< 0.1.0-8).
attempt N2 REFUSED "cuems-common 1.3.0-23 together with cuems-nodeconf 0.1.0-7 (un-renamed) — the counterpart's Breaks" -- \
    $APT install $G/cuems-common_new.deb $G/cuems-nodeconf_old.deb
state "still nothing installed" -- versions

# --- N3: this package's library bound, both ends. cuems-common 1.3.0-23 is
# offered alongside so that nodeconf's cuems-common dependency and its Breaks are
# both satisfied, leaving the cuems-utils bound as the only thing that can refuse.
# NOTE: cuems-common carries the same << 0.1.1~ ceiling, so for N3b either
# package's relationship may be the one apt names; the transcript shows which.
attempt N3a REFUSED "cuems-nodeconf 0.1.0-8 beside cuems-utils 0.1.0rc15 (below the floor)" -- \
    $APT --allow-downgrades install $G/cuems-nodeconf_new.deb $G/cuems-common_new.deb $G/cuems-utils_0.1.0rc15.deb
attempt N3b REFUSED "cuems-nodeconf 0.1.0-8 beside cuems-utils 0.1.1~rc1 (past the ceiling)" -- \
    $APT --allow-downgrades install $G/cuems-nodeconf_new.deb $G/cuems-common_new.deb "$G/cuems-utils_0.1.1~rc1.deb"
state "still nothing installed" -- versions

# --- N4: the baseline field host — everything at the pre-cutover release.
attempt N4 ACCEPTED "baseline field host: cuems-utils 0.1.0rc16 + cuems-common 1.3.0-22 + cuems-nodeconf 0.1.0-7" -- \
    $APT --allow-downgrades install $G/cuems-utils_0.1.0rc16.deb $G/cuems-common_old.deb $G/cuems-nodeconf_old.deb
state "baseline installed" -- versions

# --- N5 / N6: upgrading one half of the cutover on that host.
attempt N5 REFUSED "on the baseline host, upgrade ONLY cuems-nodeconf to 0.1.0-8" -- \
    $APT install $G/cuems-nodeconf_new.deb
attempt N6 REFUSED "on the baseline host, upgrade ONLY cuems-common to 1.3.0-23" -- \
    $APT install $G/cuems-common_new.deb
state "baseline unchanged by either half-upgrade" -- versions

# --- N7: both halves together, in one call — the cluster upgrades as a unit.
attempt N7 ACCEPTED "on the baseline host, upgrade BOTH together in one apt-get call" -- \
    $APT install $G/cuems-common_new.deb $G/cuems-nodeconf_new.deb
state "after the coordinated upgrade" -- versions
state "the daemon's entry point is installed" -- ls -l /usr/lib/cuems/bin/cuems-nodeconf
state "the renamed discovery templates are in place" -- sh -c 'ls -1 /usr/share/cuems/cuems.service.*'

# --- N8: quickstart §4's own form — dpkg rather than apt, on the upgraded host.
# dpkg, unlike apt, unpacks first and resolves after, so the expectation here is
# BREAKS-UNCONFIGURED: dpkg names cuems-common's Breaks and leaves the downgrade
# unconfigured with a non-zero exit. Expecting REFUSED was wrong about dpkg's
# order of operations, not about the gate; observed 2026-09-17 and corrected.
attempt N8 BREAKS-UNCONFIGURED "on the upgraded host, dpkg -i of cuems-nodeconf 0.1.0-7 (quickstart.md §4)" -- \
    dpkg -i $G/cuems-nodeconf_old.deb
state "final versions" -- versions
exit 0
SCENARIOS

log "running scenarios in an unprivileged mmdebstrap system (downloads from $MIRROR)"
mmdebstrap --mode=unshare --variant=apt --include=ca-certificates \
    --customize-hook='mkdir -p "$1/tmp/gate"' \
    --customize-hook="copy-in $WORK/debs /tmp/gate" \
    --customize-hook='chroot "$1" sh /tmp/gate/debs/scenarios.sh' \
    --customize-hook="copy-out /tmp/gate/transcript.txt $WORK" \
    bookworm /dev/null "$MIRROR" > "$WORK/mmdebstrap.log" 2>&1 \
    || { log "mmdebstrap failed — see $WORK/mmdebstrap.log"; exit 1; }

# --- 6. evidence -------------------------------------------------------------
mkdir -p "$(dirname "$OUT")"
{
    echo "# Release-gate demonstration — observed, not asserted (feature 001, T047 / SC-007)"
    echo "#"
    echo "# Generated by tests/packaging/release-gate-demo.sh. Do not edit by hand; re-run it."
    echo "#"
    echo "# date:                 $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# cuems-nodeconf:       $NEW_VERSION, REAL package built from this repository's working tree"
    echo "#                       at $(git -C "$REPO" rev-parse HEAD)$(git -C "$REPO" diff --quiet HEAD -- . ':!specs/001-network-map-object-adoption/evidence' || echo ' (+ uncommitted changes)')"
    echo "# cuems-nodeconf (old): $OLD_VERSION, $OLD_KIND"
    echo "#                       $OLD_REF = $(git -C "$REPO" rev-parse "$OLD_REF")"
    echo "# cuems-common (new):   $COMMON_NEW_VERSION, REAL package built from $COMMON_NEW = $COMMON_NEW_COMMIT"
    echo "# cuems-common (old):   $COMMON_OLD_VERSION, REAL package built from $COMMON_OLD = $COMMON_OLD_COMMIT"
    echo "# cuems-utils:          STUBS at ${UTILS_VERSIONS[*]} (equivs; no .deb of the library exists at these versions)"
    echo "# cuemsutils for pip:   $WHEEL, built from $UTILS_REL @ $UTILS_COMMIT$UTILS_DIRTY with $WHEEL_TOOL,"
    echo "#                       offered to dh_virtualenv's pip as PIP_FIND_LINKS for the build only."
    echo "#                       $DHV_VERSION runs pip via subprocess.check_call with no env= override"
    echo "#                       (deployment.py:182,196), so PIP_* is inherited; debian/rules is unchanged."
    echo "# build environment:    $(mmdebstrap --version), --mode=unshare --variant=apt, bookworm, $MIRROR"
    echo "#"
    echo "# WHAT SHIPS — dpkg-deb -c on the built $NEW_VERSION package:"
    echo "#   cuemsnodeconf in site-packages:      $HAS_PKG (expected >= 1)"
    echo "#   cuems-nodeconf entry point:          $HAS_ENTRY (expected 1)"
    echo "#   staged dependencies (incl. the local cuemsutils wheel): $LEAKED (expected 0)"
    echo "#   anything from tests/ or specs/:      $SHIPPED_TESTS (expected 0)"
    echo "#   => the wheel is a BUILD input only; it does not reach the package."
    echo "#"
    echo "# The library counterpart is an equivs stub: it carries a version and the one"
    echo "# path the maintainer scripts need, nothing else. Every REFUSED outcome below is"
    echo "# apt or dpkg refusing a REAL package. apt runs with --no-remove, so a"
    echo "# relationship it could only satisfy by removing an installed package is reported"
    echo "# as a refusal instead of silently removing it."
    cat "$WORK/transcript.txt"
    echo
    echo "=== SUMMARY"
    grep '^VERDICT' "$WORK/transcript.txt" | while read -r _ id exp obs; do
        e=${exp#expected=}; o=${obs#observed=}
        [ "$e" = "$o" ] && m=match || m=MISMATCH
        printf '%-4s expected %-8s observed %-8s %s\n' "$id" "$e" "$o" "$m"
    done
} > "$OUT"
log "evidence written: $OUT"

MISMATCHES="$(grep '^VERDICT' "$WORK/transcript.txt" \
    | awk '{split($3,e,"="); split($4,o,"="); if (e[2]!=o[2]) print $2}')"
if [ -z "$MISMATCHES" ]; then
    log "all scenarios matched their expectations"
else
    log "these scenarios did NOT match: $MISMATCHES — see $OUT"
    exit 1
fi
