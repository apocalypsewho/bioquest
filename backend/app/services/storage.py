"""StorageBackend: local disk in the MVP; S3-compatible adapter (boto3) when configured."""
from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod

from ..config import get_settings


class StorageBackend(ABC):
    @abstractmethod
    def put(self, data: bytes, content_type: str, suffix: str) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def put(self, data, content_type, suffix):
        key = f"{uuid.uuid4().hex}{suffix}"
        with open(os.path.join(self.root, key), "wb") as f:
            f.write(data)
        return key

    def get(self, key):
        path = os.path.join(self.root, os.path.basename(key))
        with open(path, "rb") as f:
            return f.read()


class S3Storage(StorageBackend):  # pragma: no cover - needs credentials
    def __init__(self, bucket: str, endpoint_url: str | None):
        import boto3  # optional dependency

        self.bucket = bucket
        self.s3 = boto3.client("s3", endpoint_url=endpoint_url or None)

    def put(self, data, content_type, suffix):
        key = f"uploads/{uuid.uuid4().hex}{suffix}"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()


def get_storage() -> StorageBackend:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage(s.s3_bucket, s.s3_endpoint_url)
    return LocalStorage(s.storage_dir)
