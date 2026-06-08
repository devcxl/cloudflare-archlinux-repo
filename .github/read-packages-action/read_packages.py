#!/usr/bin/env python3
"""
Read packages list from YAML file.

This script reads a YAML file containing a list of packages,
and sets GitHub Actions outputs for use in workflows.

Package entries can be:
  - Plain string (backward compat): treated as AUR package
  - Dict with 'name' and 'url' keys

Environment Variables Required:
    CONFIG_FILE: Path to packages YAML file
    GITHUB_OUTPUT: Path to GitHub Actions output file
"""

import json
import os
import sys

import yaml


def normalize_package(entry):
    """Normalize package entry to {name, url} dict format."""
    if isinstance(entry, str):
        return {'name': entry, 'url': f'https://aur.archlinux.org/{entry}.git'}
    if isinstance(entry, dict):
        if 'name' not in entry:
            raise ValueError(f"Package entry missing 'name': {entry}")
        if 'url' not in entry:
            raise ValueError(f"Package entry missing 'url': {entry}")
        return {'name': entry['name'], 'url': entry['url']}
    raise ValueError(f"Invalid package entry type: {type(entry)}")


def main():
    config_file = os.environ.get('CONFIG_FILE', '.github/packages.yml')
    github_output = os.environ.get('GITHUB_OUTPUT')

    if not os.path.exists(config_file):
        print(f"Error: Config file not found: {config_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading packages from: {config_file}")

    with open(config_file, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse YAML config: {e}", file=sys.stderr)
            sys.exit(1)

    raw_packages = data.get('packages', [])
    packages = [normalize_package(p) for p in raw_packages]

    packages_names_str = ' '.join(p['name'] for p in packages)
    packages_json = json.dumps(packages)

    if github_output:
        with open(github_output, 'a') as f:
            f.write(f'packages={packages_names_str}\n')
            f.write(f'packages-json={packages_json}\n')

    print(f"Read {len(packages)} packages")
    print(f"Packages: {packages_names_str}")


if __name__ == '__main__':
    main()
