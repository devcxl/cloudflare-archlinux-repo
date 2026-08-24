#!/usr/bin/env python3
"""
Download latest package files from Cloudflare R2.

This script scans the packages/ prefix in the bucket, keeps only the latest
version for each package, and downloads those package files into the local repository
directory. The current package being rebuilt can be skipped with SKIP_PACKAGE.
"""

import os
import re
import sys
import time
from pathlib import Path

# 版本比较逻辑统一收口到 lib/version.py，消除三处重复实现，并与 pacman vercmp 语义对齐
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.version import (  # noqa: E402
    compare_versions,
    parse_package_filename,
)

import boto3
from botocore.config import Config


PACKAGE_PREFIX = 'packages/'


def get_latest_packages(client, bucket, prefix=PACKAGE_PREFIX):
    """Return latest package file for each package/arch pair."""
    latest_packages = {}

    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            if key.endswith('/'):
                continue

            filename = key[len(prefix):] if prefix else key
            parsed = parse_package_filename(filename)
            if parsed is None:
                continue

            name, version, arch = parsed
            package_key = (name, arch)
            current = latest_packages.get(package_key)
            if current is None or compare_versions(version, current['version']) > 0:
                latest_packages[package_key] = {
                    'name': name,
                    'version': version,
                    'arch': arch,
                    'key': key,
                    'filename': filename,
                }

    return latest_packages


def main():
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')
    skip_package = os.environ.get('SKIP_PACKAGE', '')
    destination = os.environ.get('DESTINATION', 'repo')

    if not all([bucket, access_key_id, secret_access_key, endpoint]):
        print('Error: Missing required environment variables.', file=sys.stderr)
        print(
            'Required: AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT',
            file=sys.stderr,
        )
        sys.exit(1)

    print(f'Downloading latest packages from R2 bucket: {bucket}')
    print(f'Destination: {destination}')
    if skip_package:
        print(f'Skipping package: {skip_package}')
    print()

    os.makedirs(destination, exist_ok=True)

    config = Config(
        retries={'max_attempts': 3, 'mode': 'standard'},
        connect_timeout=10,
        read_timeout=30,
    )
    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint,
        config=config,
    )

    try:
        latest_packages = get_latest_packages(client, bucket, prefix=PACKAGE_PREFIX)
    except Exception as exc:
        print(f'Error accessing R2 bucket: {exc}', file=sys.stderr)
        sys.exit(1)

    if not latest_packages:
        print('No package files found in R2 packages/ directory. This may be expected on first build.')
        return

    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    for package in sorted(latest_packages.values(), key=lambda item: (item['name'], item['arch'])):
        if skip_package and package['name'] == skip_package:
            print(f"  Skipping current package: {package['filename']}")
            skipped_count += 1
            continue

        dest_path = os.path.join(destination, package['filename'])
        print(f"  Downloading: {package['filename']}")

        success = False
        for attempt in range(3):
            try:
                client.download_file(bucket, package['key'], dest_path)
                downloaded_count += 1
                success = True
                print(f'  ✓ Downloaded successfully (attempt {attempt + 1})')
                break
            except Exception as exc:
                print(
                    f"  Error downloading {package['filename']} (attempt {attempt + 1}): {exc}",
                    file=sys.stderr,
                )
                if attempt < 2:
                    time.sleep(2)

        if not success:
            failed_count += 1
            print('  ❌ Failed to download after 3 attempts', file=sys.stderr)

    print()
    print('Download complete:')
    print(f'  - Successfully downloaded: {downloaded_count}')
    if skipped_count:
        print(f'  - Skipped: {skipped_count}')
    if failed_count:
        print(f'  - Failed: {failed_count}')
        sys.exit(1)


if __name__ == '__main__':
    main()
