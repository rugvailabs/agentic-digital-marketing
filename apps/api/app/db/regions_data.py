"""Static region table: India, 28 states, 8 union territories, 16 major cities.

Two external identifier systems are attached here:

* ``google_trends_geo`` — ISO 3166-2:IN codes as Google Trends spells them.
  Trends uses the pre-2011 ``IN-OR`` for Odisha, not the current ``IN-OD``.
  Four small UTs (Andaman & Nicobar, Dadra & Nagar Haveli and Daman & Diu,
  Ladakh, Lakshadweep) are not served by Trends at region granularity, so they
  carry ``None`` and the adapter skips them rather than erroring 36 times an hour.

* ``x_woeid`` — Yahoo WOEIDs, attached to cities only; a state rolls up to its
  cities' WOEIDs (``Region.woeids_for_rollup``). These come from the city list X
  historically served on ``trends/available``. The X adapter is a stub in step 1,
  so treat the values as unverified until a bearer token is wired up and
  ``trends/available`` can confirm them.
"""

from typing import TypedDict


class RegionSeed(TypedDict):
    code: str
    name: str
    kind: str
    parent: str | None
    google_trends_geo: str | None
    x_woeid: int | None
    sort_order: int


COUNTRY: list[RegionSeed] = [
    {
        "code": "IN",
        "name": "India",
        "kind": "country",
        "parent": None,
        "google_trends_geo": "IN",
        "x_woeid": 23424848,
        "sort_order": 0,
    }
]

# (code, name, trends geo) — geo None => not served by Trends at this level.
_STATES: list[tuple[str, str, str | None]] = [
    ("IN-AP", "Andhra Pradesh", "IN-AP"),
    ("IN-AR", "Arunachal Pradesh", "IN-AR"),
    ("IN-AS", "Assam", "IN-AS"),
    ("IN-BR", "Bihar", "IN-BR"),
    ("IN-CT", "Chhattisgarh", "IN-CT"),
    ("IN-GA", "Goa", "IN-GA"),
    ("IN-GJ", "Gujarat", "IN-GJ"),
    ("IN-HR", "Haryana", "IN-HR"),
    ("IN-HP", "Himachal Pradesh", "IN-HP"),
    ("IN-JH", "Jharkhand", "IN-JH"),
    ("IN-KA", "Karnataka", "IN-KA"),
    ("IN-KL", "Kerala", "IN-KL"),
    ("IN-MP", "Madhya Pradesh", "IN-MP"),
    ("IN-MH", "Maharashtra", "IN-MH"),
    ("IN-MN", "Manipur", "IN-MN"),
    ("IN-ML", "Meghalaya", "IN-ML"),
    ("IN-MZ", "Mizoram", "IN-MZ"),
    ("IN-NL", "Nagaland", "IN-NL"),
    ("IN-OD", "Odisha", "IN-OR"),
    ("IN-PB", "Punjab", "IN-PB"),
    ("IN-RJ", "Rajasthan", "IN-RJ"),
    ("IN-SK", "Sikkim", "IN-SK"),
    ("IN-TN", "Tamil Nadu", "IN-TN"),
    ("IN-TG", "Telangana", "IN-TG"),
    ("IN-TR", "Tripura", "IN-TR"),
    ("IN-UP", "Uttar Pradesh", "IN-UP"),
    ("IN-UT", "Uttarakhand", "IN-UT"),
    ("IN-WB", "West Bengal", "IN-WB"),
]

_UNION_TERRITORIES: list[tuple[str, str, str | None]] = [
    ("IN-AN", "Andaman and Nicobar Islands", None),
    ("IN-CH", "Chandigarh", "IN-CH"),
    ("IN-DH", "Dadra and Nagar Haveli and Daman and Diu", None),
    ("IN-DL", "Delhi", "IN-DL"),
    ("IN-JK", "Jammu and Kashmir", "IN-JK"),
    ("IN-LA", "Ladakh", None),
    ("IN-LD", "Lakshadweep", None),
    ("IN-PY", "Puducherry", "IN-PY"),
]

# (code, name, parent state/UT code, WOEID)
_CITIES: list[tuple[str, str, str, int]] = [
    ("IN-DL-DEL", "Delhi", "IN-DL", 20070458),
    ("IN-MH-BOM", "Mumbai", "IN-MH", 2295411),
    ("IN-KA-BLR", "Bengaluru", "IN-KA", 2295420),
    ("IN-TN-MAA", "Chennai", "IN-TN", 2295424),
    ("IN-WB-CCU", "Kolkata", "IN-WB", 2295386),
    ("IN-TG-HYD", "Hyderabad", "IN-TG", 2295414),
    ("IN-GJ-AMD", "Ahmedabad", "IN-GJ", 2295402),
    ("IN-MH-PNQ", "Pune", "IN-MH", 2295412),
    ("IN-RJ-JAI", "Jaipur", "IN-RJ", 2295401),
    ("IN-UP-LKO", "Lucknow", "IN-UP", 2295377),
    ("IN-GJ-STV", "Surat", "IN-GJ", 2295476),
    ("IN-UP-KNU", "Kanpur", "IN-UP", 2295378),
    ("IN-MH-NAG", "Nagpur", "IN-MH", 2282863),
    ("IN-MP-IDR", "Indore", "IN-MP", 2295407),
    ("IN-MP-BHO", "Bhopal", "IN-MP", 2295405),
    ("IN-BR-PAT", "Patna", "IN-BR", 2295381),
]


def all_regions() -> list[RegionSeed]:
    """Parents first, so a single pass can resolve parent_id."""
    rows: list[RegionSeed] = list(COUNTRY)

    # States and UTs interleave alphabetically on the region strip; the
    # country stays pinned first via sort_order 0.
    tier: list[tuple[str, str, str | None, str]] = [
        (code, name, geo, "state") for code, name, geo in _STATES
    ] + [(code, name, geo, "union_territory") for code, name, geo in _UNION_TERRITORIES]
    tier.sort(key=lambda r: r[1])

    for order, (code, name, geo, kind) in enumerate(tier, start=1):
        rows.append(
            {
                "code": code,
                "name": name,
                "kind": kind,
                "parent": "IN",
                "google_trends_geo": geo,
                "x_woeid": None,
                "sort_order": order,
            }
        )

    for order, (code, name, parent, woeid) in enumerate(_CITIES, start=100):
        rows.append(
            {
                "code": code,
                "name": name,
                "kind": "city",
                "parent": parent,
                # Trends does serve metro-level geos, but only via numeric DMA
                # ids we don't have; cities ingest from News + YouTube + X.
                "google_trends_geo": None,
                "x_woeid": woeid,
                "sort_order": order,
            }
        )

    return rows


STATE_COUNT = len(_STATES)
UT_COUNT = len(_UNION_TERRITORIES)
CITY_COUNT = len(_CITIES)
