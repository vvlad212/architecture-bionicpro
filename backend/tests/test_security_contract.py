import inspect
import json
import unittest
from pathlib import Path

from backend.app.main import reports


class SecurityContractTest(unittest.TestCase):
    def test_reports_endpoint_has_no_customer_id_parameter(self) -> None:
        self.assertNotIn("customer_id", inspect.signature(reports).parameters)

    def test_keycloak_client_enforces_pkce_and_disables_password_grant(self) -> None:
        realm = json.loads(Path("keycloak/realm-export.json").read_text())
        client = next(
            item for item in realm["clients"] if item["clientId"] == "reports-bff"
        )

        self.assertFalse(client["publicClient"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertTrue(realm["revokeRefreshToken"])
        self.assertEqual(realm["refreshTokenMaxReuse"], 0)


if __name__ == "__main__":
    unittest.main()
