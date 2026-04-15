#!/usr/bin/env python3
"""
Download latest package files from Cloudflare R2.

This script scans the bucket root, keeps only the latest version for each
package, and downloads those package files into the local repository
directory. The current package being rebuilt can be skipped with SKIP_PACKAGE.
"""

import os
import re
import sys
import time

import boto3
from botocore.config import Config


def parse_arch_version(version_string):
    """Parse Arch Linux package version string for comparison."""
    if ':' in version_string:
        epoch_str, version_string = version_string.split(':', 1)
        try:
            epoch = int(epoch_str)
        except ValueError:
            epoch = 0
    else:
        epoch = 0

    if '-' in version_string:
        pkgver, pkgrel_str = version_string.rsplit('-', 1)
        try:
            pkgrel = int(pkgrel_str)
        except ValueError:
            pkgrel = 0
    else:
        pkgver = version_string
        pkgrel = 0

    pkgver_parts = []
    current = ''
    for char in pkgver:
        if char.isalpha():
            if current:
                pkgver_parts.append((0, current))
                current = ''
            pkgver_parts.append((1, char))
        elif char.isdigit():
            current += char
        else:
            if current:
                pkgver_parts.append((0, current))
                current = ''
            pkgver_parts.append((2, char))

    if current:
        pkgver_parts.append((0, current))

    return epoch, pkgver_parts, pkgrel


def compare_versions(v1, v2):
    """Compare two Arch Linux version strings."""
    parsed1 = parse_arch_version(v1)
    parsed2 = parse_arch_version(v2)

    if parsed1[0] != parsed2[0]:
        return 1 if parsed1[0] > parsed2[0] else -1

    for i in range(min(len(parsed1[1]), len(parsed2[1]))):
        type1, val1 = parsed1[1][i]
        type2, val2 = parsed2[1][i]

        if type1 == type2:
            if type1 == 0:
                try:
                    num1 = int(val1)
                    num2 = int(val2)
                    if num1 != num2:
                        return 1 if num1 > num2 else -1
                except ValueError:
                    if val1 != val2:
                        return 1 if val1 > val2 else -1
            elif val1 != val2:
                return 1 if val1 > val2 else -1
        else:
            return 1 if type1 > type2 else -1

    if len(parsed1[1]) != len(parsed2[1]):
        return 1 if len(parsed1[1]) > len(parsed2[1]) else -1

    if parsed1[2] != parsed2[2]:
        return 1 if parsed1[2] > parsed2[2] else -1

    return 0


def parse_package_filename(filename):
    """Parse package filename into (name, version, arch)."""
    if not filename.endswith('.pkg.tar.zst'):
        return None

    base = filename[:-len('.pkg.tar.zst')]
    arch_match = re.search(r'-(x86_64|i686|armv7h|aarch64|any)$', base)
    if not arch_match:
        return None

    arch = arch_match.group(1)
    base = base[:arch_match.start()]

    version_match = re.search(r'-\d+(\.\d+)*', base)
    if not version_match:
        return None

    version_start = version_match.start() + 1
    version = base[version_start:]
    name = base[:version_match.start()]

    if not re.match(r'^[a-zA-Z0-9@._+-]+$', name):
        return None

    if not re.match(r'^[a-zA-Z0-9_]+$', arch):
        return None

    return name, version, arch


def get_latest_packages(client, bucket, prefix=''):
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
        latest_packages = get_latest_packages(client, bucket, prefix='')
    except Exception as exc:
        print(f'Error accessing R2 bucket: {exc}', file=sys.stderr)
        sys.exit(1)

    if not latest_packages:
        print('No package files found in bucket root. This may be expected on first build.')
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
