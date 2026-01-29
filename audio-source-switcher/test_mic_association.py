import unittest
from audio_source_switcher import AudioController

class TestMicAssociation(unittest.TestCase):
    def setUp(self):
        # We only need the AudioController for its static-like logic methods
        # Mocking run_command isn't needed if we test finding logic with pre-supplied lists
        self.controller = AudioController()

    def test_find_by_serial(self):
        sink_props = {
            'device.serial': 'HEADSET_123',
            'alsa.card': '0'
        }
        
        sources = [
            {'name': 'src1', 'properties': {'device.serial': 'OTHER_999'}},
            {'name': 'src2', 'properties': {'device.serial': 'HEADSET_123'}}, # Match
            {'name': 'src3', 'properties': {'alsa.card': '0'}} # Weaker match
        ]
        
        match = self.controller.find_associated_source(sink_props, sources)
        self.assertIsNotNone(match)
        self.assertEqual(match['name'], 'src2')

    def test_find_by_card(self):
        sink_props = {
            'alsa.card': '5'
        }
        
        sources = [
            {'name': 'src1', 'properties': {'alsa.card': '1'}},
            {'name': 'src2', 'properties': {'alsa.card': '5'}} # Match
        ]
        
        match = self.controller.find_associated_source(sink_props, sources)
        self.assertIsNotNone(match)
        self.assertEqual(match['name'], 'src2')

    def test_find_by_bluetooth(self):
        sink_props = {
            'api.bluez5.address': 'XX:XX:XX:XX:XX:XX',
            'device.name': 'bluez_card.XX_XX'
        }
        
        sources = [
            {'name': 'src1', 'properties': {'api.bluez5.address': 'YY:YY:YY:YY:YY:YY'}},
            {'name': 'src2', 'properties': {'api.bluez5.address': 'XX:XX:XX:XX:XX:XX'}} # Match
        ]
        
        match = self.controller.find_associated_source(sink_props, sources)
        self.assertIsNotNone(match)
        self.assertEqual(match['name'], 'src2')

    def test_find_by_device_name(self):
        sink_props = {'device.name': 'common_card_name', 'device.serial': 'SINK_SERIAL'}
        sources = [{'name': 'src1', 'properties': {'device.name': 'common_card_name', 'device.serial': 'SOURCE_SERIAL'}}]
        
        match = self.controller.find_associated_source(sink_props, sources)
        self.assertIsNotNone(match)
        self.assertEqual(match['name'], 'src1')

    def test_no_match(self):
        sink_props = {'device.serial': 'A', 'alsa.card': '1'}
        sources = [{'name': 'src1', 'properties': {'device.serial': 'B', 'alsa.card': '2'}}]
        
        match = self.controller.find_associated_source(sink_props, sources)
        self.assertIsNone(match)

    def test_get_sources_fix_null_name(self):
        # Mock run_command to return specific JSON
        import json
        
        # JSON snippet from the issue (simplified)
        mock_json = json.dumps([
            {
                "name": "bluez_input.30:7A:D2:30:CB:AD",
                "description": "(null)",
                "properties": {
                    "device.description": "(null)",
                    "device.api": "bluez",
                    "api.bluez5.address": "30:7A:D2:30:CB:AD" 
                }
            }
        ])
        
        # Override run_command for this instance
        original_run_command = self.controller.run_command
        self.controller.run_command = lambda cmd: mock_json if 'sources' in cmd else ""
        
        try:
            # 1. Without cache -> Should fallback to name (bluez_input...)
            sources = self.controller.get_sources()
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]['display_name'], "bluez_input.30:7A:D2:30:CB:AD")
            
            # 2. With cache -> Should resolve to friendly name
            bt_cache = {"30:7A:D2:30:CB:AD": "Papa's AirPods Pro"}
            sources = self.controller.get_sources(bt_cache=bt_cache)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]['display_name'], "Papa's AirPods Pro")
            
        finally:
             self.controller.run_command = original_run_command

if __name__ == '__main__':
    unittest.main()
