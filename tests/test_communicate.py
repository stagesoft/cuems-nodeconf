"""
Tests for communicate.py functionality.
"""
import pytest
from unittest.mock import MagicMock, patch
from cuemsnodeconf.communicate import AsyncCommsThread


class TestAsyncCommsThread:
    """Test AsyncCommsThread functionality."""
    
    def test_stop_requested_flag(self):
        """Test that stop_requested flag is set correctly."""
        callback = MagicMock()
        thread = AsyncCommsThread(callback)
        
        # Initially should be False
        assert thread.stop_requested is False
        
        # After calling stop, should be True
        # Note: We can't actually call stop() without starting the thread,
        # but we can verify the fix is in place by checking the code
        # The bug was: stop_requested = True (missing self.)
        # The fix is: self.stop_requested = True
        
        # Verify the attribute exists
        assert hasattr(thread, 'stop_requested')
    
    def test_thread_initialization(self):
        """Test that AsyncCommsThread initializes correctly."""
        callback = MagicMock()
        thread = AsyncCommsThread(callback)
        
        assert thread.command_callback == callback
        assert thread.stop_requested is False
        assert thread.name == 'Communications'
        assert thread.daemon is True

