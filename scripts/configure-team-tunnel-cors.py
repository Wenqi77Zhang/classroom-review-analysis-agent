"""Safely manage the exact Backblaze B2 CORS origin for a Quick Tunnel."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

RULE_ID = "team-tunnel-staging"
REQUIRED_ENV = (
    "OBJECT_STORAGE_ENDPOINT",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    missing = [name for name in REQUIRED_ENV if not values.get(name)]
    if missing:
        raise SystemExit(f"环境文件缺少对象存储变量：{', '.join(missing)}")
    return values


def validate_quick_tunnel_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".trycloudflare.com")
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit("只允许精确的 https://<随机名称>.trycloudflare.com 来源。")
    return f"https://{parsed.netloc}"


def is_team_tunnel_rule(rule: dict[str, object]) -> bool:
    origins = rule.get("AllowedOrigins")
    if not isinstance(origins, list) or len(origins) != 1:
        return False
    parsed = urlsplit(str(origins[0]))
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower().endswith(".trycloudflare.com")
        and "PUT" in rule.get("AllowedMethods", [])
    )


def create_client(values: dict[str, str]):
    return boto3.client(
        "s3",
        endpoint_url=values["OBJECT_STORAGE_ENDPOINT"],
        region_name=values["OBJECT_STORAGE_REGION"],
        aws_access_key_id=values["OBJECT_STORAGE_ACCESS_KEY_ID"],
        aws_secret_access_key=values["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
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
            "Key": "_team_tunnel_cors_probe_do_not_upload",
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
            raise SystemExit("B2 CORS 预检响应与本次精确来源不匹配。")
        print(f"B2_CORS_PREFLIGHT_OK status={response.status}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("action", choices=("show", "apply", "verify", "remove"))
    parser.add_argument("--origin")
    args = parser.parse_args()

    values = load_env(args.env_file)
    client = create_client(values)
    bucket = values["OBJECT_STORAGE_BUCKET"]
    rules = get_rules(client, bucket)
    other_rules = [rule for rule in rules if not is_team_tunnel_rule(rule)]
    staging_rules = [rule for rule in rules if is_team_tunnel_rule(rule)]

    if args.action == "show":
        print(
            "B2_CORS_STATUS "
            f"total_rules={len(rules)} team_tunnel_rule={bool(staging_rules)}"
        )
        return

    if args.action == "verify":
        if not args.origin:
            raise SystemExit("verify 必须提供 --origin。")
        verify_preflight(client, bucket, validate_quick_tunnel_origin(args.origin))
        return

    if args.action == "apply":
        if not args.origin:
            raise SystemExit("apply 必须提供 --origin。")
        origin = validate_quick_tunnel_origin(args.origin)
        staging_rule = {
            "ID": RULE_ID,
            "AllowedHeaders": ["content-type"],
            "AllowedMethods": ["GET", "HEAD", "PUT"],
            "AllowedOrigins": [origin],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={"CORSRules": [*other_rules, staging_rule]},
        )
        print(f"B2_CORS_APPLIED exact_origin={origin}")
        return

    if not staging_rules:
        print("B2_CORS_REMOVE_SKIPPED team_tunnel_rule=false")
        return
    if other_rules:
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={"CORSRules": other_rules},
        )
    else:
        client.delete_bucket_cors(Bucket=bucket)
    print("B2_CORS_REMOVED team_tunnel_rule=false")


if __name__ == "__main__":
    main()
