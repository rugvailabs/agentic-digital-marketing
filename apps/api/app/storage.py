"""Object storage for rendered assets: MinIO locally, R2 in prod.

Images, video and voiceover all land in one bucket, which is why this sits
at the top of the package rather than under `images/`.

Both speak S3, so this is one boto3 client with an endpoint override. The
bucket is created on first use because a fresh `tf.ps1 up` has an empty MinIO
and a 404 on the first render is a worse first run than an idempotent create.
"""

from __future__ import annotations

import threading
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("storage")

_bucket_lock = threading.Lock()
_bucket_ready = False


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        # R2 and MinIO both want path-style addressing; virtual-host style
        # would resolve bucket.localhost.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    with _bucket_lock:
        if _bucket_ready:
            return
        client = _client()
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            try:
                client.create_bucket(Bucket=settings.s3_bucket)
                log.info("bucket created", bucket=settings.s3_bucket)
            except ClientError as exc:
                if "BucketAlreadyOwnedByYou" not in str(exc):
                    raise
        _bucket_ready = True


#: Keys include the job id and the variant, so a re-render writes a new key
#: rather than fighting a CDN cache. Hence immutable.
CACHE_CONTROL = "public, max-age=31536000, immutable"

CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
}


def content_type_for(key: str) -> str:
    return CONTENT_TYPES.get(key.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def public_url(key: str) -> str:
    return f"{settings.s3_public_url.rstrip('/')}/{settings.s3_bucket}/{key}"


def internal_url(key: str) -> str:
    """The same object, addressed from inside the compose network.

    `public_url` is what a browser uses, and locally that is localhost on a
    published port — which resolves to nothing inside a container. The
    Remotion renderer is a container fetching an `<Img src>`, so it needs
    this one.
    """
    return f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket}/{key}"


def get_bytes(key: str) -> bytes:
    """Read an object back. Raises ClientError when it is not there.

    Used by the Pillow templates to draw a brand logo. They run in the
    worker, where `public_url` is unreachable, so they go through the S3
    client rather than over HTTP.
    """
    response = _client().get_object(Bucket=settings.s3_bucket, Key=key)
    data: bytes = response["Body"].read()
    return data


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> str:
    """Upload and return the browser-reachable URL."""
    ensure_bucket()
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type or content_type_for(key),
        CacheControl=CACHE_CONTROL,
    )
    log.info("asset stored", key=key, bytes=len(data))
    return public_url(key)


def put_png(key: str, data: bytes) -> str:
    return put_bytes(key, data, "image/png")
