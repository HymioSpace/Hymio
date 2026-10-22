import unittest

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from hymio_backend.observability import REGISTRY, HTTPMetricsMiddleware, http_route


class HttpMetricsTests(unittest.TestCase):
    def test_route_template_is_used_instead_of_raw_identifier(self):
        app = Starlette(
            routes=[
                Route(
                    "/items/{item_id}",
                    lambda request: JSONResponse({"id": request.path_params["item_id"]}),
                )
            ]
        )
        app.add_middleware(HTTPMetricsMiddleware)
        client = TestClient(app)
        self.addCleanup(client.close)

        response = client.get("/items/synthetic-item")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            REGISTRY.get_sample_value(
                "hymio_http_requests_total",
                {"method": "GET", "route": "/items/{item_id}", "status": "200"},
            ),
            1,
        )
        self.assertIsNotNone(
            REGISTRY.get_sample_value(
                "hymio_http_request_duration_seconds_count",
                {"method": "GET", "route": "/items/{item_id}"},
            )
        )

    def test_known_dynamic_attachment_path_falls_back_to_bounded_label(self):
        self.assertEqual(
            http_route({"path": "/attachments/" + "a" * 32}),
            "/attachments/{attachment_id}",
        )


if __name__ == "__main__":
    unittest.main()
