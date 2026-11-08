# hapd

**Sign, install and debug HarmonyOS HAP packages from Linux — no DevEco Studio, no Windows, no macOS.**

`hapd` is a single-file, dependency-free Python CLI that wraps the official
HarmonyOS Command Line Tools (`hdc` + `hap-sign-tool`) into one non-interactive
interface. It exists because Huawei ships no DevEco Studio for Linux, and driving
`hdc` / `hap-sign-tool` by hand is a minefield of certificate-chain ordering,
profile/bundle matching and opaque error codes.

> 中文文档: [README.zh-CN.md](README.zh-CN.md)
> Deeper background on how HarmonyOS signing actually works: [docs/harmonyos-signing.md](docs/harmonyos-signing.md)

---

## Features

- **One-command deploy** — `hapd deploy app.hap` signs, installs and launches.
- **Any HAP, not just yours** — `--rename-bundle` rewrites `app.bundleName` inside
  the package so a downloaded HAP can be signed with *your* profile.
- **Permission fixing** — `--strip-unsupported` drops permissions the profile does
  not grant, which is the cure for install error `9568289`.
- **Automatic certificate-chain repair** — AppGallery Connect ships the chain
  root-first; `hap-sign-tool` wants leaf-first. Handled transparently.
- **Preflight checks** — `hapd doctor` verifies toolchain, Java, signing material,
  profile expiry, and whether the connected device's UDID is in the profile.
- **Agent friendly** — every command accepts `--json`, `--dry-run`, and returns
  documented exit codes. No prompts, no colours, no TTY assumptions.
- **Error-code translation** — `hapd explain 9568257` tells you what happened.

## Prerequisites

| Requirement | Notes |
|---|---|
| Linux x86_64 | glibc ≥ 2.28 (Debian 11+, Ubuntu 20.04+) |
| **HarmonyOS Command Line Tools** | The only non-obvious download. Brings `hdc`, `hap-sign-tool.jar`, and the SDK. Requires a (free) Huawei developer account. |
| JDK 17 or 21 | CLT 26.x recommends JDK 21; older releases want 17. Used only to run `hap-sign-tool.jar`. |
| Python 3.8+ | Standard library only. |
| `openssl`, `keytool` | For certificate-chain ordering and keystore inspection. |
| Huawei developer account | Free. Needed once, to obtain a **debug certificate** and a **debug profile** from AppGallery Connect. |
| HarmonyOS device | With *Developer options → Wireless debugging* (or USB). |

### Getting the Command Line Tools

Download **Command Line Tools → Linux-x64** from
<https://developer.huawei.com/consumer/cn/download/> (sign-in required):

```bash
unzip commandline-tools-linux-x64-<version>.zip -d ~/opt/apps/harmonyos/<version>
# => ~/opt/apps/harmonyos/<version>/command-line-tools
```

`hapd` auto-discovers `~/opt/apps/harmonyos/*/command-line-tools` (newest first).
Override with `HAPD_TOOLCHAIN` or `COMMANDLINE_TOOL_DIR`.

### Getting signing material (once)

A HAP must be signed with a certificate the device trusts. Community/OpenHarmony
certificates are **rejected by commercial HarmonyOS devices** (`9568257`), so you
need AppGallery Connect material:

1. `keytool -genkeypair -alias my-key -keyalg EC -groupname secp256r1 \
   -sigalg SHA256withECDSA -keystore my.p12 -storetype pkcs12 -validity 9125 \
   -storepass '<pw>' -keypass '<pw>' -dname "C=CN,O=Me,OU=Dev,CN=my-key"`
2. `keytool -certreq -alias my-key -keystore my.p12 -storetype pkcs12 -file my.csr -storepass '<pw>'`
3. In AGC: register the bundle name (APP ID) → upload `my.csr` to get a **debug
   certificate** `.cer` → register the device UDID → create a **debug profile**
   `.p7b` bound to that certificate and device.
4. Put `my.p12`, `*.cer`, `*.p7b` in `./signing/`.

Full walkthrough with screenshots-level detail: [docs/harmonyos-signing.md](docs/harmonyos-signing.md).

## Install

```bash
git clone https://github.com/<you>/hapd.git
ln -s "$PWD/hapd/hapd" ~/.local/bin/hapd     # or copy the file anywhere on PATH
hapd --version
```

## Quick start

```bash
# 1. Is everything in place?
HAPD_P12_PWD='<keystore password>' hapd doctor

# 2. Connect the phone (wireless debugging shows "ip:port")
hapd connect 192.168.1.63:32907
hapd udid                    # paste this into AGC when registering the device

# 3. Sign + install + launch
HAPD_P12_PWD='<pw>' hapd deploy app-unsigned.hap

# 4. Follow logs
hapd log --filter myapp
```

## Commands

| Command | Purpose |
|---|---|
| `hapd doctor` | Check toolchain, Java, signing material, profile validity, device/UDID match. |
| `hapd devices` | List connected devices. |
| `hapd connect <ip:port>` | Wireless connect (`hdc tconn`). |
| `hapd udid` | Print the device UDID (needed for AGC). |
| `hapd info <hap>` | Inspect bundle name, version, API levels, permissions, abilities. |
| `hapd profiles` | List local profiles: bundle name, expiry, device count. |
| `hapd sign <hap>` | Sign only. |
| `hapd install <hap>` | Install (add `--sign` to sign first). |
| `hapd run <bundle>` | Start an ability (`--hap` reads `mainElement` from the package). |
| `hapd log [--filter X]` | Stream `hilog`. |
| `hapd deploy <hap>` | sign → install → run. |
| `hapd update <url\|path>` | Download a build, then deploy. |
| `hapd explain <code>` | Decode a device error code. |

Global flags: `--json`, `--dry-run`, `--version`.

### Signing material resolution

Explicit flag → environment → `./signing/` (newest file wins):

| Value | Flag | Env |
|---|---|---|
| Keystore | `--p12` | `HAPD_P12` |
| Certificate | `--cert` | `HAPD_CERT` |
| Profile | `--profile` | `HAPD_PROFILE` |
| Keystore password | `--password` | `HAPD_P12_PWD` |
| Key alias | `--alias` | `HAPD_ALIAS` |
| Material directory | `--signing-dir` | — |

## Signing a HAP that is not yours

Downloaded HAPs are usually signed for someone else's profile, or unsigned.
`hapd` can re-target them:

```bash
# profile says com.example.mine, HAP says com.someone.else
hapd sign downloaded.hap -o mine.hap --rename-bundle com.example.mine

# install fails with 9568289 → drop whatever the profile does not allow
hapd sign downloaded.hap -o mine.hap --rename-bundle com.example.mine --strip-unsupported
```

`--rename-bundle` rewrites `module.json` (and `pack.info`) inside the ZIP, then
re-signs. It refuses to target a name that differs from the profile's bundle name,
because the device would reject the result anyway.

> Respect the licence of the app you are re-signing. This feature exists for
> installing your own builds and for apps that permit it.

## Using it from an agent

`hapd` is designed to be driven by an LLM agent or a CI job. See
[AGENTS.md](AGENTS.md) for the full contract. In short:

```bash
export HAPD_P12_PWD=...      # never pass secrets on the command line in CI
hapd --json doctor           # -> {"ok": true, "checks": [...]}
hapd --json info app.hap     # -> bundle_name, version, permissions ...
hapd --dry-run deploy app.hap
hapd --json deploy app.hap   # -> {"out": ..., "bundle": ...}
```

Exit codes: `0` success, `1` doctor found problems, `2` usage/problem with the
inputs, `3` missing dependency, `4` signing or verification failed,
`5` install failed, `6` launch failed.

## Troubleshooting

| Error | Meaning | Fix |
|---|---|---|
| `9568257` fail to verify pkcs7 file | Chain does not lead to a trusted root (usually OpenHarmony community certs) | Sign with AGC debug material |
| `9568322` | HAP bundle name ≠ profile bundle name | `--rename-bundle` or create a matching profile |
| `9568289` | A requested permission is not granted by the profile | `--strip-unsupported` |
| `9568332` | Same bundle installed with a different signature | `hapd install --uninstall` / uninstall first |
| `9568266` | Device UDID not in the profile | Add it in AGC, download a new profile, re-sign |
| `10106102` | `aa start` refused while the screen is locked | Unlock the phone |
| `verify certificate chain failed` | `.cer` is root-first | Handled automatically; make sure you did not strip it |
| `hdc` device shows `Unauthorized` | Authorization dialog not accepted | Unlock the phone, accept "always allow", `hdc kill` then reconnect |

## Security

Never commit `*.p12`, `*.p7b`, `*.cer` or `*.csr` — `.gitignore` covers them.
The keystore password is best supplied via `HAPD_P12_PWD`, not `--password`
(avoids shell history).

## License

MIT. See [LICENSE](LICENSE).
