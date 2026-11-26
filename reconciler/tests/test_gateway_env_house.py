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
        self.assertNotIn("HA_1_URL", names)               # the address is GATEWAY_HA_URL, passed by compose

    def test_nothing_extra_when_the_house_tools_are_off(self):
        self.assertEqual(self.names({"house": {}}), ["GATEWAY_HA_TOKEN"])


class MailCredentialTests(unittest.TestCase):
    names = HouseCredentialTests.names                  # the same helper, without running its tests twice

    CFG = {"mail": {"instance": 1, "url": "https://m.example", "people": ["tmeuze", "u-shy"]}}

    def test_the_gateway_is_given_each_listed_persons_token(self):
        names = self.names(self.CFG)
        self.assertIn("MAILFLOW_1_TMEUZE_API_TOKEN", names)
        self.assertIn("MAILFLOW_1_U_SHY_API_TOKEN", names)

    def test_novak_secret_learns_the_same_names_and_says_whose_they_are(self):
        import instances
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        (d / "gateway.yaml").write_text(yaml.safe_dump({"gateway": self.CFG}))
        (d / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": []}))
        names = instances.secret_vars(d / "mcp-servers.yaml")
        self.assertIn("MAILFLOW_1_TMEUZE_API_TOKEN", names)
        self.assertIn("tmeuze's read-only MailFlow token", instances.describe("MAILFLOW_1_TMEUZE_API_TOKEN", d / "mcp-servers.yaml"))


if __name__ == "__main__":
    unittest.main()
