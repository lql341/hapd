# Changelog

## 0.3.5 - 2026-11-08

- `install` reports what it is about to replace: `note: com.x is already installed
  (1.1.85 / 1010850); installing replaces it`. Installing a package whose bundle
  name collides with an unrelated app silently replaced it; that is how an
  EdNovas install was overwritten by a FlClash build between two runs.
- `installed_app()` returns versionName / versionCode / appIdentifier in one
  `bm dump` call.

## 0.3.4 - 2026-11-08

- **`--rename-bundle` is refused when the package's bytecode embeds its bundle
  name.** ArkTS compiled for API 12+ stores module records as
  `@bundle:<bundleName>/<module>/...` inside `ets/*.abc`. Rewriting `module.json`
  left those records stale, so the app installed and then died at launch:

  ```
  ArkCompiler: Cannot execute module buffer file .../entry/ets/entryability/EntryAbility.abc
  AppKit: Error type: ReferenceError
  AppKit: Cannot find module 'ets/entryability/EntryAbility', which is application EntryPoint
  AppKit: ... exit with code: 254
  ```

  `embedded_bundle_refs()` / `rename_blockers()` scan the `.abc` payloads; `sign`
  now exits 2 with the two real options (a profile for the original bundle name,
  or a rebuild). README/README_CN/AGENTS corrected — the previous text implied a
  zip-level rename works for any HAP.
- 41 tests.

## 0.3.3 - 2026-11-08

- **`--strip-unsupported` no longer strips normal-level permissions.** It compared
  every requested permission against the profile's `allowed-acls` /
  `restricted-permissions`, which only list *ACL* permissions - so a profile with
  no ACLs caused `INTERNET`, `CAMERA` and friends to be dropped, producing a
  signed-but-broken app. It now reads `PermissionDefinitions.json` from the
  toolchain and drops only `system_basic` / `system_core` permissions the profile
  does not grant. Unknown permissions are kept.
- `_default_out` keeps the input extension: an `.hsp` is no longer written as
  `-signed.hap`.
- `deploy --dry-run` honours `-o` and `--rename-bundle` and prints the resulting
  install/launch commands for the signed artefacts.
- 37 tests.

## 0.3.2 - 2026-11-08

- Fix `parse_version_code`: `bm dump -n` output contains a nested
  `applicationInfo` with `versionCode: 0` plus date-based dependency and
  `minCompatibleVersionCode` values. The previous "take the maximum" heuristic
  reported a dependency's code as the package's own, producing a bogus
  "version downgrade" warning. It now parses the JSON payload and reads the
  top-level `applicationInfo.versionCode`.
- 33 tests, including a fixture shaped like real `bm dump` output.

## 0.3.1 - 2026-11-08

- Add `9568263` (version downgrade) and `9568386` (bundle not installed) to the
  error table; `--replace` / `--auto-fix` now treat a downgrade like a signature
  conflict (uninstall, then retry).
- `install` preflight compares the installed `versionCode` with the package's and
  warns about an imminent `9568263` instead of failing blind.
- `installed_version()` / `parse_version_code()` are pure functions with tests.
- Consistent exit codes: expected failures raise `HapdError` (with `.code`)
  instead of `SystemExit`, so library use and tests can distinguish them.
- `devices`, `udid` and `connect` are real functions (they were lambdas), emit
  `--json`, and `connect` is no longer reported as failing for the harmless
  "Target is connected, repeat operation" response.
- `doctor` reports a missing or unparsable profile as a check instead of aborting.
- Declare the version once in `VERSION`; `install.sh` reads it, and tests assert
  `VERSION`, `hapd`, `CHANGELOG.md` and the modulefile template agree.
- 31 tests.

## 0.3.0 - 2026-11-08

- Shared packages (HSP) co-installation: `sign`/`install`/`deploy` accept several
  packages, detect `module.type == "shared"`, and install HSPs first with
  `hdc install -s`. `order_for_install()` is a pure, unit-tested function.
- `deploy --dry-run` prints the full plan (sign targets, HSP-before-HAP order,
  launch command) without touching a device and without signing material.
- Fix `--dry-run sign`: it no longer fails on the missing `sign-app success`
  line, and no longer reaches the device.
- Fix `AttributeError: args.name` in `sign_material` (broke every signing path).
- Reject non-zip inputs and HAPs without `module.json` with exit code 2 and a
  hint that `.app` archives must be unpacked first.
- 22 offline unit tests, plus an offline CLI suite driven by a stub toolchain.

## 0.2.0 - 2026-11-08

- Fix signature detection: look for the trailing PEM block instead of a
  `META-INF` entry (HAPs never contain `META-INF`, so `signed` was always false).
- `hapd uninstall`, `install --uninstall`, `install --replace`.
- `hapd keygen`: keystore + CSR in one step.
- `deploy`/`update` preflight: warn when the device UDID is absent from the
  profile or the profile has expired.
- `docs/command-line-tools.md`: the missing prerequisite — download, version to
  JDK matrix, unpack layout, module/PATH setup, verification, which ~6.9 GB of
  the 7 GB install is optional, and a login-free mirror fallback.
- READMEs restructured into Step 1 (tools) and Step 2 (signing material).
- `hapd renew`: compare replacement signing material with the current one and
  report whether an overwrite install keeps app data (public key comparison).
- `--auto-fix` for `deploy`/`update`: `9568332` triggers uninstall + retry,
  `9568289` triggers permission stripping, bounded by `--max-fix`.
- `hapd screenshot`, `hapd push`, `hapd pull`.
- `hapd info --verify` runs `verify-app`.
- Install failures print an actionable hint from the error table.
- First test suite (16 cases) and CI workflow.

## 0.1.0 - 2026-11-08

- First release: `doctor`, `devices`, `udid`, `connect`, `info`, `profiles`,
  `sign`, `install`, `run`, `log`, `deploy`, `update`, `explain`.
- Automatic certificate-chain reordering (AGC ships root-first, `hap-sign-tool`
  wants leaf-first).
- `--rename-bundle` to re-target a HAP at your own profile, and
  `--strip-unsupported` for `9568289`.
- `--json`, `--dry-run`, documented exit codes.
- Shipped as an Environment Modules package (`install.sh`,
  `modulefiles/hapd/<version>.in`, git-ignored `hapd.local.tcl` overlay).
