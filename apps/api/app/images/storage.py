"""Object storage for rendered assets: MinIO locally, R2 in prod.

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

log = get_logger("images.storage")

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


def put_png(key: str, data: bytes) -> str:
    """Upload and return the public URL."""
    ensure_bucket()
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
    )
    url = f"{settings.s3_public_url.rstrip('/')}/{settings.s3_bucket}/{key}"
    log.info("asset stored", key=key, bytes=len(data))
    return url
