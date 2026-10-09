"""Utilites to call the hardware discovery tool."""
from cuemsutils.log import logged, Logger
from cuemsutils.tools.CommunicatorServices import Communicator
import threading
import asyncio
import json
import os

NODECONF_IPC = '/tmp/nodeconf.ipc'
TIMEOUT = 15  # seconds




@logged
def get_nodeconf_comm():
    """
    Call the node configuration tool
    """
    return Communicator(NODECONF_IPC)



    

class AsyncCommsThread(threading.Thread):
    def __init__(self, command_callback: callable):
        Logger.debug('Initializing communications thread')
        self.command_callback = command_callback
        self.timeout = TIMEOUT * 1000
        self.stop_requested = False
        self.send_contexts= []
        self._engine_task = None
        threading.Thread.__init__(self, name='Communications', daemon=True)
        self.nodeconf = get_nodeconf_comm()
        
        
 

    def run(self):
        Logger.debug('Comms thread run called')
        self.event_loop = asyncio.new_event_loop()
        self.event_loop.create_task(self.run_asyncio_comms())
        self.event_loop.run_forever()
        # Loop stopped (stop_async ran): close it so any remaining transports /
        # nng aios are finalized here in the comms thread rather than at
        # interpreter exit, where pynng's nni_aio_fini panics (pthread_mutex)
        # and the process core-dumps on every stop/restart.
        try:
            self.event_loop.close()
        except Exception:
            pass
    def stop(self):
        self.stop_requested = True
        asyncio.run_coroutine_threadsafe(self.stop_async(), self.event_loop)
    
    async def stop_async(self):
        # Cancel the engine listener (blocked on an nng aio) and let the
        # cancellation unwind INSIDE the loop so pynng frees the aio cleanly.
        # Stopping the loop with the task still pending leaks the aio to
        # interpreter exit, where nni_aio_fini panics and the process
        # core-dumps. Bounded wait so a non-cancellable op cannot hang stop().
        task = getattr(self, '_engine_task', None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait({task}, timeout=2)
            except Exception:
                pass
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        Logger.info('event loop stoped')
                

    async def run_asyncio_comms(self):
        Logger.info('Starting asyncio communications')
        self._engine_task = asyncio.create_task(self.engine_listener())
        try:
            await self._engine_task
        except asyncio.CancelledError:
            Logger.debug('engine listener cancelled')

        Logger.debug('asyncio comms finished')
        #
    async def engine_listener(self):
        Logger.info('engine listener started')
        await self.nodeconf.responder_connect()
        # nodeconf runs as root, so the IPC socket it just bound is root-owned.
        # The engine (unprivileged cuems user) hard-fails its Communicator R/W
        # access check when the socket exists but is inaccessible, and at boot
        # nodeconf wins the race to create it first -> cuems-controller-engine
        # crash-loops ("Path /tmp/nodeconf.ipc is not readable or writable").
        # Make the responder socket reachable by any local CUEMS process.
        for _ in range(20):
            if os.path.exists(NODECONF_IPC):
                try:
                    os.chmod(NODECONF_IPC, 0o666)
                    Logger.debug(f'Set {NODECONF_IPC} mode 0666 for cross-user access')
                except OSError as e:
                    Logger.warning(f'Could not chmod {NODECONF_IPC}: {e}')
                break
            await asyncio.sleep(0.05)
        else:
            Logger.warning(f'{NODECONF_IPC} did not appear after responder_connect')
        while not self.stop_requested:
            Logger.debug(f'waiting for engine message')
            await self.nodeconf.responder_get_request(self.command_callback)

    async def respond_to_engine(self, message, context):
        Logger.debug(f'Sending to editengine: {message}, with context ')
        await context.asend(json.dumps(message).encode())           

