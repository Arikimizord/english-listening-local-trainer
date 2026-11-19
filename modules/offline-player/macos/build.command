#!/bin/bash
set -euo pipefail

src="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "请在 macOS 上构建。"
  exit 1
fi
if ! xcode-select -p >/dev/null 2>&1; then
  echo "构建需要 Xcode Command Line Tools。也可用 Safari 打开听力课堂.html。"
  exit 1
fi

output="${1:-$src/听力课堂.app}"
if [[ -e "$output" || -L "$output" ]]; then
  echo "目标已存在：$output。可传入另一个 .app 路径。"
  exit 1
fi
parent="$(cd "$(dirname "$output")" && pwd)"
output="$parent/$(basename "$output")"
stage="$(mktemp -d "$parent/.classroom-player.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
app="$stage/听力课堂.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/assets"

cp "$src/听力课堂.html" "$src/player.css" "$src/player.js" "$src/subtitles.js" "$app/Contents/Resources/"
cp "$src/assets/cats-frames.png" "$app/Contents/Resources/assets/"
cp "$src/Info.plist" "$app/Contents/"
xcrun --sdk macosx swiftc -O -parse-as-library -swift-version 5 -target arm64-apple-macosx14.0 \
  "$src/Player.swift" -o "$app/Contents/MacOS/CETClassroomPlayer"
plutil -lint "$app/Contents/Info.plist"
codesign --force --sign - "$app"
codesign --verify --strict "$app"
lipo -verify_arch arm64 "$app/Contents/MacOS/CETClassroomPlayer"
mv "$app" "$output"
echo "$output"
