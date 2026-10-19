#!/bin/bash
set -euo pipefail
IOS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IOS_BUILD="${HYMIO_IOS_BUILD_DIR:-/tmp/HymioIOSBuild}"
IOS_DEVICE="${1:-}"
if [ -z "$IOS_DEVICE" ]; then
  IOS_DEVICE="$(xcrun simctl list devices available -j | python3 -c 'import json,sys; ds=[d for k,v in json.load(sys.stdin)["devices"].items() if "iOS" in k for d in v if "iPhone" in d["name"]]; print(next((d["udid"] for d in ds if d["state"]=="Booted"),ds[0]["udid"]))')"
fi
xcrun simctl boot "$IOS_DEVICE" 2>/dev/null || true
xcrun simctl bootstatus "$IOS_DEVICE" -b
xcodebuild -project "$IOS_ROOT/Hymio.xcodeproj" -scheme Hymio -configuration Debug -destination "platform=iOS Simulator,id=$IOS_DEVICE" -derivedDataPath "$IOS_BUILD" CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- build
xcrun simctl install "$IOS_DEVICE" "$IOS_BUILD/Build/Products/Debug-iphonesimulator/Hymio.app"
IOS_BUNDLE="$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$IOS_BUILD/Build/Products/Debug-iphonesimulator/Hymio.app/Info.plist")"
xcrun simctl launch "$IOS_DEVICE" "$IOS_BUNDLE"
open -a Simulator
