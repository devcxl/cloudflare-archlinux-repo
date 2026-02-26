#!/usr/bin/env python3
"""
Check AUR package updates and trigger build workflows.

This script:
1. Queries AUR RPC API to get current package versions
2. Gets already built versions from R2 storage
3. Compares versions and detects updates
4. Triggers build.yml workflow for packages with updates

Environment Variables Required:
    PACKAGES: Space-separated list of AUR packages to check
    AWS_S3_BUCKET: R2 bucket name
    AWS_ACCESS_KEY_ID: R2 access key ID
    AWS_SECRET_ACCESS_KEY: R2 secret access key
    AWS_S3_ENDPOINT: R2 S3-compatible endpoint URL
    GH_TOKEN: GitHub token for triggering workflows
    GH_REPOSITORY: GitHub repository path (owner/repo)
"""

import os
import re
import sys

import boto3
import requests


def parse_package_filename(filename):
    """
    Parse Arch Linux package filename.

    Format: {name}-{version}-{arch}.pkg.tar.zst
    Example: localsend-bin-1.14.4-1-x86_64.pkg.tar.zst

    Returns tuple: (name, version, arch) or None if invalid
    """
    # Expected extension
    if not filename.endswith('.pkg.tar.zst'):
        return None

    # Remove extension and parse filename
    base = filename[:-len('.pkg.tar.zst')]

    # 查找架构部分（x86_64, i686, armv7h, aarch64 等）
    arch_match = re.search(r'-(x86_64|i686|armv7h|aarch64)$', base)
    if not arch_match:
        return None

    arch = arch_match.group(1)
    # 从 base 中移除 arch 部分
    base = base[:arch_match.start()]

    # 查找版本部分（版本格式通常包含数字、点和可能的连字符或其他字符）
    # 版本通常以数字开头，但可能包含字母字符（如 rc, beta 等）
    version_match = re.search(r'-\d+(\.\d+)*', base)
    if not version_match:
        return None

    version_start = version_match.start() + 1
    version = base[version_start:]
    name = base[:version_match.start()]

    # Validate package name (whitelist)
    if not re.match(r'^[a-zA-Z0-9@._+-]+$', name):
        return None

    # Validate arch
    if not re.match(r'^[a-zA-Z0-9_]+$', arch):
        return None

    return (name, version, arch)


def parse_arch_version(version_string):
    """
    Parse Arch Linux package version string.

    Arch version format: [epoch:]pkgver-pkgrel
    - epoch: Optional epoch number (defaults to 0)
    - pkgver: Package version (e.g., 1.2.3, 1.2.3.r1.g1234abc)
    - pkgrel: Package release number

    Returns a tuple: (epoch, pkgver_parts, pkgrel)
    """
    # Handle epoch prefix
    if ':' in version_string:
        epoch_str, version_string = version_string.split(':', 1)
        try:
            epoch = int(epoch_str)
        except ValueError:
            epoch = 0
    else:
        epoch = 0

    # Split pkgver and pkgrel
    if '-' in version_string:
        # Last hyphen is pkgver-pkgrel separator
        parts = version_string.rsplit('-', 1)
        pkgver = parts[0]
        try:
            pkgrel = int(parts[1])
        except ValueError:
            pkgrel = 0
    else:
        pkgver = version_string
        pkgrel = 0

    # Parse pkgver into comparable parts
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

    return (epoch, pkgver_parts, pkgrel)


def compare_versions(v1, v2):
    """
    Compare two Arch Linux version strings.

    Returns:
        1 if v1 > v2
        -1 if v1 < v2
        0 if v1 == v2
    """
    parsed1 = parse_arch_version(v1)
    parsed2 = parse_arch_version(v2)

    # Compare epoch first
    if parsed1[0] != parsed2[0]:
        return 1 if parsed1[0] > parsed2[0] else -1

    # Compare pkgver parts
    for i in range(min(len(parsed1[1]), len(parsed2[1]))):
        type1, val1 = parsed1[1][i]
        type2, val2 = parsed2[1][i]

        if type1 == type2:
            if type1 == 0:  # Number
                try:
                    num1 = int(val1)
                    num2 = int(val2)
                    if num1 != num2:
                        return 1 if num1 > num2 else -1
                except ValueError:
                    if val1 != val2:
                        return 1 if val1 > val2 else -1
            else:  # Letter or other
                if val1 != val2:
                    return 1 if val1 > val2 else -1
        else:
            # Different types: numbers come before letters
            return 1 if type1 > type2 else -1

    # If one has more parts, it's considered newer
    if len(parsed1[1]) != len(parsed2[1]):
        return 1 if len(parsed1[1]) > len(parsed2[1]) else -1

    # Compare pkgrel
    if parsed1[2] != parsed2[2]:
        return 1 if parsed1[2] > parsed2[2] else -1

    return 0


def get_aur_versions(packages):
    """
    Get package versions from AUR RPC API.

    Returns dict: {package_name: version}
    """
    aur_versions = {}

    if not packages:
        return aur_versions

    # Build API URL with all packages
    url = "https://aur.archlinux.org/rpc?v=5&type=info"
    for pkg in packages:
        url += f"&arg[]={pkg}"

    print(f"Querying AUR API for {len(packages)} packages...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get('type') == 'info' and 'results' in data:
            for result in data['results']:
                pkg_name = result.get('Name')
                pkg_version = result.get('Version')
                if pkg_name and pkg_version:
                    aur_versions[pkg_name] = pkg_version
                    print(f"  {pkg_name}: {pkg_version}")

    except requests.RequestException as e:
        print(f"Error querying AUR API: {e}", file=sys.stderr)

    return aur_versions


def get_r2_versions(client, bucket, prefix='repo/'):
    """
    Get package versions from R2 storage.

    Returns dict: {package_name: version}
    """
    r2_versions = {}

    print(f"Scanning R2 bucket: {bucket}")

    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                key = obj['Key']
                filename = key[len(prefix):]

                # Skip directories and signature files
                if filename.endswith('/') or filename.endswith('.sig'):
                    continue

                # Parse package filename
                # Format: {name}-{version}-{arch}.pkg.tar.zst
                if not filename.endswith('.pkg.tar.zst'):
                    continue

                # 使用与 clean_old_packages.py 中相同的解析逻辑
                parsed = parse_package_filename(filename)
                if parsed:
                    name, version, arch = parsed
                    # Validate package name
                    if re.match(r'^[a-zA-Z0-9@._+-]+$', name):
                        r2_versions[name] = version

    except Exception as e:
        print(f"Error scanning R2: {e}", file=sys.stderr)

    return r2_versions


def trigger_build(gh_token, gh_repo, package_name):
    """
    Trigger build.yml workflow for a specific package.

    Returns True if successful, False otherwise.
    """
    headers = {
        'Authorization': f'Bearer {gh_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    data = {
        'ref': 'master',
        'inputs': {
            'repo-name': package_name
        }
    }

    url = f'https://api.github.com/repos/{gh_repo}/actions/workflows/build.yml/dispatches'

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error triggering build for {package_name}: {e}", file=sys.stderr)
        return False


def main():
    # Get environment variables
    packages_str = os.environ.get('PACKAGES', '')
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')
    gh_token = os.environ.get('GH_TOKEN')
    gh_repo = os.environ.get('GH_REPOSITORY')

    if not all([packages_str, bucket, access_key_id, secret_access_key, endpoint, gh_token, gh_repo]):
        print("Error: Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    # Parse package list
    packages = packages_str.split()
    print(f"Checking {len(packages)} packages for updates...")
    print()

    # Get AUR versions
    aur_versions = get_aur_versions(packages)
    print()

    # Get R2 versions
    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint
    )
    r2_versions = get_r2_versions(client, bucket)

    if r2_versions:
        print(f"Found {len(r2_versions)} packages in R2")
        for name, version in sorted(r2_versions.items()):
            print(f"  {name}: {version}")
    else:
        print("No packages found in R2")
    print()

    # Compare versions and trigger builds
    updates_found = []
    for pkg_name in packages:
        aur_ver = aur_versions.get(pkg_name)
        r2_ver = r2_versions.get(pkg_name)

        if not aur_ver:
            print(f"Warning: {pkg_name} not found in AUR")
            continue

        if not r2_ver:
            # Package not in R2, trigger build
            print(f"New package: {pkg_name} ({aur_ver})")
            if trigger_build(gh_token, gh_repo, pkg_name):
                updates_found.append(pkg_name)
                print(f"  ✓ Build triggered")
            continue

        # Compare versions
        cmp = compare_versions(aur_ver, r2_ver)
        if cmp > 0:
            print(f"Update available: {pkg_name}")
            print(f"  AUR version: {aur_ver}")
            print(f"  R2 version:  {r2_ver}")
            if trigger_build(gh_token, gh_repo, pkg_name):
                updates_found.append(pkg_name)
                print(f"  ✓ Build triggered")

    # Summary
    print()
    if updates_found:
        print(f"Updates found: {len(updates_found)}")
        print(f"Triggered builds for: {', '.join(updates_found)}")
    else:
        print("No updates found. All packages are up to date.")


if __name__ == '__main__':
    main()
