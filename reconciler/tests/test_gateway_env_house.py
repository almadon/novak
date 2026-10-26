import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "reconciler"))
import gateway_env  # noqa: E402


class HouseCredentialTests(unittest.TestCase):
    def names(self, gateway):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        (d / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": []}))
        (d / "people.yaml").write_text(yaml.safe_dump({"people": {}, "household": {"entries": []}}))
        (d / "gateway.yaml").write_text(yaml.safe_dump({"gateway": gateway}))
        return gateway_env.needed_names(d)

    def test_the_gateway_is_given_the_house_instance_credentials(self):
        names = self.names({"house": {"ha": 1, "people": ["tmeuze"]}})
        self.assertIn("HA_1_ADMIN_API_TOKEN", names)
        self.assertIn("HA_1_URL", names)

    def test_nothing_extra_when_the_house_tools_are_off(self):
        self.assertEqual(self.names({"house": {}}), ["GATEWAY_HA_TOKEN"])


if __name__ == "__main__":
    unittest.main()
