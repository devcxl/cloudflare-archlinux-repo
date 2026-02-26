#!/usr/bin/env python3
"""
Test script for package parsing functions in check_aur_updates.py
"""

import sys
import os

# Add the script directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_aur_updates import parse_package_filename, get_r2_versions
import boto3

def test_parse_package_filename():
    """Test the package filename parsing function"""
    test_cases = [
        "claude-code-2.1.59-1-x86_64.pkg.tar.zst",
        "localsend-bin-1.17.0-1-x86_64.pkg.tar.zst",
        "baidunetdisk-bin-4.17.7-1-x86_64.pkg.tar.zst",
        "dingtalk-bin-7.0.33.11433-1-x86_64.pkg.tar.zst",
        "hysteria-bin-1.3.5-1-x86_64.pkg.tar.zst"
    ]

    print("Testing package filename parsing:")
    print("-" * 50)

    for filename in test_cases:
        result = parse_package_filename(filename)
        if result:
            name, version, arch = result
            print(f"Filename: {filename}")
            print(f"  Name: {name}")
            print(f"  Version: {version}")
            print(f"  Arch: {arch}")
            print()
        else:
            print(f"Failed to parse: {filename}")
            print()

def test_get_r2_versions():
    """Test getting versions from R2 storage"""
    # Check if we have the necessary environment variables
    if not all(key in os.environ for key in ['AWS_S3_BUCKET', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_S3_ENDPOINT']):
        print("Warning: Missing R2 environment variables. Skipping R2 test.")
        print("Please set AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_S3_ENDPOINT")
        return

    try:
        client = boto3.client(
            's3',
            aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
            endpoint_url=os.environ['AWS_S3_ENDPOINT']
        )

        print("Testing R2 version retrieval:")
        print("-" * 50)

        r2_versions = get_r2_versions(client, os.environ['AWS_S3_BUCKET'])

        if r2_versions:
            print(f"Found {len(r2_versions)} packages in R2:")
            for name, version in sorted(r2_versions.items()):
                print(f"  {name}: {version}")
        else:
            print("No packages found in R2")

    except Exception as e:
        print(f"Error testing R2 version retrieval: {e}")

if __name__ == "__main__":
    print("Running tests for check_aur_updates.py")
    print("=" * 50)

    test_parse_package_filename()

    print("=" * 50)

    test_get_r2_versions()

    print("=" * 50)
    print("Tests completed")