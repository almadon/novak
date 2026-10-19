import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]


class RouterKeyTests(unittest.TestCase):
    def test_router_gets_its_master_key_from_router_api_key(self):
        env = COMPOSE["router"]["environment"]
        self.assertIn("LITELLM_MASTER_KEY=${ROUTER_API_KEY}", env)

    def test_every_router_client_presents_the_router_key(self):
        self.assertIn("ROUTER_API_KEY", COMPOSE["open-webui"]["environment"]["OPENAI_API_KEY"])
        self.assertIn("ROUTER_API_KEY", COMPOSE["hindsight"]["environment"]["HINDSIGHT_API_LLM_API_KEY"])
        self.assertIn("ROUTER_API_KEY", COMPOSE["ingest"]["environment"]["INGEST_LLM_API_KEY"])

    def test_the_router_profile_is_gated_on_the_key(self):
        vars_sh = (REPO / "scripts" / "lib" / "vars.sh").read_text()
        self.assertIn("ROUTER_SECRETS=(ROUTER_API_KEY)", vars_sh)
        self.assertIn("ROUTER_API_KEY=set-in-keychain", (REPO / ".env.example").read_text())

    def test_the_key_is_a_shared_secret_so_it_can_be_generated_and_shown(self):
        import subprocess
        out = subprocess.run(["bash", "-c", f"source {REPO}/scripts/lib/vars.sh; "
                              'for v in "${SECRET_VARS[@]}"; do echo "S:$v"; done; '
                              'for v in "${SHARED_SECRETS[@]}"; do echo "H:$v"; done; '
                              'for v in "${EXTERNAL_SECRETS[@]}"; do echo "E:$v"; done'],
                             capture_output=True, text=True).stdout.split()
        self.assertIn("S:ROUTER_API_KEY", out)
        self.assertIn("H:ROUTER_API_KEY", out)
        self.assertNotIn("E:ROUTER_API_KEY", out)       # ours to generate, not owned by another system


if __name__ == "__main__":
    unittest.main()
