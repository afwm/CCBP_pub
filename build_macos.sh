#!/bin/bash

# macOS Nuitka Build Script for CCBP

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Step 1: Creating App Icon ---"
# Ensure the icon script exists and run it
if [ -f "create_icns.sh" ]; then
  bash create_icns.sh
else
  echo "Warning: create_icns.sh not found. Skipping icon creation."
  # Consider exiting if icon is mandatory: exit 1
fi
echo "--- Icon creation finished (or skipped). ---"
echo ""

echo "--- Step 2: Checking Required Environment Variables ---"
# Check for required environment variables
# These might be needed by the application runtime if not using config.json,
# or by other potential build steps not included here.
# If they are ONLY used by scripts/prepare_build.py (which is not used here),
# these checks might be removable.
if [ -z "$LICENSE_SECRET_KEY" ]; then
  echo "Error: Environment variable LICENSE_SECRET_KEY might be required."
  echo "Please ensure it is set if needed by the application or build process:"
  echo "export LICENSE_SECRET_KEY=\"your_secret_key\""
  # Decide if this is a fatal error: exit 1
fi

if [ -z "$LICENSE_API_URL" ]; then
  echo "Error: Environment variable LICENSE_API_URL might be required."
  echo "Please ensure it is set if needed by the application or build process:"
  echo "export LICENSE_API_URL=\"your_api_url\""
  # Decide if this is a fatal error: exit 1
fi

echo "--- Environment variable check finished. Proceeding with build. ---"
echo ""

echo "--- Step 3: Running Nuitka Build ---"
python -m nuitka main.py \
  --standalone \
  --enable-plugin=pyside6 \
  --macos-create-app-bundle \
  --macos-app-icon=assets/icons/app.icns \
  --macos-app-name="CCBP" \
  --output-dir=nuitka_dist_macos \
  --include-data-file=assets/ffmpeg/mac/ffmpeg=assets/ffmpeg/mac/ffmpeg \
  --include-data-file=assets/ffmpeg/mac/ffprobe=assets/ffmpeg/mac/ffprobe \
  --include-data-file=ccbp/config/path_mapping_rules.json=ccbp/config/path_mapping_rules.json \
  --include-data-dir=ccbp/resources=ccbp/resources \
  --macos-app-protected-resource="NSCameraUsageDescription:カメラアクセスが必要です（もしクロップ機能でカメラを使う場合）" \
  --macos-app-protected-resource="NSMicrophoneUsageDescription:マイクアクセスが必要です（もし音声関連機能で使う場合）" \
  --macos-app-protected-resource="NSPhotoLibraryUsageDescription:フォトライブラリへのアクセス許可（もし画像選択で使う場合）" \
  --macos-app-protected-resource="NSDownloadsFolderUsageDescription:ダウンロードフォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）" \
  --macos-app-protected-resource="NSDocumentsFolderUsageDescription:書類フォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）" \
  --macos-app-protected-resource="NSDesktopFolderUsageDescription:デスクトップフォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）"

echo "-------------------------------------\"
echo "Nuitka build finished successfully!"
echo "Output directory: nuitka_dist_macos"
echo "-------------------------------------\"

# Optional: open nuitka_dist_macos/main.app 