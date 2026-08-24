#!/usr/bin/env python3
"""
Cleanup old package versions from Cloudflare R2 storage.

This script scans the packages/ prefix in the bucket, keeps only the latest
version for each package/arch pair, and deletes older package files together with their
signature files. It does not modify the repository database.
"""

import os
import re
import sys
from pathlib import Path

# 版本比较逻辑统一收口到 lib/version.py，消除三处重复实现，并与 pacman vercmp 语义对齐
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.version import (  # noqa: E402
    compare_versions,
    parse_arch_version,
    parse_package_filename,
)

import boto3


PACKAGE_PREFIX = 'packages/'


def get_latest_versions(client, bucket, prefix=PACKAGE_PREFIX):
    """Get the latest version for each package in the R2 packages/ directory."""
    latest_versions = {}
    all_packages = []

    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            if key.endswith('/') or key.endswith('.sig'):
                continue

            filename = key[len(prefix):] if prefix else key
            parsed = parse_package_filename(filename)
            if parsed is None:
                continue

            name, version, arch = parsed
            package = {'name': name, 'version': version, 'arch': arch, 'key': key}
            all_packages.append(package)

            package_key = (name, arch)
            current = latest_versions.get(package_key)
            if current is None or compare_versions(version, current['version']) > 0:
                latest_versions[package_key] = package

    return latest_versions, all_packages


def delete_old_versions(client, bucket, latest_versions, all_packages, dry_run=False, max_deletions=50):
    """Delete older package files and their signatures from R2."""
    deleted_keys = []

    for package in all_packages:
        package_key = (package['name'], package['arch'])
        latest_package = latest_versions.get(package_key)
        if latest_package and package['version'] == latest_package['version']:
            continue

        deleted_keys.append(package['key'])
        deleted_keys.append(f"{package['key']}.sig")

        if len(deleted_keys) >= max_deletions * 2:
            print(f'Warning: Reached maximum deletion limit ({max_deletions} packages)')
            break

    if not deleted_keys:
        print('No old versions to delete.')
        return []

    if dry_run:
        print(f'DRY RUN: Would delete {len(deleted_keys)} files:')
        for key in deleted_keys:
            print(f'  - {key}')
        return []

    batch_size = 1000
    for offset in range(0, len(deleted_keys), batch_size):
        batch = deleted_keys[offset:offset + batch_size]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={'Objects': [{'Key': key} for key in batch]},
        )

        if response.get('Errors'):
            raise RuntimeError(f"Failed to delete some objects: {response['Errors']}")

        for deleted in response.get('Deleted', []):
            print(f"Deleted: {deleted['Key']}")

    return deleted_keys


def main():
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')

    if not all([bucket, access_key_id, secret_access_key, endpoint]):
        print('Error: Missing required environment variables.', file=sys.stderr)
        print(
            'Required: AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT',
            file=sys.stderr,
        )
        sys.exit(1)

    dry_run = os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes')
    try:
        max_deletions = int(os.environ.get('MAX_DELETIONS', '50'))
    except ValueError:
        max_deletions = 50

    print(f'Connecting to R2 bucket: {bucket}')
    print(f'Endpoint: {endpoint}')
    print(f'Dry run: {dry_run}')
    print(f'Max deletions: {max_deletions}')
    print()

    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint,
    )

    try:
        latest_versions, all_packages = get_latest_versions(client, bucket, prefix=PACKAGE_PREFIX)
    except Exception as exc:
        print(f'Error scanning bucket: {exc}', file=sys.stderr)
        sys.exit(1)

    if not latest_versions:
        print('No packages found in R2 packages/ directory. Nothing to clean.')
        return

    print(f'Found {len(latest_versions)} latest package entries:')
    for package in sorted(latest_versions.values(), key=lambda item: (item['name'], item['arch'])):
        print(f"  - {package['name']}: {package['version']} ({package['arch']})")
    print()

    deleted_keys = delete_old_versions(
        client,
        bucket,
        latest_versions,
        all_packages,
        dry_run=dry_run,
        max_deletions=max_deletions,
    )

    if not dry_run:
        print(f'\nDeleted {len(deleted_keys)} files.')


if __name__ == '__main__':
    main()
