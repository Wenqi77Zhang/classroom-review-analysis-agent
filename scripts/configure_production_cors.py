"""Maintain one exact HTTPS origin for the production object-storage upload path."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

RULE_ID = "classroom-review-production"
REQUIRED_ENV = (
    "OBJECT_STORAGE_ENDPOINT",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)
OPTIONAL_ENV = ("OBJECT_STORAGE_USE_PATH_STYLE",)


def load_values(path: Path | None) -> dict[str, str]:
    known_env = (*REQUIRED_ENV, *OPTIONAL_ENV)
    values = {name: os.getenv(name, "").strip() for name in known_env}
    if path is not None:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() in known_env:
                values[name.strip()] = value.strip().strip("\"'")
    missing = [name for name in REQUIRED_ENV if not values[name]]
    if missing:
        raise SystemExit(f"环境缺少对象存储变量：{', '.join(missing)}")
    return values


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit("生产 CORS 来源必须是无路径、查询参数和凭据的完整 HTTPS origin。")
    return f"https://{parsed.netloc}"


def create_client(values: dict[str, str]):
    use_path_style = values.get("OBJECT_STORAGE_USE_PATH_STYLE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return boto3.client(
        "s3",
        endpoint_url=values["OBJECT_STORAGE_ENDPOINT"],
        region_name=values["OBJECT_STORAGE_REGION"],
        aws_access_key_id=values["OBJECT_STORAGE_ACCESS_KEY_ID"],
        aws_secret_access_key=values["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if use_path_style else "virtual"},
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def get_rules(client, bucket: str) -> list[dict[str, object]]:
    try:
        response = client.get_bucket_cors(Bucket=bucket)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchCORSConfiguration"}:
            return []
        raise
    return list(response.get("CORSRules", []))


def verify_preflight(client, bucket: str, origin: str) -> None:
    signed_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": "_production_cors_probe_do_not_upload",
            "ContentType": "video/mp4",
        },
        ExpiresIn=60,
        HttpMethod="PUT",
    )
    request = Request(
        signed_url,
        method="OPTIONS",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    with urlopen(request, timeout=10) as response:
        allowed_origin = response.headers.get("Access-Control-Allow-Origin")
        allowed_methods = response.headers.get("Access-Control-Allow-Methods", "")
        allowed_headers = response.headers.get("Access-Control-Allow-Headers", "")
        if (
            allowed_origin != origin
            or "PUT" not in allowed_methods.upper()
            or "content-type" not in allowed_headers.lower()
        ):
            raise SystemExit("B2 CORS 预检响应与生产站点精确来源不匹配。")
        print(f"B2_PRODUCTION_CORS_PREFLIGHT_OK status={response.status}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("show", "apply", "verify", "remove"))
    parser.add_argument("--origin")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()

    values = load_values(args.env_file)
    client = create_client(values)
    bucket = values["OBJECT_STORAGE_BUCKET"]

    if args.action == "verify":
        if not args.origin:
            raise SystemExit("verify 必须提供 --origin。")
        verify_preflight(client, bucket, validate_origin(args.origin))
        return

    rules = get_rules(client, bucket)
    other_rules = [rule for rule in rules if rule.get("ID") != RULE_ID]
    production_rules = [rule for rule in rules if rule.get("ID") == RULE_ID]

    if args.action == "show":
        print(
            "B2_PRODUCTION_CORS_STATUS "
            f"total_rules={len(rules)} production_rule={bool(production_rules)}"
        )
        return

    if args.action == "apply":
        if not args.origin:
            raise SystemExit("apply 必须提供 --origin。")
        origin = validate_origin(args.origin)
        rule = {
            "ID": RULE_ID,
            "AllowedHeaders": ["content-type"],
            "AllowedMethods": ["GET", "HEAD", "PUT"],
            "AllowedOrigins": [origin],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={"CORSRules": [*other_rules, rule]},
        )
        print(f"B2_PRODUCTION_CORS_APPLIED exact_origin={origin}")
        return

    if not production_rules:
        print("B2_PRODUCTION_CORS_REMOVE_SKIPPED production_rule=false")
        return
    if other_rules:
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={"CORSRules": other_rules},
        )
    else:
        client.delete_bucket_cors(Bucket=bucket)
    print("B2_PRODUCTION_CORS_REMOVED production_rule=false")


if __name__ == "__main__":
    main()
