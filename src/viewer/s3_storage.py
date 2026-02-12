"""S3-compatible storage backend for log files (Tigris, R2, AWS S3)."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from log_viewer import parse_jsonl_lines, parse_log_metadata

logger = logging.getLogger(__name__)

# Matches "_debug.jsonl" suffix
_DEBUG_SUFFIX = "_debug.jsonl"
_PRESIGNED_URL_EXPIRY = 3600  # 1 hour
_CATALOG_KEY = "_catalog.json"


def _is_debug_key(key: str) -> bool:
    return key.endswith(_DEBUG_SUFFIX)


def _parse_tags_dict(data: Any) -> dict[str, list[str]]:
    """Normalise raw JSON into {filename: [tag, ...]}."""
    if not isinstance(data, dict):
        return {}
    return {
        name: [str(t) for t in tags if str(t).strip()]
        for name, tags in data.items()
        if isinstance(tags, list)
    }


class S3LogStorage:
    """Read/write log files, images and tags from S3-compatible storage."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str = "auto",
    ):
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

        kwargs: dict[str, Any] = {"region_name": region_name}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if aws_access_key_id:
            kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.s3 = boto3.client("s3", **kwargs)

        # Lazy-loaded catalog (None = not yet attempted, [] = empty/missing)
        self._catalog: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _load_catalog(self) -> list[dict[str, Any]] | None:
        """Fetch and parse _catalog.json from S3.

        Returns the parsed list on success, or None if the catalog is
        missing or malformed (with a warning logged).
        """
        if self._catalog is not None:
            return self._catalog

        key = self._key(_CATALOG_KEY)
        text = self._get_text(key)
        if text is None:
            logger.warning(
                "Catalog %s not found in s3://%s — falling back to "
                "per-file S3 listing (slow)",
                key,
                self.bucket,
            )
            self._catalog = []
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Catalog %s is not valid JSON — ignoring", key)
            self._catalog = []
            return None

        if not isinstance(data, list):
            logger.warning("Catalog %s has unexpected format — ignoring", key)
            self._catalog = []
            return None

        self._catalog = data
        logger.info("Loaded catalog with %d entries", len(data))
        return self._catalog

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _key(self, *parts: str) -> str:
        return self.prefix + "/".join(parts)

    def _get_text(self, key: str) -> str | None:
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def _put_text(
        self, key: str, text: str, content_type: str = "application/json"
    ) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType=content_type,
        )

    def _list_keys(self, prefix: str) -> list[dict[str, Any]]:
        """Return list of {Key, Size, LastModified} under *prefix*."""
        items: list[dict[str, Any]] = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                items.append(obj)
        return items

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def list_groups(self, include_debug: bool = False) -> list[dict[str, Any]]:
        """Return [{name, file_count}, ...] for directories with .jsonl files.

        Group names use the full relative path, e.g. "default/default1"
        or "live/different_behaviour/distract_person".

        Uses _catalog.json when available; falls back to S3 listing.
        """
        catalog = self._load_catalog()
        if catalog:
            return self._list_groups_from_catalog(catalog, include_debug)

        # Fallback: full S3 listing
        groups: dict[str, int] = {}
        for obj in self._list_keys(self.prefix):
            key = obj["Key"]
            rel = key[len(self.prefix) :]
            parts = rel.split("/")
            if len(parts) < 2 or not parts[-1].endswith(".jsonl"):
                continue
            if not include_debug and _is_debug_key(parts[-1]):
                continue
            group_name = "/".join(parts[:-1])
            groups[group_name] = groups.get(group_name, 0) + 1

        return sorted(
            [{"name": n, "file_count": c} for n, c in groups.items()],
            key=lambda g: g["name"],
        )

    @staticmethod
    def _list_groups_from_catalog(
        catalog: list[dict[str, Any]], include_debug: bool
    ) -> list[dict[str, Any]]:
        groups: dict[str, int] = {}
        for entry in catalog:
            name = entry.get("name", "")
            if not include_debug and _is_debug_key(name):
                continue
            group = entry.get("group")
            if group:
                groups[group] = groups.get(group, 0) + 1
        return sorted(
            [{"name": n, "file_count": c} for n, c in groups.items()],
            key=lambda g: g["name"],
        )

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def list_files(
        self, group: str | None = None, include_debug: bool = False
    ) -> list[dict[str, Any]]:
        """Return file metadata list for .jsonl files in a group (or all).

        Each file dict includes a ``group`` field derived from the S3 key
        path so the frontend can address the file without needing the
        currently-selected group.

        Uses _catalog.json when available; falls back to S3 listing +
        per-file Range requests.
        """
        catalog = self._load_catalog()
        if catalog:
            return self._list_files_from_catalog(catalog, group, include_debug)

        # Fallback: full S3 listing with per-file metadata extraction
        prefix = (self._key(group) + "/") if group else self.prefix

        files = []
        for obj in self._list_keys(prefix):
            key = obj["Key"]
            filename = key.rsplit("/", 1)[-1]
            if not filename.endswith(".jsonl"):
                continue
            if not include_debug and _is_debug_key(filename):
                continue

            rel = key[len(self.prefix) :]
            parts = rel.rsplit("/", 1)
            file_group = parts[0] if len(parts) > 1 else None

            metadata = self._extract_metadata(key, file_size=obj["Size"])

            files.append(
                {
                    "name": filename,
                    "group": file_group,
                    "path": key,
                    "size": obj["Size"],
                    "mtime": obj["LastModified"].timestamp(),
                    "mtime_iso": obj["LastModified"].isoformat(),
                    "entry_count": metadata["entry_count"],
                    "model": metadata["model"],
                    "first_timestamp": metadata["first_timestamp"],
                }
            )

        return sorted(files, key=lambda f: f["name"], reverse=True)

    def _list_files_from_catalog(
        self,
        catalog: list[dict[str, Any]],
        group: str | None,
        include_debug: bool,
    ) -> list[dict[str, Any]]:
        files = []
        for entry in catalog:
            name = entry.get("name", "")
            if not name.endswith(".jsonl"):
                continue
            if not include_debug and _is_debug_key(name):
                continue
            file_group = entry.get("group")
            if group and file_group != group:
                continue

            # Construct S3 key path on the fly
            path = self._key(file_group, name) if file_group else self._key(name)

            files.append(
                {
                    "name": name,
                    "group": file_group,
                    "path": path,
                    "size": entry.get("size", 0),
                    "entry_count": entry.get("entry_count", 0),
                    "model": entry.get("model", "unknown"),
                    "first_timestamp": entry.get("first_timestamp"),
                }
            )

        return sorted(files, key=lambda f: f["name"], reverse=True)

    _METADATA_RANGE_BYTES = 4096  # first 4 KB is enough for ~20 JSONL lines
    _AVG_BYTES_PER_LINE = 200

    def _extract_metadata(self, key: str, file_size: int) -> dict[str, Any]:
        """Read first 4 KB via Range request for model/timestamp.

        Estimates entry_count from file_size instead of downloading the
        whole object.
        """
        try:
            resp = self.s3.get_object(
                Bucket=self.bucket,
                Key=key,
                Range=f"bytes=0-{self._METADATA_RANGE_BYTES - 1}",
            )
            head_text = resp["Body"].read().decode("utf-8", errors="replace")
        except ClientError:
            return {"model": "unknown", "first_timestamp": None, "entry_count": 0}

        meta = parse_log_metadata(head_text.splitlines())
        # Override entry_count with estimate from total file size
        meta["entry_count"] = max(1, file_size // self._AVG_BYTES_PER_LINE)
        return meta

    # ------------------------------------------------------------------
    # Log entries
    # ------------------------------------------------------------------

    def read_log_entries(
        self,
        filename: str,
        group: str | None = None,
        since_line: int | None = None,
    ) -> list[dict[str, Any]]:
        """Parse a JSONL file from S3 and return entries."""
        key = self._key(group, filename) if group else self._key(filename)
        text = self._get_text(key)
        if text is None:
            return []
        return parse_jsonl_lines(text.splitlines(), since_line=since_line)

    def file_exists(self, filename: str, group: str | None = None) -> bool:
        key = self._key(group, filename) if group else self._key(filename)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def load_tags(self, group: str | None = None) -> dict[str, list[str]]:
        key = self._key(group, "tags.json") if group else self._key("tags.json")
        text = self._get_text(key)
        if text is None:
            return {}
        try:
            return _parse_tags_dict(json.loads(text))
        except json.JSONDecodeError:
            return {}

    def load_all_tags(self) -> dict[str, list[str]]:
        """Aggregate tags from all groups into a single dict."""
        merged: dict[str, list[str]] = {}
        merged.update(self.load_tags())  # root-level tags
        for g in self.list_groups():
            merged.update(self.load_tags(group=g["name"]))
        return merged

    def save_tags(self, tags: dict[str, list[str]], group: str | None = None) -> None:
        key = self._key(group, "tags.json") if group else self._key("tags.json")
        self._put_text(key, json.dumps(tags, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def get_image_url(self, image_path: str, group: str | None = None) -> str | None:
        """Return a presigned URL for an image stored in S3."""
        # Extract the *_images/filename tail (last two path segments)
        parts = image_path.split("/")
        tail = "/".join(parts[-2:]) if len(parts) >= 2 else image_path

        # If group is known, resolve directly inside prefix/group/
        if group:
            key = self._key(group, tail)
            try:
                self.s3.head_object(Bucket=self.bucket, Key=key)
                return self.s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=_PRESIGNED_URL_EXPIRY,
                )
            except ClientError:
                pass

        # Fallback: strip common prefixes and try direct resolution
        for strip_prefix in ("log_images/", "logs/"):
            if image_path.startswith(strip_prefix):
                image_path = image_path[len(strip_prefix) :]
                break

        key = self.prefix + image_path
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return None

        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=_PRESIGNED_URL_EXPIRY,
        )

    # ------------------------------------------------------------------
    # Search (basic)
    # ------------------------------------------------------------------

    def search_logs(
        self,
        query: str,
        level: str | None = None,
        event: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text search across all non-debug JSONL files at root level.

        # TODO: search does not cover grouped files — only root-level .jsonl.
        """
        if not query:
            return []

        results: list[dict[str, Any]] = []
        search_text = query.lower()

        for obj in self._list_keys(self.prefix):
            key = obj["Key"]
            filename = key.rsplit("/", 1)[-1]
            if not filename.endswith(".jsonl") or _is_debug_key(filename):
                continue
            rel = key[len(self.prefix) :]
            if "/" in rel:
                continue

            entries = self.read_log_entries(filename)
            for entry in entries:
                if entry.get("_parse_error"):
                    if search_text in entry.get("raw_line", "").lower():
                        entry_copy = dict(entry)
                        entry_copy["_file"] = filename
                        results.append(entry_copy)
                    continue
                if level and entry.get("level") != level:
                    continue
                if event and entry.get("event") != event:
                    continue
                searchable = " ".join(
                    [
                        entry.get("message", ""),
                        entry.get("tool", ""),
                        entry.get("event", ""),
                        json.dumps(entry.get("args", {}), ensure_ascii=False),
                        str(entry.get("result", "")),
                    ]
                ).lower()
                if search_text in searchable:
                    entry_copy = dict(entry)
                    entry_copy["_file"] = filename
                    results.append(entry_copy)

        return results
