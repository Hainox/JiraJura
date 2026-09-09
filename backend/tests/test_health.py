from httpx import AsyncClient


async def test_public_health_endpoint_returns_service_status(client: AsyncClient):
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
