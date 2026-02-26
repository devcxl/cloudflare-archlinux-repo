#!/usr/bin/env python3
"""
Cleanup old package versions from Cloudflare R2 storage.

This script connects to an S3-compatible storage (Cloudflare R2),
lists all packages in the repo/ prefix, and for each package name,
deletes all older versions, keeping only the latest one.

Environment Variables Required:
    AWS_S3_BUCKET: R2 bucket name
    AWS_ACCESS_KEY_ID: R2 access key ID
    AWS_SECRET_ACCESS_KEY: R2 secret access key
    AWS_S3_ENDPOINT: R2 S3-compatible endpoint URL
"""

import os
import re
import sys
import subprocess
import tempfile
import shutil

import boto3


def parse_arch_version(version_string):
    """
    Parse Arch Linux package version string.

    Arch version format: [epoch:]pkgver-pkgrel
    - epoch: Optional epoch number (defaults to 0)
    - pkgver: Package version (e.g., 1.2.3, 1.2.3.r1.g1234abc)
    - pkgrel: Package release number

    Returns a tuple: (epoch, pkgver_parts, pkgrel)
    For comparison purposes.
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
        # pkgver can contain hyphens in some cases
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
    # Common formats: 1.2.3, 1.2.3.r1.g1234abc, 20240101
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


def get_latest_versions(client, bucket, prefix='repo/'):
    """
    Get the latest version for each package in the bucket.

    Returns dict: {package_name: {'version': version, 'key': key, 'arch': arch}}
    """
    latest_versions = {}
    all_packages = []

    # List all objects in the bucket with the prefix
    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            # Get just the filename (remove prefix)
            filename = key[len(prefix):]

            # Skip directories and signature files
            if filename.endswith('/') or filename.endswith('.sig'):
                continue

            # Parse package filename
            parsed = parse_package_filename(filename)
            if parsed is None:
                continue

            name, version, arch = parsed
            all_packages.append({
                'name': name,
                'version': version,
                'arch': arch,
                'key': key
            })

    # Group by package name and find latest version
    for pkg in all_packages:
        name = pkg['name']
        version = pkg['version']

        if name not in latest_versions:
            latest_versions[name] = pkg
        else:
            # Compare versions
            cmp = compare_versions(version, latest_versions[name]['version'])
            if cmp > 0:
                latest_versions[name] = pkg

    return latest_versions, all_packages


def delete_old_versions(client, bucket, latest_versions, all_packages, dry_run=False, max_deletions=50):
    """
    Delete old versions of packages.

    Returns list of deleted keys
    """
    deleted_keys = []

    for pkg in all_packages:
        name = pkg['name']
        version = pkg['version']
        arch = pkg['arch']
        key = pkg['key']

        # Check if this is the latest version for this package
        if name in latest_versions:
            latest_pkg = latest_versions[name]
            if (version == latest_pkg['version'] and
                arch == latest_pkg['arch']):
                # This is the latest version, keep it
                continue

        # Delete the package file
        deleted_keys.append(key)

        # Also delete the signature file if it exists
        sig_key = key + '.sig'
        deleted_keys.append(sig_key)

        # Check deletion limit
        if len(deleted_keys) >= max_deletions * 2:  # Each package has 2 files
            print(f"Warning: Reached maximum deletion limit ({max_deletions} packages)")
            break

    if not deleted_keys:
        print("No old versions to delete.")
        return []

    if dry_run:
        print(f"DRY RUN: Would delete {len(deleted_keys)} files:")
        for key in deleted_keys:
            print(f"  - {key}")
        return []

    # Delete in batches of 1000 (S3 limit)
    batch_size = 1000
    for i in range(0, len(deleted_keys), batch_size):
        batch = deleted_keys[i:i + batch_size]

        # Prepare deletion request
        delete_request = {
            'Objects': [{'Key': key} for key in batch]
        }

        response = client.delete_objects(
            Bucket=bucket,
            Delete=delete_request
        )

        if 'Deleted' in response:
            for deleted in response['Deleted']:
                print(f"Deleted: {deleted['Key']}")

        if 'Errors' in response and response['Errors']:
            print(f"Errors: {response['Errors']}")

    return deleted_keys


def main():
    # Get environment variables
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')

    if not all([bucket, access_key_id, secret_access_key, endpoint]):
        print("Error: Missing required environment variables.", file=sys.stderr)
        print("Required: AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT", file=sys.stderr)
        sys.exit(1)

    # Optional: dry run mode
    dry_run = os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes')

    # Optional: max deletions
    try:
        max_deletions = int(os.environ.get('MAX_DELETIONS', '50'))
    except ValueError:
        max_deletions = 50

    # Optional: database name and GPG signing
    database_name = os.environ.get('DATABASE_NAME', 'self')
    gpg_private_key = os.environ.get('GPG_PRIVATE_KEY', '')
    gpg_passphrase = os.environ.get('GPG_PASSPHRASE', '')

    print(f"Connecting to R2 bucket: {bucket}")
    print(f"Endpoint: {endpoint}")
    print(f"Dry run: {dry_run}")
    print(f"Max deletions: {max_deletions}")
    print(f"Database name: {database_name}")
    print()

    # Create S3 client
    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint
    )

    # Get latest versions
    print("Scanning packages...")
    latest_versions, all_packages = get_latest_versions(client, bucket)

    if not latest_versions:
        print("No packages found in bucket.")
        return

    print(f"Found {len(latest_versions)} unique packages:")
    for name, pkg in sorted(latest_versions.items()):
        print(f"  - {name}: {pkg['version']} ({pkg['arch']})")
    print()

    # Find old versions to delete
    old_packages = []
    for pkg in all_packages:
        name = pkg['name']
        version = pkg['version']
        arch = pkg['arch']

        if name in latest_versions:
            latest_pkg = latest_versions[name]
            if version == latest_pkg['version'] and arch == latest_pkg['arch']:
                continue  # Keep latest version

        old_packages.append(pkg)

    if not old_packages:
        print("No old versions to delete.")
        return

    print(f"Found {len(old_packages)} old versions to delete:")
    for pkg in old_packages:
        print(f"  - {pkg['name']}: {pkg['version']} ({pkg['arch']})")
    print()

    # Create temporary directory for database operations
    with tempfile.TemporaryDirectory() as temp_dir:
        db_dir = os.path.join(temp_dir, 'repo')
        os.makedirs(db_dir)

        # Download database files
        print("Downloading database files...")
        db_files = [
            f"{database_name}.db.tar.gz",
            f"{database_name}.db.tar.gz.sig",
            f"{database_name}.files.tar.gz",
            f"{database_name}.files.tar.gz.sig"
        ]

        for db_file in db_files:
            key = f"repo/{db_file}"
            local_path = os.path.join(db_dir, db_file)
            try:
                client.download_file(bucket, key, local_path)
                print(f"  Downloaded: {db_file}")
            except Exception as e:
                print(f"  Warning: Failed to download {db_file}: {e}")

        # Delete old versions from R2
        print("\nDeleting old package files...")
        deleted = delete_old_versions(
            client,
            bucket,
            latest_versions,
            all_packages,
            dry_run=dry_run,
            max_deletions=max_deletions
        )

        # Remove old packages from database using repo-remove
        if not dry_run and old_packages:
            print("\nRemoving old package entries from database...")

            # Collect unique package names to remove
            packages_to_remove = list(set([pkg['name'] for pkg in old_packages]))

            # Use repo-remove to remove packages from the database
            db_path = os.path.join(db_dir, f"{database_name}.db.tar.gz")

            if os.path.exists(db_path):
                try:
                    # Construct repo-remove command
                    cmd = ['repo-remove', db_path] + packages_to_remove
                    print(f"  Running command: {' '.join(cmd)}")

                    # Run repo-remove
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        cwd=db_dir
                    )

                    if result.returncode == 0:
                        print(f"  Success: Removed {len(packages_to_remove)} packages from database")

                        # Sign the database if GPG key is provided
                        if gpg_private_key and gpg_passphrase:
                            print("\nSigning database...")
                            sign_database(db_dir, database_name, gpg_private_key, gpg_passphrase)

                        # Upload updated database files to R2
                        print("\nUploading updated database...")
                        upload_database(client, bucket, db_dir, database_name)
                    else:
                        print(f"  Error: repo-remove failed with exit code {result.returncode}", file=sys.stderr)
                        print(f"  stdout: {result.stdout}", file=sys.stderr)
                        print(f"  stderr: {result.stderr}", file=sys.stderr)

                except Exception as e:
                    print(f"  Error: Failed to run repo-remove: {e}", file=sys.stderr)
            else:
                print("  Warning: Database file not found, skipping database update")

    if not dry_run:
        print(f"\nDeleted {len(deleted)} files.")


def sign_database(repo_dir, db_name, gpg_private_key, gpg_passphrase):
    """
    Sign the pacman database using GPG.
    """
    try:
        # Import GPG key
        import_cmd = [
            'gpg', '--batch', '--pinentry-mode', 'loopback',
            '--passphrase', gpg_passphrase, '--import'
        ]
        subprocess.run(
            import_cmd,
            input=gpg_private_key.encode('utf-8'),
            capture_output=True,
            check=True
        )

        # Sign database files
        for db_file in [f"{db_name}.db.tar.gz", f"{db_name}.files.tar.gz"]:
            db_path = os.path.join(repo_dir, db_file)
            sig_path = f"{db_path}.sig"

            if os.path.exists(db_path):
                sign_cmd = [
                    'gpg', '--batch', '--pinentry-mode', 'loopback',
                    '--passphrase', gpg_passphrase, '--detach-sig', '--yes', db_path
                ]
                subprocess.run(sign_cmd, capture_output=True, check=True, cwd=repo_dir)
                print(f"  Signed: {db_file}")

    except subprocess.CalledProcessError as e:
        print(f"  Error: GPG signing failed: {e}", file=sys.stderr)
        print(f"  stdout: {e.stdout}", file=sys.stderr)
        print(f"  stderr: {e.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"  Error: GPG signing failed: {e}", file=sys.stderr)


def upload_database(client, bucket, repo_dir, db_name):
    """
    Upload updated database files to R2.
    """
    db_files = [
        f"{db_name}.db.tar.gz",
        f"{db_name}.db.tar.gz.sig",
        f"{db_name}.files.tar.gz",
        f"{db_name}.files.tar.gz.sig"
    ]

    for db_file in db_files:
        local_path = os.path.join(repo_dir, db_file)
        if os.path.exists(local_path):
            key = f"repo/{db_file}"
            try:
                client.upload_file(
                    local_path,
                    bucket,
                    key,
                    ExtraArgs={'ContentType': 'application/octet-stream'}
                )
                print(f"  Uploaded: {db_file}")
            except Exception as e:
                print(f"  Error: Failed to upload {db_file}: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
