# Optional iOS Signing for CI

The repository’s `iOS and Backend CI` workflow intentionally validates the application with an **unsigned simulator build** and an **unsigned device `.xcarchive`**. The existing Xcode target has no development team, provisioning profile, or signing identity configured, and this repository contains no signing secrets. Consequently, the current workflow cannot and does not create an installable IPA.

> The current artifact proves compilation and archive creation; it is not suitable for installation on an iPhone.

## Stage A: Current, Credential-Free Validation

The workflow runs the shared `MacLocalModelBridge` scheme against the iOS Simulator with signing disabled, then archives the `Release` configuration for the generic iOS device destination. It uploads an unsigned `MacLocalModelBridge.xcarchive` and Xcode diagnostics, both with a 14-day retention period.

## Stage B: Required Inputs for a Signed IPA

Before adding a separate manually triggered export workflow, create the following **GitHub Actions secrets**. Do not add the source files, decoded values, certificate password, provisioning profile, private key, or Apple credentials to the repository. GitHub documents this temporary-keychain approach for macOS runners.[1]

| Secret | Required value | Purpose |
|---|---|---|
| `BUILD_CERTIFICATE_BASE64` | Base64 encoding of the Apple Distribution `.p12` file. | Imports the certificate and its private key into a temporary runner keychain. |
| `P12_PASSWORD` | Password used to export the `.p12`. | Unlocks the imported signing identity. |
| `BUILD_PROVISION_PROFILE_BASE64` | Base64 encoding of the matching iOS Distribution `.mobileprovision` profile. | Enables the `com.localai.MacLocalModelBridge` bundle identifier to be signed for its intended distribution method. |
| `KEYCHAIN_PASSWORD` | A randomly generated, CI-only password. | Protects the temporary runner keychain for the job lifetime. |

The provisioning profile must match the app bundle identifier **`com.localai.MacLocalModelBridge`**, the selected distribution method, and the same Apple team as the distribution certificate. Create an `ExportOptions.plist` appropriate to the chosen method (`app-store`, `ad-hoc`, `development`, or `enterprise`), including that team identifier and the installed profile mapping. Keep it as a reviewed configuration file without credentials, or generate it from non-secret repository variables; do not guess the team ID or profile name.

## Secure Export Workflow Shape

A later manual signing workflow should perform these ordered steps: decode the two Base64 secrets to `$RUNNER_TEMP`; create and unlock a temporary keychain; import the `.p12`; install the `.mobileprovision` under `~/Library/MobileDevice/Provisioning Profiles`; archive with signing enabled; run `xcodebuild -exportArchive` with the reviewed `ExportOptions.plist`; and upload the resulting `.ipa`. The signing material should exist only on the ephemeral GitHub-hosted runner. GitHub notes that those VMs are destroyed after the job, unlike self-hosted runners that require explicit cleanup.[1]

Do not enable this stage until the responsible Apple developer has supplied these inputs and has confirmed the intended distribution method. The unsigned CI pipeline remains the correct default for compilation validation.

## References

[1]: https://docs.github.com/actions/use-cases-and-examples/deploying/installing-an-apple-certificate-on-macos-runners-for-xcode-development "GitHub Docs: Installing an Apple certificate on macOS runners for Xcode development"
