#!/bin/bash

# macOS Nuitka Build Script for CCBP

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Step 0: Loading .env if exists ---"
if [ -f .env ]; then
  set -a
  source .env
  set +a
  echo ".env loaded."
else
  echo "Error: .env file not found. 必要な環境変数を .env に記載してください。"
  exit 1
fi
echo ""

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
if [ -z "$LICENSE_API_URL" ]; then
  echo "Error: LICENSE_API_URL is not set."
  exit 1
fi
if [ -z "$LICENSE_FERNET_KEY" ]; then
  echo "Error: LICENSE_FERNET_KEY is not set."
  exit 1
fi
echo "--- Environment variable check finished. ---"
echo ""

echo "--- Step 3: Generating config.json ---"
cat <<EOF > config.json
{
  "working_directory": "",
  "license_key": "",
  "license.status": null,
  "license.expires": null,
  "license.validated_at": null,
  "license.last_message": "未確認",
  "batch/csv_file": "",
  "batch/template_dir": "",
  "batch/template_material_dir": "",
  "batch/replace_material_dir": "",
  "batch/output_dir": "",
  "batch/output_csv_dir": "",
  "crop_input_dir": "",
  "crop_output_dir": "",
  "license/api_url": "${LICENSE_API_URL}",
  "license/fernet_key": "${LICENSE_FERNET_KEY}",
  "internal/fernet_key": ""
}
EOF
echo "config.json generated:"
cat config.json
echo ""

echo "--- Step 4: Running Nuitka Build ---"
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
  --include-data-file=config.json=config.json \
  --macos-app-protected-resource="NSCameraUsageDescription:カメラアクセスが必要です（もしクロップ機能でカメラを使う場合）" \
  --macos-app-protected-resource="NSMicrophoneUsageDescription:マイクアクセスが必要です（もし音声関連機能で使う場合）" \
  --macos-app-protected-resource="NSPhotoLibraryUsageDescription:フォトライブラリへのアクセス許可（もし画像選択で使う場合）" \
  --macos-app-protected-resource="NSDownloadsFolderUsageDescription:ダウンロードフォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）" \
  --macos-app-protected-resource="NSDocumentsFolderUsageDescription:書類フォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）" \
  --macos-app-protected-resource="NSDesktopFolderUsageDescription:デスクトップフォルダへのアクセス許可（もしファイルの保存/読み込みで使う場合）"

echo "-------------------------------------"
echo "Nuitka build finished successfully!"
echo "Output directory: nuitka_dist_macos"
echo "-------------------------------------"

# Optional: open nuitka_dist_macos/main.app 