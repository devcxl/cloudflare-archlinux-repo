#!/usr/bin/env python3
"""Upload repository files to Cloudflare R2 bucket root."""

import mimetypes
import os
import sys
import time

import boto3


def iter_upload_files(source_dir):
    """Yield (local_path, key) for files under source_dir, following symlinks."""
    for root, _, files in os.walk(source_dir):
        for filename in sorted(files):
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, source_dir)
            if os.path.islink(local_path):
                yield os.path.realpath(local_path), relative_path
            else:
                yield local_path, relative_path


def main():
    bucket = os.environ.get('AWS_S3_BUCKET')
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('AWS_S3_ENDPOINT')
    source_dir = os.environ.get('SOURCE_DIR', './repo')

    if not all([bucket, access_key_id, secret_access_key, endpoint]):
        print('Error: Missing required environment variables.', file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(source_dir):
        print(f'Error: Source directory not found: {source_dir}', file=sys.stderr)
        sys.exit(1)

    client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint,
    )

    uploaded = 0
    for local_path, key in iter_upload_files(source_dir):
        content_type = mimetypes.guess_type(key)[0] or 'application/octet-stream'
        for attempt in range(3):
            try:
                client.upload_file(
                    local_path,
                    bucket,
                    key,
                    ExtraArgs={'ContentType': content_type},
                )
                uploaded += 1
                print(f'Uploaded: {key}')
                break
            except Exception as exc:
                print(
                    f'Error uploading {key} (attempt {attempt + 1}): {exc}',
                    file=sys.stderr,
                )
                if attempt == 2:
                    sys.exit(1)
                time.sleep(2)

    print(f'Upload complete: {uploaded} files')


if __name__ == '__main__':
    main()
