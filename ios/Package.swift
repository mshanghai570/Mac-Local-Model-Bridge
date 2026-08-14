// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MacLocalModelBridge",
    platforms: [
        .iOS(.v16),
        .macOS(.v13)
    ],
    products: [
        .library(
            name: "MacLocalModelBridge",
            targets: ["MacLocalModelBridge"]),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "MacLocalModelBridge",
            dependencies: [],
            path: "MacLocalModelBridge"
        ),
        .testTarget(
            name: "MacLocalModelBridgeTests",
            dependencies: ["MacLocalModelBridge"],
            path: "MacLocalModelBridgeTests"
        ),
    ]
)
