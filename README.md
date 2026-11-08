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

### Step 1 — install the Command Line Tools (the only awkward part)

`hapd` is a thin wrapper; `hdc` and `hap-sign-tool.jar` come from Huawei's
**Command Line Tools**. They are not packaged for any distro, so install them by
hand, once:

```bash
# 1. download commandline-tools-linux-x64-<version>.zip  (~2.3 GB)
#    https://developer.huawei.com/consumer/cn/download/  -> "Command Line Tools" -> Linux-x64
#    (a free Huawei developer account is required)
# 2. unpack into a versioned directory
mkdir -p ~/opt/apps/harmonyos
unzip commandline-tools-linux-x64-<version>.zip -d ~/opt/apps/harmonyos/<version>
# 3. install the one dependency it needs
sudo apt install unzip openssl openjdk-21-jdk-headless
# 4. check
~/opt/apps/harmonyos/<version>/command-line-tools/sdk/default/openharmony/toolchains/hdc -v
```

Match the version to your device: **CLT 26.0.0.x ↔ HarmonyOS 7.0 / API 26 /
JDK 21**, CLT 5.x ↔ HarmonyOS 5.x / JDK 17. `hapd` auto-discovers
`~/opt/apps/harmonyos/*/command-line-tools` (newest first); override with
`HAPD_TOOLCHAIN` or `COMMANDLINE_TOOL_DIR`.

**Full guide — download, JDK matrix, PATH/module setup, shrinking the 7 GB
install to 108 MB, and a login-free mirror fallback:
[docs/command-line-tools.md](docs/command-line-tools.md).**

### Step 2 — get signing material (once)

A HAP must be signed with a certificate the device trusts. Community/OpenHarmony
certificates are **rejected by commercial HarmonyOS devices** (`9568257`), so you
need AppGallery Connect material:

1. `HAPD_P12_PWD='<pw>' hapd keygen --name my-key -o signing`
   (creates `signing/my-key.p12` and `signing/my-key.csr`; plain `keytool` works too)
2. In AGC: register the bundle name (APP ID) → upload `my-key.csr` to get a
   **debug certificate** `.cer` → register the device UDID → create a **debug
   profile** `.p7b` bound to that certificate and device.
3. Put `*.cer` and `*.p7b` next to the `.p12` in `./signing/`.

Full walkthrough with screenshots-level detail: [docs/harmonyos-signing.md](docs/harmonyos-signing.md).

## Install

`hapd` ships as an [Environment Modules](https://modules.readthedocs.io/) package,
which keeps it out of your shell rc files and lets you pin or roll back versions.

```bash
git clone https://github.com/lql341/hapd.git ~/work/hapd
cd ~/work/hapd
./install.sh                       # -> $MODULEFILES_DIR/hapd/<version>
module load hapd
hapd --version
```

`install.sh` options:

| Option | Effect |
|---|---|
| `--module-dir DIR` | Write the modulefile to `DIR/hapd/<version>` (default `$MODULEFILES_DIR` or `~/opt/modulefiles`) |
| `--no-link` | Skip the convenience symlink in `~/.local/bin` |

If your `MODULEPATH` does not include the module directory yet, add it once in your
module init file (`module use ~/opt/modulefiles`) — **do not** export hapd's
variables from `.bashrc`.

No module system? A symlink is enough:

```bash
ln -s "$PWD/hapd" ~/.local/bin/hapd
```

### Signing material via the module overlay

`install.sh` creates `hapd.local.tcl` next to the script (git-ignored). The
generated modulefile sources it on `module load`, so keys never touch your shell
rc and never enter the repository:

```tcl
# hapd.local.tcl
setenv HAPD_P12      /path/to/my-key.p12
setenv HAPD_CERT     /path/to/my-debug.cer
setenv HAPD_PROFILE  /path/to/my-debug.p7b
setenv HAPD_P12_PWD  <keystore password>
setenv HAPD_ALIAS    my-key
```

After that, `hapd doctor` and `hapd deploy` need no arguments or environment setup.


## Quick start

```bash
module load hapd

# 1. Is everything in place?
hapd doctor

# 2. Connect the phone (wireless debugging shows "ip:port")
hapd connect 192.168.1.63:32907
hapd udid                    # paste this into AGC when registering the device

# 3. Sign + install + launch
hapd deploy app-unsigned.hap

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
| `hapd install <hap>` | Install (add `--sign` to sign first, `--uninstall` to replace, `--replace` to recover from `9568332`). |
| `hapd uninstall <bundle>` | Remove a bundle (`--hap` reads the name from a package). |
| `hapd keygen` | Create a `.p12` + `.csr` for AppGallery Connect. |
| `hapd renew` | Compare new signing material with the current one before the certificate expires. |
| `hapd screenshot` | Grab a device screenshot (`-o file`). |
| `hapd push` / `hapd pull` | Move files to and from the device. |
| `hapd run <bundle>` | Start an ability (`--hap` reads `mainElement` from the package). |
| `hapd log [--filter X]` | Stream `hilog`. |
| `hapd deploy <hap>` | sign → install → run (`--auto-fix` retries on `9568332` / `9568289`). |
| `hapd update <url\|path>` | Download a build, then deploy. |
| `hapd explain <code>` | Decode a device error code. |

Global flags: `--json`, `--dry-run`, `--version`.

### Signing material resolution

Module overlay → explicit flag → environment → `./signing/` (newest file wins):

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
