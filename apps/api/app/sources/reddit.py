"""Reddit, via OAuth against `hot` and `rising`.

Two listings rather than one. `hot` is what the subreddit is reading now and
is dominated by posts several hours old; `rising` is what is accelerating and
is where a trend shows up first. Ranking on `hot` alone makes this a slower
duplicate of Google News.

Credentials are required and there is no anonymous fallback. Reddit closed
`www.reddit.com/*.json` to unauthenticated clients, and from a datacenter IP
it answers 403 to every path — verified on 2026-10-27 against 70 subreddit
`about.json` URLs, all 403. So an adapter that tried to degrade gracefully to
the public JSON would be dead code pretending to be a safety net.

That 403 has one more consequence worth stating: SUBREDDITS below could not
be checked against live Reddit, so it is a map of plausible names rather than
a verified one. A subreddit that is gone, renamed or private must therefore
cost its own listing and nothing more — `fetch` skips it with a log line and
keeps the rest of the region, instead of failing the region on one bad name.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.hashtags import camel_hashtag, literal_hashtags
from app.core.logging import get_logger
from app.models import Region, SourceName
from app.sources.base import RawTrendItem, TrendSource

log = get_logger("source.reddit")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
#: Reads go to oauth.reddit.com. The www host does not accept bearer tokens.
API_BASE = "https://oauth.reddit.com"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Listings merged per subreddit, and why both: see the module docstring.
LISTINGS = ("hot", "rising")

#: Tokens that expire mid-cycle cost a retry, so they are refreshed early.
TOKEN_SKEW_SECONDS = 60

#: National subreddits, used for the country board.
NATIONAL = ("india", "IndiaSpeaks", "indianews")

#: Region code -> subreddits. City codes are included because a city board is
#: where a city subreddit belongs; states roll up their cities' names too, so
#: r/mumbai feeds both Mumbai and Maharashtra.
#:
#: Unverified — see the module docstring. Names are the conventional ones for
#: each place, and a wrong one is skipped rather than fatal.
SUBREDDITS: dict[str, tuple[str, ...]] = {
    # states
    "IN-AP": ("Andhra", "andhrapradesh", "visakhapatnam"),
    "IN-AR": ("ArunachalPradesh",),
    "IN-AS": ("Assam", "guwahati"),
    "IN-BR": ("bihar", "Patna"),
    "IN-CT": ("Chhattisgarh", "raipur"),
    "IN-GA": ("goa",),
    "IN-GJ": ("Gujarat", "ahmedabad", "Surat"),
    "IN-HP": ("HimachalPradesh", "shimla"),
    "IN-HR": ("haryana", "Gurgaon", "faridabad"),
    "IN-JH": ("Jharkhand", "ranchi"),
    "IN-KA": ("bangalore", "karnataka"),
    "IN-KL": ("Kerala", "kochi"),
    "IN-MH": ("mumbai", "pune", "nagpur", "Maharashtra"),
    "IN-ML": ("Shillong", "meghalaya"),
    "IN-MN": ("manipur",),
    "IN-MP": ("indore", "bhopal", "MadhyaPradesh"),
    "IN-MZ": ("Mizoram",),
    "IN-NL": ("Nagaland",),
    "IN-OD": ("Odisha", "bhubaneswar"),
    "IN-PB": ("punjab", "ludhiana"),
    "IN-RJ": ("jaipur", "rajasthan", "udaipur"),
    "IN-SK": ("Sikkim",),
    "IN-TG": ("hyderabad", "Telangana"),
    "IN-TN": ("Chennai", "TamilNadu", "coimbatore"),
    "IN-TR": ("Tripura",),
    "IN-UP": ("lucknow", "UttarPradesh", "kanpur"),
    "IN-UT": ("uttarakhand", "dehradun"),
    "IN-WB": ("kolkata", "westbengal"),
    # union territories
    "IN-CH": ("Chandigarh",),
    "IN-DL": ("delhi", "noida"),
    "IN-JK": ("Kashmir", "srinagar"),
    "IN-LA": ("Ladakh",),
    # cities
    "IN-BR-PAT": ("Patna",),
    "IN-DL-DEL": ("delhi",),
    "IN-GJ-AMD": ("ahmedabad",),
    "IN-GJ-STV": ("Surat",),
    "IN-KA-BLR": ("bangalore",),
    "IN-MH-BOM": ("mumbai",),
    "IN-MH-NAG": ("nagpur",),
    "IN-MH-PNQ": ("pune",),
    "IN-MP-BHO": ("bhopal",),
    "IN-MP-IDR": ("indore",),
    "IN-RJ-JAI": ("jaipur",),
    "IN-TG-HYD": ("hyderabad",),
    "IN-TN-MAA": ("Chennai",),
    "IN-UP-KNU": ("kanpur",),
    "IN-UP-LKO": ("lucknow",),
    "IN-WB-CCU": ("kolkata",),
}

#: Flairs that label the kind of post rather than its subject. Camel-casing
#: these produces #Discussion and #AskIndia on unrelated stories, which is
#: how a tag ends up on a post it has nothing to do with.
_PROCEDURAL_FLAIRS = frozenset(
    {
        "ask india",
        "askindia",
        "discussion",
        "image",
        "video",
        "mod post",
        "megathread",
        "meta",
        "oc",
        "original content",
        "rant",
        "serious",
        "unverified",
        "misleading",
        "non-political",
        "ama",
    }
)


def subreddits_for(region: Region) -> tuple[str, ...]:
    """Subreddits to read for `region`, national ones included for India."""
    if region.code == "IN":
        return NATIONAL
    return SUBREDDITS.get(region.code, ())


def hashtags_from(title: str, flair: str | None) -> list[str]:
    """Tags for one post: what was typed, then the flair if it is a subject.

    Reddit titles rarely carry hashtags, so the flair is the main source —
    but only where it names a topic. A procedural flair is dropped: #Image
    and #Discussion describe the post's format and would be published next to
    a caption about something else entirely.
    """
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str | None) -> None:
        if not tag:
            return
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            tags.append(tag)

    # `literal_hashtags`, not a local `#(\w+)`: Python's \w excludes combining
    # marks, so that pattern captured #मौसम as #मसम — the matra dropped, a
    # different word. The flair path went through camel_hashtag and was fine,
    # which is why the Indic test passed over a broken literal path.
    for tag in literal_hashtags(title, flair or ""):
        add(tag)

    if flair and flair.strip().lower() not in _PROCEDURAL_FLAIRS:
        add(camel_hashtag(flair))

    return tags[:5]


class RedditAdapter(TrendSource):
    name = SourceName.reddit
    label = "Reddit"
    env_vars = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
    #: Between news (1.0) and YouTube (0.6). Upvotes are a real crowd signal
    #: and move fast, but a subreddit is a slice of a region rather than the
    #: region, so its ranks are trusted less than a news chart's.
    weight = 0.7

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client = client
        self._client_id = client_id if client_id is not None else settings.reddit_client_id
        self._client_secret = (
            client_secret if client_secret is not None else settings.reddit_client_secret
        )
        self._user_agent = user_agent or settings.reddit_user_agent
        self._token: str | None = None
        self._token_expires = 0.0

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def supports(self, region: Region) -> bool:
        return bool(subreddits_for(region))

    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        if not self.is_configured():
            log.info(
                "not configured",
                region=region.code,
                reason="REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not set",
            )
            return []

        subs = subreddits_for(region)
        client = self._client
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            token = await self._bearer(client)
            posts: dict[str, dict[str, Any]] = {}
            for sub in subs:
                for listing in LISTINGS:
                    for post in await self._listing(client, token, sub, listing, limit):
                        post_id = str(post.get("id") or "")
                        if not post_id:
                            continue
                        # A post in both hot and rising is one post. Keeping
                        # the higher score means the listing it did better in
                        # decides its rank, which is the honest reading.
                        existing = posts.get(post_id)
                        if existing is None or _score(post) > _score(existing):
                            posts[post_id] = post
        finally:
            if own_client:
                await client.aclose()

        ranked = sorted(posts.values(), key=_score, reverse=True)[:limit]
        return [_to_item(post, rank) for rank, post in enumerate(ranked, start=1)]

    async def _bearer(self, client: httpx.AsyncClient) -> str:
        """A cached app-only token. Reddit's last ~2 hours."""
        if self._token and time.monotonic() < self._token_expires:
            return self._token

        response = await client.post(
            TOKEN_URL,
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise httpx.HTTPError("reddit returned no access_token")
        self._token = token
        self._token_expires = time.monotonic() + max(
            0.0, float(payload.get("expires_in") or 3600) - TOKEN_SKEW_SECONDS
        )
        return token

    async def _listing(
        self,
        client: httpx.AsyncClient,
        token: str,
        sub: str,
        listing: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """One listing, or nothing if that subreddit will not serve it.

        A 404 or 403 here is a name in SUBREDDITS that is gone, renamed or
        private. Since that map is unverified it has to cost this listing
        only — raising would lose the subreddits that do work.
        """
        try:
            response = await client.get(
                f"{API_BASE}/r/{sub}/{listing}",
                params={"limit": str(min(limit, 100)), "raw_json": "1"},
                headers={"Authorization": f"Bearer {token}", "User-Agent": self._user_agent},
            )
        except httpx.HTTPError as exc:
            log.warning("listing failed", subreddit=sub, listing=listing, error=str(exc)[:120])
            return []

        if response.status_code in (403, 404, 451):
            log.info(
                "subreddit unavailable, skipping",
                subreddit=sub,
                listing=listing,
                status=response.status_code,
            )
            return []
        response.raise_for_status()

        children = ((response.json() or {}).get("data") or {}).get("children") or []
        out: list[dict[str, Any]] = []
        for child in children:
            data = (child or {}).get("data") or {}
            if data.get("stickied") or data.get("over_18"):
                # Pinned mod posts are not trends, and NSFW is not something
                # a brand markets against.
                continue
            data["_subreddit"] = sub
            out.append(data)
        return out


def _score(post: dict[str, Any]) -> int:
    """Upvotes, per the spec. `ups` and `score` agree on a listing read."""
    for key in ("ups", "score"):
        value = post.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _to_item(post: dict[str, Any], rank: int) -> RawTrendItem:
    title = str(post.get("title") or "").strip()
    flair = post.get("link_flair_text")
    permalink = str(post.get("permalink") or "")
    return RawTrendItem(
        title=title,
        rank=rank,
        # Upvotes, which are this platform's volume and are not comparable to
        # a YouTube view count — see the trend_sources.volume note.
        volume=_score(post),
        url=f"https://www.reddit.com{permalink}" if permalink else None,
        category=str(flair).strip() if flair else None,
        extra={
            "subreddit": post.get("_subreddit"),
            "comments": int(post.get("num_comments") or 0),
            "hashtags": hashtags_from(title, flair if isinstance(flair, str) else None),
        },
    )
