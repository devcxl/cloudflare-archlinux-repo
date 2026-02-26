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

import boto3


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

    # Connect to R2
    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint
    )

    # List and download objects
    prefix = 'repo/'
    downloaded_count = 0
    skipped_count = 0

    paginator = client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            filename = key[len(prefix):]

            # Skip directories
            if not filename or filename.endswith('/'):
                continue

            # Skip packages matching skip_package
            if skip_package and filename.startswith(skip_package + '-'):
                print(f"  Skipping: {filename}")
                skipped_count += 1
                continue

            # Download the file
            dest_path = os.path.join(destination, filename)
            print(f"  Downloading: {filename}")

            try:
                client.download_file(bucket, key, dest_path)
                downloaded_count += 1
            except Exception as e:
                print(f"  Error downloading {filename}: {e}", file=sys.stderr)

    # Summary
    print()
    print(f"Download complete: {downloaded_count} files downloaded")
    if skipped_count:
        print(f"Skipped: {skipped_count} files")


if __name__ == '__main__':
    main()
