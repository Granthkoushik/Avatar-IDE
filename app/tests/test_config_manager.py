# app/tests/test_config_manager.py
import unittest
from app.services.config_manager import get_config, get_setting

class TestConfigManager(unittest.TestCase):
    def test_get_config(self):
        cfg = get_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("system", cfg)
        self.assertIn("ai_models", cfg)

    def test_get_setting(self):
        proj_name = get_setting("system.project_name")
        self.assertEqual(proj_name, "AVATAR")
        
        # Test default fallback
        fallback = get_setting("system.non_existent_key", "default_val")
        self.assertEqual(fallback, "default_val")
