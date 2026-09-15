import os
import tempfile
import unittest
from pathlib import Path

import extractor


class TestGeminiEnvLoading(unittest.TestCase):
    def test_get_api_key_strips_trailing_noise_and_uses_project_dotenv(self):
        project_root = Path(__file__).resolve().parent.parent
        env_path = project_root / ".env"
        raw_value = env_path.read_text(encoding="utf-8").strip()

        key = extractor.get_api_key()

        self.assertTrue(key)
        self.assertNotIn("`", key)
        self.assertEqual(key, raw_value.split("=", 1)[1].strip().strip("`"))

    def test_model_name_uses_supported_latest_flash(self):
        self.assertEqual(extractor.MODEL_NAME, "gemini-3.6-flash")


if __name__ == "__main__":
    unittest.main()
