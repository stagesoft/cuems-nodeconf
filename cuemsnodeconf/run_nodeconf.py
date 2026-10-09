#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Entry point for the cuems-nodeconf daemon.

Runs under systemd as Type=notify, NotifyAccess=main: CuemsNodeConf.run() calls
systemd.daemon.notify('READY=1') once the initial discovery pass completes, then
stays resident. We install SIGTERM/SIGINT handlers that call stop() for a clean
teardown (cancel the avahi browser, close zeroconf, stop the comms thread, free
the published aliases).

The previous implementation used cuemsutils.daemon.run_daemon (python-daemon
DaemonContext), which was removed from cuems-utils: its double-fork drops the
NOTIFY_SOCKET fd, so sd_notify() silently failed and the Type=notify unit timed
out waiting for READY.
"""

import signal

from cuemsutils.log import Logger
from .CuemsNodeConf import CuemsNodeConf


def main():
    nodeconf = CuemsNodeConf()

    def _handle_signal(signum, frame):
        Logger.info(f'Signal {signum} received; shutting down cuems-nodeconf')
        nodeconf.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    Logger.debug('CuemsNodeConf instance created; starting daemon')
    try:
        nodeconf.start()
    except SystemExit:
        raise
    except Exception as e:
        Logger.error(f'Fatal error in cuems-nodeconf: {type(e).__name__}: {e}')
        Logger.exception(e)
        raise


if __name__ == '__main__':
    main()
