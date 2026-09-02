"""S3-compatible object storage boundary for uploads and downloads."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Request

from backend.app.config import Settings
from backend.app.errors import UpstreamUnavailableError

READINESS_OBJECT_KEY = "_system/readiness-v1"


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str
    etag: str | None = None
    checksum: str | None = None


class ObjectStorage(Protocol):
    async def ready(self) -> None: ...

    async def presign_upload(self, object_key: str, content_type: str) -> str: ...

    async def presign_download(self, object_key: str) -> str: ...

    async def put(self, object_key: str, content: bytes, content_type: str) -> None: ...

    async def head(self, object_key: str) -> ObjectMetadata | None: ...

    async def delete(self, object_key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...


class S3ObjectStorage:
    """Backblaze B2/MinIO implementation through their shared S3-compatible API."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.object_storage_bucket
        self._ttl_seconds = settings.object_storage_presigned_url_ttl_seconds
        addressing_style = "path" if settings.object_storage_use_path_style else "virtual"
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint,
            region_name=settings.object_storage_region,
            aws_access_key_id=settings.object_storage_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.object_storage_secret_access_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": addressing_style},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=10,
            ),
        )

    async def presign_upload(self, object_key: str, content_type: str) -> str:
        return await asyncio.to_thread(
            self._presign,
            "put_object",
            {"Bucket": self._bucket, "Key": object_key, "ContentType": content_type},
        )

    async def ready(self) -> None:
        """Verify that the configured private bucket is reachable.

        Restricted application keys commonly cannot call ``HeadBucket`` even
        though they can read and write objects. Probe the fixed, non-sensitive
        readiness sentinel provisioned at startup instead, so a missing object
        is also treated as not ready without listing files or exposing a URL.
        """
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=READINESS_OBJECT_KEY,
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailableError("对象存储暂时不可用。") from exc

    async def presign_download(self, object_key: str) -> str:
        return await asyncio.to_thread(
            self._presign,
            "get_object",
            {"Bucket": self._bucket, "Key": object_key},
        )

    async def put(self, object_key: str, content: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailableError("对象存储暂时无法保存导出文件。") from exc

    def _presign(self, operation: str, params: dict[str, str]) -> str:
        try:
            return self._client.generate_presigned_url(
                operation,
                Params=params,
                ExpiresIn=self._ttl_seconds,
                HttpMethod="PUT" if operation == "put_object" else "GET",
            )
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise UpstreamUnavailableError("对象存储暂时无法生成访问地址。") from exc

    async def head(self, object_key: str) -> ObjectMetadata | None:
        return await asyncio.to_thread(self._head, object_key)

    def _head(self, object_key: str) -> ObjectMetadata | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise UpstreamUnavailableError("对象存储暂时无法核验文件。") from exc
        except BotoCoreError as exc:
            raise UpstreamUnavailableError("对象存储暂时无法核验文件。") from exc

        etag = response.get("ETag")
        checksum = (
            response.get("ChecksumSHA256")
            or response.get("ChecksumSHA1")
            or response.get("ChecksumCRC32C")
            or response.get("ChecksumCRC32")
        )
        return ObjectMetadata(
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            etag=str(etag).strip('"') if etag else None,
            checksum=str(checksum) if checksum else None,
        )

    async def delete(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailableError("对象存储暂时无法删除文件。") from exc

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object below one owner-scoped classroom prefix.

        Classroom deletion must also remove older report formats and derived
        artifacts that are not represented by a single current database row.
        S3 list/delete is used only for the exact immutable owner/classroom
        prefix; callers must never pass a bucket-wide or owner-wide prefix.
        """
        parts = prefix.split("/")
        if len(parts) != 5 or parts[0] != "owners" or parts[2] != "classrooms" or parts[4]:
            raise ValueError("对象删除前缀必须精确限定到单个课堂。")
        try:
            UUID(parts[1])
            UUID(parts[3])
        except (ValueError, AttributeError) as exc:
            raise ValueError("对象删除前缀必须精确限定到单个课堂。") from exc
        return await asyncio.to_thread(self._delete_prefix, prefix)

    def _delete_prefix(self, prefix: str) -> int:
        deleted = 0
        continuation_token: str | None = None
        try:
            while True:
                params: dict[str, str] = {"Bucket": self._bucket, "Prefix": prefix}
                if continuation_token:
                    params["ContinuationToken"] = continuation_token
                response = self._client.list_objects_v2(**params)
                keys = [
                    str(item["Key"])
                    for item in response.get("Contents", [])
                    if isinstance(item, dict) and item.get("Key")
                ]
                if keys:
                    result = self._client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
                    )
                    if result.get("Errors"):
                        raise UpstreamUnavailableError("对象存储未能完整删除课堂文件。")
                    deleted += len(keys)
                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")
                if not continuation_token:
                    raise UpstreamUnavailableError("对象存储分页结果不完整，已停止删除。")
        except UpstreamUnavailableError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailableError("对象存储暂时无法删除课堂文件。") from exc
        return deleted


def get_object_storage(request: Request) -> ObjectStorage:
    return request.app.state.object_storage
