#!/usr/bin/env python3
"""
Download packages and database from R2 storage.

This script downloads all files from R2 repo/ prefix,
optionally skipping packages matching a specific name.

Environment Variables Required:
    AWS_S3_BUCKET: R2 bucket name
    AWS_ACCESS_KEY_ID: R2 access key ID
    AWS_SECRET_ACCESS_KEY: R2 secret access key
    AWS_S3_ENDPOINT: R2 S3-compatible endpoint URL
    SKIP_PACKAGE: Package name to skip (optional)
    DESTINATION: Destination directory (default: repo)
"""

import os
import sys
import time

import boto3
from botocore.config import Config


def main():
    # Get environment variables
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')
    skip_package = os.environ.get('SKIP_PACKAGE', '')
    destination = os.environ.get('DESTINATION', 'repo')

    if not all([bucket, access_key_id, secret_access_key, endpoint]):
        print("Error: Missing required environment variables.", file=sys.stderr)
        print("Required: AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading from R2 bucket: {bucket}")
    print(f"Destination: {destination}")
    if skip_package:
        print(f"Skipping package: {skip_package}")
    print()

    # Create destination directory
    os.makedirs(destination, exist_ok=True)

    # Connect to R2 with retries and timeouts
    config = Config(
        retries={
            'max_attempts': 3,
            'mode': 'standard'
        },
        connect_timeout=10,
        read_timeout=30
    )

    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint,
        config=config
    )

    # List and download objects
    prefix = 'repo/'
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        has_contents = False
        for page in pages:
            if 'Contents' not in page:
                continue

            has_contents = True
            for obj in page['Contents']:
                key = obj['Key']
                filename = key[len(prefix):]

                # Skip directories and packages
                if not filename or filename.endswith('/'):
                    continue

                # Skip packages matching skip_package
                if skip_package and filename.startswith(skip_package + '-'):
                    print(f"  Skipping: {filename}")
                    skipped_count += 1
                    continue

                # 只下载数据库文件，不下载包文件
                # 需要下载的文件：self.db.tar.gz, self.db.tar.gz.sig, self.files.tar.gz, self.files.tar.gz.sig
                if not (filename.endswith('.db.tar.gz') or
                        filename.endswith('.db.tar.gz.sig') or
                        filename.endswith('.files.tar.gz') or
                        filename.endswith('.files.tar.gz.sig')):
                    print(f"  Skipping package file: {filename}")
                    skipped_count += 1
                    continue

                # Download the file with retries
                dest_path = os.path.join(destination, filename)
                print(f"  Downloading: {filename}")

                success = False
                for attempt in range(3):
                    try:
                        client.download_file(bucket, key, dest_path)
                        downloaded_count += 1
                        success = True
                        print(f"  ✓ Downloaded successfully (attempt {attempt + 1})")
                        break
                    except Exception as e:
                        print(f"  Error downloading {filename} (attempt {attempt + 1}): {e}", file=sys.stderr)
                        if attempt < 2:
                            time.sleep(2)

                if not success:
                    failed_count += 1
                    print(f"  ❌ Failed to download after 3 attempts")

        if not has_contents:
            print("  No objects found in bucket. This is expected if it's the first build.")

    except Exception as e:
        print(f"Error accessing R2 bucket: {e}", file=sys.stderr)
        print("  This could be because the bucket doesn't exist yet or is empty.")

    # Summary
    print()
    print(f"Download complete:")
    print(f"  - Successfully downloaded: {downloaded_count}")
    if skipped_count:
        print(f"  - Skipped: {skipped_count}")
    if failed_count:
        print(f"  - Failed: {failed_count}")

    # Continue execution even if there were failures
    if failed_count > 0:
        print(f"\nWarning: Some files failed to download, but the process continues.", file=sys.stderr)


if __name__ == '__main__':
    main()
