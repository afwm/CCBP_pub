#!/bin/bash

# アイコンセットディレクトリの作成
mkdir -p assets/icons/app.iconset

# 元画像のパス（1024x1024のPNG）
if [ -f "@icon.png" ]; then
    ORIGINAL="@icon.png"
elif [ -f "assets/icons/icon_1024.png" ]; then
    ORIGINAL="assets/icons/icon_1024.png"
else
    echo "Error: Icon file not found!"
    echo "Please place the icon file as either '@icon.png' in the root directory"
    echo "or as 'icon_1024.png' in the assets/icons directory."
    exit 1
fi

# 必要なサイズの画像を生成
SIZES=("16" "32" "64" "128" "256" "512" "1024")
for size in "${SIZES[@]}"; do
    if [ "$size" == "1024" ]; then
        cp "$ORIGINAL" "assets/icons/app.iconset/icon_512x512@2x.png"
    elif [ "$size" == "64" ]; then
        sips -z $size $size "$ORIGINAL" --out "assets/icons/app.iconset/icon_32x32@2x.png"
    elif [ "$size" == "512" ]; then
        sips -z $size $size "$ORIGINAL" --out "assets/icons/app.iconset/icon_${size}x${size}.png"
        sips -z $((size*2)) $((size*2)) "$ORIGINAL" --out "assets/icons/app.iconset/icon_${size}x${size}@2x.png"
    else
        sips -z $size $size "$ORIGINAL" --out "assets/icons/app.iconset/icon_${size}x${size}.png"
        sips -z $((size*2)) $((size*2)) "$ORIGINAL" --out "assets/icons/app.iconset/icon_${size}x${size}@2x.png"
    fi
done

# icnsファイルの生成
cd assets/icons && iconutil -c icns app.iconset

echo "Icon created successfully at assets/icons/app.icns" 