from typing import Any

from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import VALID_BUSINESS, Browser, app_client, browser_login
from tests.test_members import invite_and_join


async def owner_with_business(client: Any, idp: FakeIdP) -> tuple[Browser, str]:
    owner = await browser_login(client, idp, FakeUser(email="owner@example.com"), mfa=True)
    business = await owner.post("/api/v1/businesses", json=VALID_BUSINESS)
    return owner, business.json()["business"]["id"]


async def test_customers_crud_and_search(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await owner_with_business(client, idp)
        base = f"/api/v1/businesses/{bid}/customers"

        created = await owner.post(
            base, json={"name": "לקוח ראשון בע״מ", "tax_id": "123456782", "email": "a@x.co"}
        )
        await owner.post(base, json={"name": "Second Ltd", "phone": "050-1234567"})
        found = await owner.get(base, params={"q": "ראשון"})
        by_phone = await owner.get(base, params={"q": "050"})
        assert created.status_code == 201, created.text
        cid = created.json()["id"]
        archived = await owner.patch(f"{base}/{cid}", json={"is_archived": True})
        after = await owner.get(base)

        assert created.status_code == 201, created.text
        assert [c["name"] for c in found.json()] == ["לקוח ראשון בע״מ"]
        assert [c["name"] for c in by_phone.json()] == ["Second Ltd"]
        assert archived.json()["is_archived"] is True
        assert [c["name"] for c in after.json()] == ["Second Ltd"]


async def test_customer_tax_id_is_validated(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await owner_with_business(client, idp)

        bad = await owner.post(
            f"/api/v1/businesses/{bid}/customers", json={"name": "X", "tax_id": "123456789"}
        )

        assert bad.status_code == 422


async def test_items_crud(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await owner_with_business(client, idp)
        base = f"/api/v1/businesses/{bid}/items"

        created = await owner.post(
            base,
            json={"name": "ייעוץ", "unit_price": "350.00", "unit_of_measure": "שעה", "sku": "C-1"},
        )
        iid = created.json()["id"]
        updated = await owner.patch(f"{base}/{iid}", json={"unit_price": "400"})
        found = await owner.get(base, params={"q": "C-1"})

        assert created.json()["vat_type"] == "standard"
        assert created.json()["item_type"] == "service"
        assert updated.json()["unit_price"] == "400.00"
        assert [i["id"] for i in found.json()] == [iid]


async def test_catalog_permissions_and_isolation(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, bid = await owner_with_business(client, idp)
        await owner.post(f"/api/v1/businesses/{bid}/customers", json={"name": "לקוח"})
        viewer = await invite_and_join(
            client, idp, owner, bid, sent_jobs, FakeUser(email="v@example.com"), "viewer"
        )
        base = f"/api/v1/businesses/{bid}/customers"

        assert len((await viewer.get(base)).json()) == 1
        assert (await viewer.post(base, json={"name": "חדש"})).status_code == 403

        other = await browser_login(client, idp, FakeUser(email="o@example.com"), mfa=True)
        assert (await other.get(base)).status_code == 404
