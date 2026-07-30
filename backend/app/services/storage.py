"""S3-compatible object storage boundary for uploads and downloads."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Request

from backend.app.config import Settings
from backend.app.errors import UpstreamUnavailableError


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str
    etag: str | None = None
    checksum: str | None = None


class ObjectStorage(Protocol):
    async def presign_upload(self, object_key: str, content_type: str) -> str: ...

    async def presign_download(self, object_key: str) -> str: ...

    async def put(self, object_key: str, content: bytes, content_type: str) -> None: ...

    async def head(self, object_key: str) -> ObjectMetadata | None: ...

    async def delete(self, object_key: str) -> None: ...


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


def get_object_storage(request: Request) -> ObjectStorage:
    return request.app.state.object_storage
