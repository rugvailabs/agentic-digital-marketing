"""The brand endpoints, against a real Postgres schema.

Real, because half of what is worth pinning is in the database: the unique
constraint that turns a duplicate slug into a 409, the cascade that takes a
brand's jobs with it, and the JSONB columns that have to come back as lists
rather than nulls.

Storage is the one thing stubbed. `put_bytes` is boto3 against MinIO, and a
test that needs a bucket to prove a digest is in a key is testing MinIO.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import brands as brands_api
from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models import (
    Brand,
    ContentJob,
    JobKind,
    Language,
    Region,
    RegionKind,
    Trend,
    Workspace,
)

TEST_DB = "trendforge_brands_test"

PNG = b"\x89PNG\r\n\x1a\n" + b"fake" * 8


@pytest.fixture(scope="module")
async def engine() -> AsyncIterator[object]:
    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
            await conn.exec_driver_sql(f'CREATE DATABASE "{TEST_DB}"')
    except Exception as exc:  # pragma: no cover - CI without a database
        pytest.skip(f"no database available: {type(exc).__name__}")
    finally:
        await admin.dispose()

    base, _, _ = settings.database_url.rpartition("/")
    test_engine = create_async_engine(f"{base}/{TEST_DB}")
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()

    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    await admin.dispose()


@pytest.fixture
async def factory(engine) -> AsyncIterator[async_sessionmaker]:
    """An empty workspace and one topic, with the session dependency bound."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()
    async with session_factory() as session:
        for table in (ContentJob, Brand, Trend, Region, Workspace):
            await session.execute(table.__table__.delete())

        session.add(Workspace(id=Workspace.DEFAULT_ID, slug="default", name="Default workspace"))
        region = Region(code="IN", name="India", kind=RegionKind.country, sort_order=0)
        session.add(region)
        await session.flush()
        session.add(
            Trend(
                region_id=region.id,
                topic="India win the series",
                topic_key="india win series",
                rank=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await session.commit()

    async def override() -> AsyncIterator[object]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield session_factory
    app.dependency_overrides.clear()


@pytest.fixture
async def client(factory) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def make(client: httpx.AsyncClient, **kw) -> dict:
    kw.setdefault("name", "Madras Filter Coffee")
    response = await client.post("/brands", json=kw)
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    async def test_a_name_is_enough(self, client: httpx.AsyncClient) -> None:
        """Everything else has a default, so a team can make a brand and
        generate something before deciding what it sounds like."""
        brand = await make(client)

        assert brand["slug"] == "madras-filter-coffee"
        assert brand["languages"] == ["english"]
        assert brand["font_choice"] == "display"
        assert brand["products"] == []
        assert brand["logo_url"] is None

    async def test_the_whole_profile_round_trips(self, client: httpx.AsyncClient) -> None:
        brand = await make(
            client,
            voice_prompt="Warm, specific, a little dry.",
            languages=["english", "tamil"],
            products=["Filter coffee subscriptions", "Cold brew cans"],
            do_not_mention=["pricing", "Competitor Ltd"],
            default_region_code="IN-TN",
        )

        assert brand["languages"] == ["english", "tamil"]
        assert brand["products"][1] == "Cold brew cans"
        assert brand["do_not_mention"] == ["pricing", "Competitor Ltd"]
        assert brand["default_region_code"] == "IN-TN"

    async def test_a_duplicate_slug_is_a_conflict_not_a_500(
        self, client: httpx.AsyncClient
    ) -> None:
        await make(client)

        response = await client.post("/brands", json={"name": "Madras Filter Coffee"})

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    async def test_a_name_with_no_ascii_asks_for_a_slug(self, client: httpx.AsyncClient) -> None:
        """Rather than inventing a transliteration. A slug is a URL the team
        has to live with, and guessing one from Devanagari is not this
        endpoint's call to make."""
        response = await client.post("/brands", json={"name": "कॉफ़ी हाउस"})

        assert response.status_code == 422
        assert "send a slug" in response.json()["detail"]

    async def test_that_name_works_once_a_slug_is_given(self, client: httpx.AsyncClient) -> None:
        brand = await make(client, name="कॉफ़ी हाउस", slug="coffee-house")

        assert brand["name"] == "कॉफ़ी हाउस"
        assert brand["slug"] == "coffee-house"

    async def test_three_digit_hex_is_expanded_and_cased(self, client: httpx.AsyncClient) -> None:
        """Pillow and Remotion both take the string as given, so one
        spelling is stored and the colour pickers agree with the renders."""
        brand = await make(client, primary_color="#2b1", secondary_color="#e3a51d")

        assert brand["primary_color"] == "#22BB11"
        assert brand["secondary_color"] == "#E3A51D"

    @pytest.mark.parametrize("colour", ["coffee", "#12", "2B1A12", "#2B1A12FFFF"])
    async def test_a_colour_that_is_not_hex_is_refused(
        self, client: httpx.AsyncClient, colour: str
    ) -> None:
        response = await client.post("/brands", json={"name": "X", "primary_color": colour})

        assert response.status_code == 422

    async def test_only_the_two_bundled_faces_are_allowed(self, client: httpx.AsyncClient) -> None:
        """A third face would stop the posts looking like this product."""
        response = await client.post("/brands", json={"name": "X", "font_choice": "comic"})

        assert response.status_code == 422

    async def test_blank_textarea_lines_are_dropped(self, client: httpx.AsyncClient) -> None:
        """These arrive as a textarea split on newlines, where an empty line
        is a keystroke rather than an entry."""
        brand = await make(client, products=["  Cold brew  ", "", "   ", "Filters"])

        assert brand["products"] == ["Cold brew", "Filters"]

    async def test_an_unknown_language_is_refused(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/brands", json={"name": "X", "languages": ["klingon"]})

        assert response.status_code == 422

    async def test_a_new_brand_belongs_to_the_default_workspace(
        self, client: httpx.AsyncClient, factory
    ) -> None:
        brand = await make(client)

        async with factory() as session:
            row = await session.get(Brand, brand["id"])

        assert row is not None
        assert row.workspace_id == Workspace.DEFAULT_ID


class TestRead:
    async def test_the_list_is_ordered_by_name(self, client: httpx.AsyncClient) -> None:
        """A team scanning a dropdown wants alphabetical, not creation
        order."""
        await make(client, name="Zephyr Tea")
        await make(client, name="Anna Stores")

        names = [brand["name"] for brand in (await client.get("/brands")).json()]

        assert names == ["Anna Stores", "Zephyr Tea"]

    async def test_one_brand_by_id(self, client: httpx.AsyncClient) -> None:
        brand = await make(client)

        response = await client.get(f"/brands/{brand['id']}")

        assert response.status_code == 200
        assert response.json()["slug"] == "madras-filter-coffee"

    async def test_an_unknown_id_is_a_404(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/brands/9999")).status_code == 404


class TestUpdate:
    async def test_a_patch_leaves_untouched_fields_alone(self, client: httpx.AsyncClient) -> None:
        brand = await make(client, voice_prompt="Warm and dry.", products=["Cold brew"])

        patched = (
            await client.patch(f"/brands/{brand['id']}", json={"secondary_color": "#1E7D5A"})
        ).json()

        assert patched["secondary_color"] == "#1E7D5A"
        assert patched["voice_prompt"] == "Warm and dry."
        assert patched["products"] == ["Cold brew"]

    async def test_an_empty_list_clears_one(self, client: httpx.AsyncClient) -> None:
        """Sent explicitly, [] is a clear. It is absence that means
        unchanged, not emptiness."""
        brand = await make(client, do_not_mention=["pricing"])

        patched = (await client.patch(f"/brands/{brand['id']}", json={"do_not_mention": []})).json()

        assert patched["do_not_mention"] == []

    async def test_a_logo_can_be_removed(self, client: httpx.AsyncClient, factory) -> None:
        brand = await make(client)
        async with factory() as session:
            row = await session.get(Brand, brand["id"])
            assert row is not None
            row.logo_url = "http://minio/logo.png"
            await session.commit()

        patched = (await client.patch(f"/brands/{brand['id']}", json={"logo_url": None})).json()

        assert patched["logo_url"] is None

    async def test_null_on_a_non_nullable_field_is_ignored(self, client: httpx.AsyncClient) -> None:
        """PATCH cannot distinguish a deliberate blank from a field the form
        left out, so the safe reading wins and the column survives."""
        brand = await make(client, voice_prompt="Warm and dry.")

        patched = (await client.patch(f"/brands/{brand['id']}", json={"voice_prompt": None})).json()

        assert patched["voice_prompt"] == "Warm and dry."

    async def test_renaming_onto_another_slug_is_a_conflict(
        self, client: httpx.AsyncClient
    ) -> None:
        await make(client, name="Anna Stores")
        other = await make(client, name="Zephyr Tea")

        response = await client.patch(f"/brands/{other['id']}", json={"slug": "anna-stores"})

        assert response.status_code == 409

    async def test_an_unknown_id_is_a_404(self, client: httpx.AsyncClient) -> None:
        assert (await client.patch("/brands/9999", json={"name": "X"})).status_code == 404


class TestDelete:
    async def add_job(self, factory, brand_id: int, count: int = 1) -> None:
        async with factory() as session:
            trend = (await session.scalars(select(Trend))).one()
            for _ in range(count):
                session.add(
                    ContentJob(
                        workspace_id=Workspace.DEFAULT_ID,
                        brand_id=brand_id,
                        trend_id=trend.id,
                        kind=JobKind.post,
                        language=Language.english,
                        formats=["square"],
                    )
                )
            await session.commit()

    async def test_an_unused_brand_just_goes(self, client: httpx.AsyncClient) -> None:
        brand = await make(client)

        assert (await client.delete(f"/brands/{brand['id']}")).status_code == 204
        assert (await client.get(f"/brands/{brand['id']}")).status_code == 404

    async def test_a_brand_with_content_is_refused_with_the_count(
        self, client: httpx.AsyncClient, factory
    ) -> None:
        """A brand is a settings page and the library is a body of work. The
        count is what a confirm dialog has to say out loud."""
        brand = await make(client)
        await self.add_job(factory, brand["id"], count=3)

        response = await client.delete(f"/brands/{brand['id']}")

        assert response.status_code == 409
        assert "3 items" in response.json()["detail"]

    async def test_nothing_is_lost_by_the_refusal(self, client: httpx.AsyncClient, factory) -> None:
        brand = await make(client)
        await self.add_job(factory, brand["id"])
        await client.delete(f"/brands/{brand['id']}")

        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ContentJob)) == 1
            assert await session.scalar(select(func.count()).select_from(Brand)) == 1

    async def test_force_takes_the_content_with_it(
        self, client: httpx.AsyncClient, factory
    ) -> None:
        brand = await make(client)
        await self.add_job(factory, brand["id"], count=2)

        assert (await client.delete(f"/brands/{brand['id']}?force=true")).status_code == 204

        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ContentJob)) == 0
            assert await session.scalar(select(func.count()).select_from(Brand)) == 0

    async def test_one_item_is_not_called_items(self, client: httpx.AsyncClient, factory) -> None:
        brand = await make(client)
        await self.add_job(factory, brand["id"])

        detail = (await client.delete(f"/brands/{brand['id']}")).json()["detail"]

        assert "1 item in the library" in detail

    async def test_the_slug_is_free_afterwards(self, client: httpx.AsyncClient) -> None:
        """Which is the point of deleting rather than hiding."""
        brand = await make(client)
        await client.delete(f"/brands/{brand['id']}")

        response = await client.post("/brands", json={"name": "Madras Filter Coffee"})

        assert response.status_code == 201

    async def test_an_unknown_id_is_a_404(self, client: httpx.AsyncClient) -> None:
        assert (await client.delete("/brands/9999")).status_code == 404


class TestLogo:
    @pytest.fixture(autouse=True)
    def stub_storage(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
        """Records what would have been uploaded. Patched on the api module
        rather than on `app.storage`, because that is the name the handler
        resolves."""
        seen: list[tuple[str, int]] = []

        def put(key: str, data: bytes, content_type: str | None = None) -> str:
            seen.append((key, len(data)))
            return f"http://minio/trendforge/{key}"

        monkeypatch.setattr(brands_api, "put_bytes", put)
        return seen

    async def test_the_url_lands_on_the_brand(
        self, client: httpx.AsyncClient, stub_storage
    ) -> None:
        brand = await make(client)

        response = await client.post(
            f"/brands/{brand['id']}/logo",
            files={"file": ("logo.png", PNG, "image/png")},
        )

        key, size = stub_storage[0]

        assert response.status_code == 200
        assert response.json()["logo_url"] == f"http://minio/trendforge/{key}"
        assert size == len(PNG)

    async def test_the_key_carries_a_digest_of_the_bytes(
        self, client: httpx.AsyncClient, stub_storage
    ) -> None:
        """The bucket's cache headers say immutable, so a stable key would
        serve the old logo for a year after it changed."""
        brand = await make(client)
        await client.post(
            f"/brands/{brand['id']}/logo", files={"file": ("a.png", PNG, "image/png")}
        )
        await client.post(
            f"/brands/{brand['id']}/logo",
            files={"file": ("a.png", PNG + b"different", "image/png")},
        )

        first, second = (key for key, _ in stub_storage)

        assert first != second
        assert first.startswith(f"brands/{brand['id']}/logo-")

    async def test_the_same_bytes_are_the_same_key(
        self, client: httpx.AsyncClient, stub_storage
    ) -> None:
        brand = await make(client)
        for _ in range(2):
            await client.post(
                f"/brands/{brand['id']}/logo", files={"file": ("a.png", PNG, "image/png")}
            )

        assert stub_storage[0][0] == stub_storage[1][0]

    @pytest.mark.parametrize(
        ("filename", "content_type"),
        [("logo.pdf", "application/pdf"), ("logo.txt", "text/plain"), ("logo.gif", "image/gif")],
    )
    async def test_a_type_the_renderers_cannot_draw_is_refused(
        self, client: httpx.AsyncClient, filename: str, content_type: str
    ) -> None:
        brand = await make(client)

        response = await client.post(
            f"/brands/{brand['id']}/logo", files={"file": (filename, b"data", content_type)}
        )

        assert response.status_code == 415

    async def test_a_charset_parameter_does_not_confuse_it(self, client: httpx.AsyncClient) -> None:
        """Browsers send `image/svg+xml; charset=utf-8` and that is still an
        svg."""
        brand = await make(client)

        response = await client.post(
            f"/brands/{brand['id']}/logo",
            files={"file": ("logo.svg", b"<svg/>", "image/svg+xml; charset=utf-8")},
        )

        assert response.status_code == 200

    async def test_a_camera_roll_upload_is_refused(self, client: httpx.AsyncClient) -> None:
        brand = await make(client)

        response = await client.post(
            f"/brands/{brand['id']}/logo",
            files={"file": ("big.png", b"x" * (brands_api.MAX_LOGO_BYTES + 1), "image/png")},
        )

        assert response.status_code == 413

    async def test_an_empty_file_is_refused(self, client: httpx.AsyncClient) -> None:
        brand = await make(client)

        response = await client.post(
            f"/brands/{brand['id']}/logo", files={"file": ("empty.png", b"", "image/png")}
        )

        assert response.status_code == 422

    async def test_an_unknown_brand_is_a_404_before_the_upload(
        self, client: httpx.AsyncClient, stub_storage
    ) -> None:
        response = await client.post(
            "/brands/9999/logo", files={"file": ("logo.png", PNG, "image/png")}
        )

        assert response.status_code == 404
        assert stub_storage == []


class TestSlugify:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Madras Filter Coffee", "madras-filter-coffee"),
            ("  Anna's Stores!  ", "anna-s-stores"),
            ("Chai & Co.", "chai-co"),
            ("24/7 Kirana", "24-7-kirana"),
            ("कॉफ़ी हाउस", ""),
            ("Zephyr कॉफ़ी", "zephyr"),
        ],
    )
    def test_it_folds_to_ascii_or_gives_up(self, name: str, expected: str) -> None:
        assert brands_api.slugify(name) == expected

    def test_it_fits_the_column(self) -> None:
        assert len(brands_api.slugify("word " * 40)) <= 64
