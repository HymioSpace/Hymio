// swift-tools-version: 5.10
import PackageDescription

let package = Package(
  name: "HymioCore",
  platforms: [.macOS(.v13)],
  products: [.library(name: "HymioCore", targets: ["HymioCore"])],
  targets: [
    .target(name: "HymioCore", path: "Hymio/Core"),
    .testTarget(name: "HymioCoreTests", dependencies: ["HymioCore"], path: "Tests"),
  ]
)
