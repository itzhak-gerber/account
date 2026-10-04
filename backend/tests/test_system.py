from tests.helpers import app_client


async def test_health_reports_database_ok() -> None:
    async with app_client() as client:
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["database"] == "ok"


async def test_security_headers_present() -> None:
    async with app_client() as client:
        response = await client.get("/api/v1/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


async def test_strict_csp_on_api_but_not_on_docs() -> None:
    async with app_client() as client:
        api = await client.get("/api/v1/health")
        docs = await client.get("/api/docs")

        assert api.headers["Content-Security-Policy"].startswith("default-src 'none'")
        assert docs.status_code == 200
        assert "Content-Security-Policy" not in docs.headers
