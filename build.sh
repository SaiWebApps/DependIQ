#!/usr/bin/env bash
# Build script for Render deployment

set -o errexit  # Exit on error

echo "Starting DependIQ build process..."

pip install --upgrade pip
pip install .

echo "Build completed successfully!"
