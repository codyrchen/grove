#!/bin/sh
# Zip the extension for the Chrome Web Store: sh extension/build.sh
set -e
cd "$(dirname "$0")"
if grep -q '127.0.0.1' config.js; then
  echo "config.js still points at 127.0.0.1. Set GROVE_URL to the live site first." >&2
  exit 1
fi
version=$(sed -n 's/.*"version": "\(.*\)".*/\1/p' manifest.json)
rm -f "../grove-extension-$version.zip"
zip -qr "../grove-extension-$version.zip" manifest.json config.js newtab.html newtab.css newtab.js icons
echo "Built grove-extension-$version.zip"
