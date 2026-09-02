import ast
import json
import unittest
from pathlib import Path


SPEC_PATH = Path(__file__).parents[1] / "infra" / "environments" / "demo" / "app" / "openapi.json"
HANDLER_PATH = SPEC_PATH.with_name("handler.py")


def runtime_constant(name):
    tree = ast.parse(HANDLER_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Runtime constant not found: {name}")


class OpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SPEC_PATH.read_text(encoding="utf-8")
        cls.spec = json.loads(cls.raw)

    def test_contract_uses_openapi_31_and_has_unique_operation_pairs(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        operations = [(method.upper(), path) for path, item in self.spec["paths"].items() for method in item if method in {"get", "post", "patch", "put", "delete"}]
        self.assertEqual(len(operations), len(set(operations)))

    def test_contract_covers_every_lambda_route(self):
        expected = {
            ("GET", "/"), ("GET", "/health"), ("GET", "/openapi.json"), ("POST", "/bookings"),
            ("GET", "/bookings/{booking_id}"), ("PATCH", "/bookings/{booking_id}"), ("GET", "/bookings/{booking_id}/quote"), ("PATCH", "/bookings/{booking_id}/quote"), ("GET", "/bookings/{booking_id}/payment"),
            ("GET", "/admin"), ("GET", "/admin/session"), ("GET", "/admin/summary"), ("GET", "/admin/bookings"), ("PATCH", "/admin/bookings/{booking_id}"),
            ("PATCH", "/admin/bookings/{booking_id}/assignment"), ("GET", "/admin/bookings/{booking_id}/quotes"), ("POST", "/admin/bookings/{booking_id}/quotes"),
            ("GET", "/admin/bookings/{booking_id}/payments"), ("POST", "/admin/bookings/{booking_id}/payments"),
            ("GET", "/admin/vehicles"), ("POST", "/admin/vehicles"), ("PATCH", "/admin/vehicles/{vehicle_id}"),
            ("GET", "/admin/chauffeurs"), ("POST", "/admin/chauffeurs"), ("PATCH", "/admin/chauffeurs/{chauffeur_id}"),
            ("GET", "/admin/notifications"), ("PATCH", "/admin/notifications/{notification_id}"), ("POST", "/webhooks/payments"),
        }
        documented = {(method.upper(), path) for path, item in self.spec["paths"].items() for method in item if method in {"get", "post", "patch", "put", "delete"}}
        self.assertEqual(documented, expected)

    def test_sensitive_routes_declare_the_correct_header_schemes(self):
        schemes = self.spec["components"]["securitySchemes"]
        self.assertEqual(schemes["bookingToken"]["name"], "x-booking-token")
        self.assertEqual(schemes["staffPassword"]["name"], "x-staff-password")
        self.assertEqual(schemes["webhookSignature"]["name"], "x-webhook-signature")
        self.assertEqual(self.spec["paths"]["/bookings/{booking_id}"]["get"]["security"], [{"bookingToken": []}])
        self.assertEqual(self.spec["paths"]["/bookings/{booking_id}"]["patch"]["security"], [{"bookingToken": []}])
        self.assertEqual(self.spec["paths"]["/bookings/{booking_id}/quote"]["patch"]["security"], [{"bookingToken": []}])
        self.assertEqual(self.spec["paths"]["/admin/bookings"]["get"]["security"], [{"staffPassword": []}])
        self.assertEqual(self.spec["paths"]["/admin/summary"]["get"]["security"], [{"staffPassword": []}])
        self.assertEqual(self.spec["paths"]["/webhooks/payments"]["post"]["security"], [{"webhookSignature": []}])

    def test_contract_contains_no_example_credentials(self):
        for forbidden in ("demo-admin", "demo-operator", "PAYMENT_WEBHOOK_SECRET", "AWS_RELEASE_ROLE_ARN"):
            self.assertNotIn(forbidden, self.raw)

    def test_booking_location_enums_match_runtime_validation(self):
        booking = self.spec["components"]["schemas"]["BookingRequest"]
        properties = booking["properties"]

        self.assertEqual(set(properties["hub"]["enum"]), runtime_constant("HUBS"))
        self.assertEqual(
            set(properties["trip_type"]["enum"]), runtime_constant("TRIP_TYPES")
        )
        self.assertEqual(
            set(properties["destination_state"]["enum"]),
            runtime_constant("NIGERIAN_STATES"),
        )
        self.assertIn("destination_state", booking["allOf"][0]["then"]["required"])

    def test_fleet_and_assignment_writes_have_request_contracts(self):
        expected = {
            ("/admin/vehicles", "post"): ("VehicleCreate", {"name", "hub"}),
            ("/admin/chauffeurs", "post"): ("ChauffeurCreate", {"name", "hub"}),
            ("/admin/bookings/{booking_id}/assignment", "patch"): (
                "AssignmentRequest", {"vehicle_id", "chauffeur_id"}
            ),
        }

        for (path, method), (schema_name, required) in expected.items():
            with self.subTest(path=path, method=method):
                operation = self.spec["paths"][path][method]
                schema = operation["requestBody"]["content"]["application/json"]["schema"]
                self.assertEqual(schema["$ref"], f"#/components/schemas/{schema_name}")
                self.assertEqual(
                    set(self.spec["components"]["schemas"][schema_name]["required"]),
                    required,
                )

        chauffeur = self.spec["components"]["schemas"]["ChauffeurCreate"]
        self.assertEqual(
            set(chauffeur["properties"]["interstate_eligible"]["enum"]),
            {"YES", "NO"},
        )
        self.assertEqual(
            chauffeur["properties"]["interstate_eligible"]["default"], "NO"
        )

    def test_quote_write_contract_documents_internal_cost_as_optional(self):
        operation = self.spec["paths"]["/admin/bookings/{booking_id}/quotes"]["post"]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(schema["$ref"], "#/components/schemas/QuoteCreate")
        quote = self.spec["components"]["schemas"]["QuoteCreate"]
        self.assertEqual(set(quote["required"]), {"amount_ngn", "valid_until"})
        self.assertNotIn("estimated_cost_ngn", quote["required"])
        self.assertEqual(quote["properties"]["estimated_cost_ngn"]["minimum"], 0)


if __name__ == "__main__":
    unittest.main()
