#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/MacLocalModelBridge.xcodeproj"
SCHEME="MacLocalModelBridge"
CONFIGURATION="Release"
SDK="iphoneos"
BUILD_DIR="$PROJECT_DIR/build"
DERIVED_DATA="$PROJECT_DIR/DerivedData"
IPA_PATH="$PROJECT_DIR/MacLocalModelBridge-unsigned.ipa"

echo "🧹 Cleaning previous build artifacts..."
rm -rf "$BUILD_DIR" "$DERIVED_DATA"

echo "🔨 Building $SCHEME ($CONFIGURATION) for $SDK..."
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -sdk "$SDK" \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$DERIVED_DATA" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  clean build

echo "📦 Packaging unsigned IPA..."
APP_PATH=$(find "$DERIVED_DATA" -name "MacLocalModelBridge.app" -path "*/Build/Products/*" | head -n 1)

if [ -z "$APP_PATH" ]; then
  echo "❌ Could not find built app. Check build output above."
  exit 1
fi

mkdir -p Payload
cp -R "$APP_PATH" Payload/

echo "🗜  Creating $IPA_PATH..."
zip -r -y "$IPA_PATH" Payload

rm -rf Payload

echo "✅ Unsigned IPA created at: $IPA_PATH"
echo "ℹ️  To sideload to a physical iPhone, use AltStore, Sideloadly, or a similar tool."
echo "   The sideloading tool will re-sign the app with your free provisioning profile."
