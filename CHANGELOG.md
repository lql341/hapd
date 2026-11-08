# Changelog

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
