# AGENTS.md

Machine-oriented contract for driving `hapd`. Human docs: [README.md](README.md).

`hapd` signs, installs and launches HarmonyOS HAP packages on a Linux host.
It is a thin, deterministic wrapper around Huawei's `hdc` and `hap-sign-tool.jar`.

## Invariants

1. **Never commit or exfiltrate signing material.** `*.p12`, `*.p7b`, `*.cer`,
   `*.csr` stay local. `.gitignore` blocks them; do not override it.
2. **Never pass secrets as arguments in CI.** Use `HAPD_P12_PWD`.
3. **Always run `hapd --json doctor` before a deploy.** It is the single source of
   truth for whether a deploy can succeed.
4. **Prefer `--dry-run` before any state-changing call** (`deploy`, `update`,
   `install`, `sign` to an existing path).
5. **Do not invent signing material.** If `doctor` reports missing material, stop
   and ask the human: obtaining it requires an interactive AppGallery Connect
   session that an agent cannot perform.

## Discovery

`hapd` is installed as an Environment Modules package. Load it before anything
else; the modulefile sets `PATH` and `HAPD_HOME` and sources the machine-local
overlay that carries the signing material.

```bash
module load hapd            # or: module load hapd/<version>
command -v hapd             # /path/to/hapd-repo/hapd
hapd --version
hapd --json doctor
```

If `hapd` is not found, the module is not loaded — do **not** fall back to
exporting variables into `.bashrc`. Report the missing module instead. A local
checkout can always be run directly: `/path/to/hapd-repo/hapd --json doctor`.

`doctor` JSON shape:

```json
{
  "hapd": "0.1.0",
  "ok": true,
  "checks": [
    {"name": "toolchain", "ok": true, "detail": "/home/u/opt/apps/harmonyos/26.0.0.865/command-line-tools"},
    {"name": "hdc", "ok": true, "detail": ".../toolchains/hdc"},
    {"name": "hap-sign-tool", "ok": true, "detail": ".../hap-sign-tool.jar"},
    {"name": "java", "ok": true, "detail": "/usr/bin/java"},
    {"name": "device", "ok": true, "detail": "192.168.1.63:32907(Connected)"},
    {"name": "signing material", "ok": true, "detail": "p12=my.p12 alias=my-key profile=my.p7b"},
    {"name": "profile valid", "ok": true, "detail": "bundle=com.example.app expires=2027-11-08 (364 days left)"},
    {"name": "device in profile", "ok": true, "detail": "udid=01EB73B36178DC16..."}
  ]
}
```

Gate on `ok` and on the individual `checks[].name`s you care about.

## Toolchain discovery order

`HAPD_TOOLCHAIN` → `COMMANDLINE_TOOL_DIR` → `~/opt/apps/harmonyos/command-line-tools`
→ `~/opt/apps/harmonyos/*/command-line-tools` (newest first) → `~/command-line-tools`.

## Signing-material resolution

Module overlay (`hapd.local.tcl`, sourced by the modulefile) → flag → env →
`./signing/` (or `./ednovas/signing/`), newest file per extension.

| Purpose | Flag | Env |
|---|---|---|
| keystore | `--p12` | `HAPD_P12` |
| certificate | `--cert` | `HAPD_CERT` |
| profile | `--profile` | `HAPD_PROFILE` |
| keystore password | `--password` | `HAPD_P12_PWD` |
| key alias | `--alias` | `HAPD_ALIAS` |
| material dir | `--signing-dir` | — |

## Recipes

Inspect before acting:

```bash
hapd --json info ./app-unsigned.hap
# {"path":...,"bundle_name":"com.example.app","version_name":"1.2.3",
#  "min_api":60002022,"target_api":60101024,"module_name":"entry",
#  "main_element":"EntryAbility","device_types":["phone"],
#  "permissions":["ohos.permission.INTERNET"],"abilities":["EntryAbility"],
#  "extension_abilities":[],"signed":false}
```

Sign only:

```bash
hapd sign ./app-unsigned.hap -o ./app-signed.hap
```

Sign + install + launch:

```bash
hapd --json deploy ./app-unsigned.hap
# {"out":"/abs/app-signed.hap","bundle":"com.example.app","profile":"/abs/my.p7b","dropped":[]}
```

Fetch a published build and deploy it:

```bash
hapd update https://example.com/app-1.2.3-unsigned.hap --dir ./dist
```

Install a pre-signed HAP without re-signing:

```bash
hapd install ./app-signed.hap
```

Re-target a HAP that was signed for someone else:

```bash
hapd sign ./thirdparty.hap -o ./mine.hap --rename-bundle com.example.mine --strip-unsupported
```

Wait: `--rename-bundle` **must** equal the profile's bundle name or `hapd` exits 2.
Read it from `hapd --json profiles`.

Launch and observe:

```bash
hapd run com.example.app --ability EntryAbility
hapd log --filter com.example.app      # streams hilog; long-running
```

## Exit codes

| Code | Meaning | Agent action |
|---|---|---|
| 0 | success | continue |
| 1 | `doctor` found problems | read `checks[]`, fix, re-run |
| 2 | input problem (bundle mismatch, missing file) | fix inputs; do not retry blindly |
| 3 | missing dependency (CLT, java, openssl, material) | ask the human |
| 4 | signing or verification failed | capture stderr, report |
| 5 | install rejected | `hapd explain <code>`, apply the fix |
| 6 | launch failed | usually `10106102` (screen locked) — ask the human to unlock |

## Failure playbook

| Symptom | Diagnosis | Action |
|---|---|---|
| `9568257 fail to verify pkcs7 file` | chain does not reach a trusted root (OpenHarmony community certs) | requires AGC debug material — human step |
| `9568322` | HAP bundle ≠ profile bundle | `--rename-bundle <profile bundle>` (get it from `hapd --json profiles`) |
| `9568289` | permission not granted by profile | add `--strip-unsupported` |
| `9568332` | same bundle installed with another signature | uninstall, then install |
| `9568266` | device UDID missing from profile | human must add device in AGC and download a new profile |
| `Unauthorized` from `devices` | phone did not accept the debug authorization | ask human to unlock and tap "always allow" |
| `verify certificate chain failed` | `.cer` was already leaf-first, or corrupted | re-download from AGC; `hapd` reorders automatically |

## Constraints and honesty rules

- An agent **cannot** create signing material: AppGallery Connect requires an
  interactive Huawei account session (login, possibly SMS/real-name verification).
  Say so instead of attempting workarounds.
- Do not try to bypass signature verification. It is not possible on commercial
  devices and inhibits the security model.
- `hapd log` never terminates on its own. Run it with a timeout or expect the
  caller to interrupt.
- Re-signing third-party apps may violate their licence. Surface that when asked.
