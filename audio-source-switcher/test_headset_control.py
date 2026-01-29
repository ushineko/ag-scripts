
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Adjust path to import the module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from audio_source_switcher import HeadsetController

class TestHeadsetController(unittest.TestCase):
    @patch('subprocess.run')
    def test_set_inactive_time(self, mock_run):
        hc = HeadsetController()
        
        # Test 10 minutes
        hc.set_inactive_time(10)
        mock_run.assert_called_with(
            ['headsetcontrol', '-i', '10'],
            capture_output=True, text=True, check=True
        )
        
        # Test 0 minutes (disable)
        hc.set_inactive_time(0)
        mock_run.assert_called_with(
            ['headsetcontrol', '-i', '0'],
            capture_output=True, text=True, check=True
        )

if __name__ == '__main__':
    unittest.main()
