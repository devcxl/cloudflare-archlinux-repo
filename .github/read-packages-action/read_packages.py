#!/usr/bin/env python3
"""
Read packages list from YAML file.

This script reads a YAML file containing a list of packages,
and sets GitHub Actions outputs for use in workflows.

Environment Variables Required:
    CONFIG_FILE: Path to packages YAML file
    GITHUB_OUTPUT: Path to GitHub Actions output file
"""

import json
import os
import sys

import yaml


def main():
    config_file = os.environ.get('CONFIG_FILE', '.github/packages.yml')
    github_output = os.environ.get('GITHUB_OUTPUT')

    if not os.path.exists(config_file):
        print(f"Error: Config file not found: {config_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading packages from: {config_file}")

    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)

    packages = data.get('packages', [])
    packages_str = ' '.join(packages)
    packages_json = json.dumps(packages)

    # Set outputs for GitHub Actions
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f'packages={packages_str}\n')
            f.write(f'packages-json={packages_json}\n')

    print(f"Read {len(packages)} packages")
    print(f"Packages: {packages_str}")
    print(f"Packages JSON: {packages_json}")


if __name__ == '__main__':
    main()
