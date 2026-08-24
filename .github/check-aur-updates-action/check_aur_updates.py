#!/usr/bin/env python3
"""
Check package updates and trigger security scan workflows.

This script:
1. Detects package source from URL (AUR RPC for aur.archlinux.org, GitHub API for github.com)
2. Gets already built versions from R2 storage
3. Compares versions and detects updates
4. Triggers security-scan.yml workflow for packages with updates

Environment Variables Required:
    PACKAGES_JSON: JSON list of packages [{name, url}]
    AWS_S3_BUCKET: R2 bucket name
    AWS_ACCESS_KEY_ID: R2 access key ID
    AWS_SECRET_ACCESS_KEY: R2 secret access key
    AWS_S3_ENDPOINT: R2 S3-compatible endpoint URL
    GH_TOKEN: GitHub token for triggering workflows / API calls
    GH_REPOSITORY: GitHub repository path (owner/repo)
"""

import json
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
import requests


PACKAGE_PREFIX = 'packages/'
GITHUB_API_BASE = 'https://api.github.com'


def parse_aur_pkgname(url):
    """
    Extract AUR package name from an aur.archlinux.org URL.

    Examples:
        https://aur.archlinux.org/visual-studio-code-bin.git → visual-studio-code-bin
        https://aur.archlinux.org/pkgname → pkgname

    Returns package name (str) or None.
    """
    m = re.search(r'aur\.archlinux\.org/([^/\s]+?)(?:\.git)?/?$', url)
    return m.group(1) if m else None


def parse_github_repo(git_url):
    """
    Extract owner/repo from a GitHub URL.

    Examples:
        https://github.com/user/repo.git  → user/repo
        https://github.com/user/repo      → user/repo
        git@github.com:user/repo.git      → user/repo
    """
    patterns = [
        r'github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$',
    ]
    for pat in patterns:
        m = re.search(pat, git_url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def get_github_latest_release(owner_repo, gh_token=None):
    """
    Get the latest release tag from GitHub.

    Returns tag_name (str) or None.
    """
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if gh_token:
        headers['Authorization'] = f'Bearer {gh_token}'

    url = f'{GITHUB_API_BASE}/repos/{owner_repo}/releases/latest'

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            print(f"    No releases found for {owner_repo}, trying tags...")
            return get_github_latest_tag(owner_repo, gh_token)
        response.raise_for_status()
        data = response.json()
        tag = data.get('tag_name', '')
        return tag.lstrip('v')
    except requests.RequestException as e:
        print(f"    Error fetching release for {owner_repo}: {e}", file=sys.stderr)
        return None


def get_github_latest_tag(owner_repo, gh_token=None):
    """
    Get the latest tag from GitHub (fallback when no releases exist).

    Returns tag_name (str) or None.
    """
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if gh_token:
        headers['Authorization'] = f'Bearer {gh_token}'

    url = f'{GITHUB_API_BASE}/repos/{owner_repo}/tags?per_page=1'

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            tag = data[0].get('name', '')
            return tag.lstrip('v')
    except requests.RequestException as e:
        print(f"    Error fetching tags for {owner_repo}: {e}", file=sys.stderr)

    return None


def get_aur_versions(package_names):
    """
    Get package versions from AUR RPC API.

    Returns dict: {package_name: version}
    """
    aur_versions = {}

    if not package_names:
        return aur_versions

    url = "https://aur.archlinux.org/rpc?v=5&type=info"
    for name in package_names:
        url += f"&arg[]={name}"

    print(f"Querying AUR API for {len(package_names)} packages...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if (data.get('type') == 'info' or data.get('type') == 'multiinfo') and 'results' in data:
            for result in data['results']:
                pkg_name = result.get('Name')
                pkg_version = result.get('Version')
                if pkg_name and pkg_version:
                    aur_versions[pkg_name] = pkg_version
                    print(f"  {pkg_name}: {pkg_version}")

    except requests.RequestException as e:
        print(f"Error querying AUR API: {e}", file=sys.stderr)

    return aur_versions


def get_git_versions(git_packages, gh_token=None):
    """
    Get latest tag versions from GitHub for github.com-sourced packages.

    Returns dict: {package_name: version}
    """
    git_versions = {}

    if not git_packages:
        return git_versions

    print(f"Querying GitHub API for {len(git_packages)} git packages...")

    for pkg in git_packages:
        name = pkg.get('name')
        url = pkg.get('url', '')
        owner_repo = parse_github_repo(url)

        if not owner_repo:
            print(f"  {name}: could not parse GitHub repo from URL: {url}")
            continue

        tag = get_github_latest_release(owner_repo, gh_token)
        if tag:
            git_versions[name] = tag
            print(f"  {name}: {tag} (from {owner_repo})")
        else:
            print(f"  {name}: could not determine version for {owner_repo}")

    return git_versions


def get_r2_versions(client, bucket, prefix=PACKAGE_PREFIX):
    """
    Get package versions from R2 storage.

    Returns dict: {package_name: version}
    """
    r2_versions = {}

    print(f"Scanning R2 bucket packages directory: {bucket}/{prefix}")

    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                key = obj['Key']
                filename = key[len(prefix):]

                if filename.endswith('/') or filename.endswith('.sig'):
                    continue

                if not filename.endswith('.pkg.tar.zst'):
                    continue

                parsed = parse_package_filename(filename)
                if parsed:
                    name, version, arch = parsed
                    if re.match(r'^[a-zA-Z0-9@._+-]+$', name):
                        current_version = r2_versions.get(name)
                        if current_version is None or compare_versions(version, current_version) > 0:
                            r2_versions[name] = version

    except Exception as e:
        print(f"Error scanning R2: {e}", file=sys.stderr)

    return r2_versions


def trigger_security_scan(gh_token, gh_repo, package_name, source_url):
    """
    Trigger security-scan.yml workflow for a specific package.

    Returns True if successful, False otherwise.
    """
    headers = {
        'Authorization': f'Bearer {gh_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    data = {
        'ref': 'master',
        'inputs': {
            'package-name': package_name,
            'source-url': source_url,
        }
    }

    url = f'https://api.github.com/repos/{gh_repo}/actions/workflows/security-scan.yml/dispatches'

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error triggering security scan for {package_name}: {e}", file=sys.stderr)
        return False


def is_aur_url(url):
    """Check if a URL points to the AUR."""
    return 'aur.archlinux.org' in url


def main():
    packages_json = os.environ.get('PACKAGES_JSON', '[]')
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')
    gh_token = os.environ.get('GH_TOKEN')
    gh_repo = os.environ.get('GH_REPOSITORY')

    if not all([bucket, access_key_id, secret_access_key, endpoint, gh_token, gh_repo]):
        print("Error: Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    try:
        packages = json.loads(packages_json) if packages_json.strip() else []
    except json.JSONDecodeError as e:
        print(f"Error parsing PACKAGES_JSON: {e}", file=sys.stderr)
        packages = []

    if not packages:
        print("No packages configured.")
        return

    # Split packages by URL domain for version checking strategy
    aur_packages = [p for p in packages if is_aur_url(p.get('url', ''))]
    git_packages = [p for p in packages if not is_aur_url(p.get('url', ''))]

    aur_count = len(aur_packages)
    git_count = len(git_packages)
    print(f"Checking {len(packages)} packages for updates ({aur_count} AUR, {git_count} Git)...")
    print()

    # Get versions from sources
    aur_names = [p['name'] for p in aur_packages]
    aur_versions = get_aur_versions(aur_names)
    git_versions = get_git_versions(git_packages, gh_token)
    print()

    # Get R2 versions
    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint
    )
    r2_versions = get_r2_versions(client, bucket, prefix=PACKAGE_PREFIX)

    if r2_versions:
        print(f"Found {len(r2_versions)} packages in R2")
        for name, version in sorted(r2_versions.items()):
            print(f"  {name}: {version}")
    else:
        print("No packages found in R2")
    print()

    # Compare versions and trigger security scans
    updates_found = []

    for pkg in packages:
        pkg_name = pkg['name']
        pkg_url = pkg.get('url', '')

        # Get source version
        if is_aur_url(pkg_url):
            source_ver = aur_versions.get(pkg_name)
            source_label = 'AUR'
        else:
            source_ver = git_versions.get(pkg_name)
            source_label = 'Git'

        if source_ver is None:
            print(f"Warning: {pkg_name} not found in {source_label}")
            continue

        r2_ver = r2_versions.get(pkg_name)

        if not r2_ver:
            print(f"New package: {pkg_name} ({source_ver})")
            if trigger_security_scan(gh_token, gh_repo, pkg_name, pkg_url):
                updates_found.append(pkg_name)
                print(f"  ✓ Security scan triggered")
            continue

        cmp = compare_versions(source_ver, r2_ver)
        if cmp > 0:
            print(f"Update available: {pkg_name}")
            print(f"  {source_label} version: {source_ver}")
            print(f"  R2 version:       {r2_ver}")
            if trigger_security_scan(gh_token, gh_repo, pkg_name, pkg_url):
                updates_found.append(pkg_name)
                print(f"  ✓ Security scan triggered")

    print()
    if updates_found:
        print(f"Updates found: {len(updates_found)}")
        print(f"Triggered security scans for: {', '.join(updates_found)}")
    else:
        print("No updates found. All packages are up to date.")


if __name__ == '__main__':
    main()
