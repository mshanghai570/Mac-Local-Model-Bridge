#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/MacLocalModelBridge.xcodeproj"
SCHEME="MacLocalModelBridge"
CONFIGURATION="Release"
SDK="iphoneos"
DERIVED_DATA="$PROJECT_DIR/DerivedData"
IPA_PATH="$PROJECT_DIR/MacLocalModelBridge-unsigned.ipa"
BUNDLE_ID="com.localai.MacLocalModelBridge"
APP_NAME="MacLocalModelBridge"

echo "🧹 Cleaning previous build artifacts..."
rm -rf "$DERIVED_DATA"
rm -f "$IPA_PATH"
rm -rf "$PROJECT_DIR/Payload"

# Target-based device build. Does not require scheme/destination resolution,
# so it works even when Xcode has no matching iOS platform installed for
# scheme-based builds.
#
# NOTE: actool requires an installed iOS *simulator* runtime whenever the
# target supports iphonesimulator. If none is available, we retry once with
# Assets.xcassets excluded (app works fine, just no home-screen icon).
build_app() {
  local exclude_flag="$1"
  rm -rf "$DERIVED_DATA"
  xcodebuild \
    -project "$PROJECT" \
    -target "$APP_NAME" \
    -configuration "$CONFIGURATION" \
    -sdk "$SDK" \
    -arch arm64 \
    ONLY_ACTIVE_ARCH=YES \
    $exclude_flag \
    CODE_SIGN_STYLE=Manual \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY="" \
    SYMROOT="$DERIVED_DATA/Build/Products" \
    OBJROOT="$DERIVED_DATA/Build/Intermediates.noindex" \
    build
}

echo "🔨 Building $APP_NAME ($CONFIGURATION) for $SDK..."
if ! build_app "" 2>&1; then
  echo "⚠️  Build failed (likely no iOS simulator runtime installed for actool)."
  echo "    Retrying without Assets.xcassets..."
  build_app 'EXCLUDED_SOURCE_FILE_NAMES=Assets.xcassets'
fi

echo "📦 Packaging unsigned IPA..."
APP_PATH=$(find "$DERIVED_DATA" -name "$APP_NAME.app" -type d | head -n 1)

if [ -z "$APP_PATH" ]; then
  echo "❌ Could not find built app in $DERIVED_DATA. Check build output above."
  exit 1
fi

echo "🔍 Verifying architecture..."
BINARY_PATH="$APP_PATH/$APP_NAME"
if ! file "$BINARY_PATH" | grep -q "arm64"; then
  echo "❌ Error: Built binary is not arm64. Sideloading will fail."
  file "$BINARY_PATH"
  exit 1
fi

cd "$PROJECT_DIR"
mkdir -p Payload
cp -R "$APP_PATH" Payload/

cat > Payload/iTunesMetadata.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>ApplicationBundleID</key>
    <string>$BUNDLE_ID</string>
    <key>ApplicationVersion</key>
    <string>1.0.0</string>
    <key>ReleaseType</key>
    <string>Beta</string>
    <key>SoftwareVariant</key>
    <string>iOS</string>
</dict>
</plist>
PLIST

echo "🗜  Creating $IPA_PATH..."
zip -r -y "$IPA_PATH" Payload

rm -rf Payload

echo "✅ Unsigned IPA created at: $IPA_PATH"
