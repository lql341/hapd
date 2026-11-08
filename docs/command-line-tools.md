# Installing the HarmonyOS Command Line Tools on Linux

`hapd` itself is a 31 KB Python script — everything that actually touches a HAP
comes from Huawei's **Command Line Tools (CLT)**. This document covers getting
them onto a Linux machine, which is the only genuinely awkward step.

`hapd` needs exactly two files from the package:

```
command-line-tools/sdk/default/openharmony/toolchains/hdc                     # device bridge
command-line-tools/sdk/default/openharmony/toolchains/lib/hap-sign-tool.jar   # signing
```

## Version matching

| HarmonyOS device | API | CLT version | JDK |
|---|---|---|---|
| 7.0 | 26 | `26.0.0.x` | **21** |
| 6.1 / 6.0 | 23 / 22 | `6.1.0.x` / `6.0.0.x` | 17 or 21 |
| 5.x | 12–15 | `5.0.3.x` | **17** |

CLT 26.x documents "JDK 21 recommended; 17 for releases below 26.0.0". A newer
CLT generally talks to older devices; `hdc` prints its version with `hdc -v`.

## 1. Download

The official download is behind a Huawei developer account:

1. Open <https://developer.huawei.com/consumer/cn/download/> and sign in.
2. Find **Command Line Tools**, select **Linux-x64**.
3. You get `commandline-tools-linux-x64-<version>.zip` (~2.3 GB). Verify the
   SHA-256 shown next to the download link if you care.

> Account notes: a free Huawei ID is enough to download, but the download centre
> sometimes asks for real-name verification (实名认证) before exposing the Linux
> package. An `arm64` variant exists for ARM machines; pick the one matching
> `uname -m`.

## 2. Install

Keep it out of `/opt` unless you want to run everything as root — a versioned
directory under your home works fine:

```bash
mkdir -p ~/opt/apps/harmonyos
unzip commandline-tools-linux-x64-<version>.zip -d ~/opt/apps/harmonyos/<version>
# -> ~/opt/apps/harmonyos/<version>/command-line-tools
```

If `ls` shows a directory like `sdk-linux-<something>/commandline/` instead, the
archive unpacked one level deeper; move the inner `command-line-tools` directory
to where you want it.

Avoid paths containing spaces or non-ASCII characters (a classic source of
`hvigorw`/`hdc` breakage), and do not put projects in hidden directories.

Result:

```
~/opt/apps/harmonyos/<version>/command-line-tools/
├── bin/                     hvigorw, ohpm, codelinter, hstack
├── tool/node/               bundled Node.js (use this one, not your system node)
├── sdk/default/openharmony/
│   ├── toolchains/          hdc, lib/hap-sign-tool.jar, restool, hnpcli …
│   ├── ets/  js/  native/  previewer/
└── version.txt              exact SDK / API version
```

## 3. Dependencies

| Package | Why |
|---|---|
| JDK 21 (or 17) | runs `hap-sign-tool.jar` — the only hard Java requirement |
| `openssl` | reordering the certificate chain, inspecting profiles |
| `unzip` | obviously |
| `keytool` | ships with the JDK; used by `hapd keygen` |
| glibc ≥ 2.28 | Debian 11+ / Ubuntu 20.04+ / RHEL 8+ |

```bash
# Debian / Ubuntu
sudo apt install unzip openssl openjdk-21-jdk-headless
# RHEL / openEuler
sudo dnf install unzip openssl java-21-openjdk-headless
```

JDK 21 on a "only JDK 17" release is the usual mismatch — if `hap-sign-tool.jar`
prints a `UnsupportedClassVersionError`, you have the wrong JDK.

## 4. Make it visible to hapd

Three options. Pick one.

### A. Environment Modules (recommended, and what `install.sh` assumes)

`hapd` discovers `~/opt/apps/harmonyos/*/command-line-tools` automatically, so
you do not strictly need this — but a modulefile makes `hdc` available in your
shell too:

```tcl
# ~/opt/modulefiles/harmonyos/26.0.0.865
#%Module
module-whatis "HarmonyOS CLT 26.0.0.865 (API 26)"
set root /home/<you>/opt/apps/harmonyos/26.0.0.865/command-line-tools
prepend-path PATH $root/bin
prepend-path PATH $root/sdk/default/openharmony/toolchains
prepend-path PATH $root/tool/node/bin
setenv COMMANDLINE_TOOL_DIR $root
setenv HDC_HOME $root/sdk/default/openharmony/toolchains
setenv DEVECO_SDK_HOME $root/sdk
setenv NODE_HOME $root/tool/node
```

```bash
module load harmonyos/26.0.0.865
hdc -v
```

### B. Plain environment variables

```bash
export COMMANDLINE_TOOL_DIR=$HOME/opt/apps/harmonyos/<version>/command-line-tools
export HDC_HOME=$COMMANDLINE_TOOL_DIR/sdk/default/openharmony/toolchains
export PATH=$HDC_HOME:$COMMANDLINE_TOOL_DIR/bin:$PATH
```

### C. Tell hapd explicitly

```bash
export HAPD_TOOLCHAIN=$HOME/opt/apps/harmonyos/<version>/command-line-tools
```

This only affects `hapd`; `hdc` will not be on your `PATH`.

## 5. Verify

```bash
hdc -v                                             # Ver: 3.2.0f
java -jar "$HDC_HOME/lib/hap-sign-tool.jar" -version   # 1.0.0
hvigorw -v                                         # only if you build apps
hapd doctor
```

`hapd doctor` marks the toolchain check green once it can find `hdc` and
`hap-sign-tool.jar`, and separately checks Java, the signing material, the
profile's expiry and the connected device.

## Optional: shrink the install

The package is ~7 GB, but `hapd` needs only ~108 MB of it:

| Directory | Size | Needed to sign/install? |
|---|---|---|
| `sdk/default/openharmony/native` | 2.7 G | no (NDK, for compiling C/C++) |
| `sdk/default/openharmony/previewer` | 423 M | no (IDE preview) |
| `sdk/default/openharmony/ets` | 358 M | no (ArkTS compiler) |
| `hvigor` | 288 M | only for building |
| `emulator` | 202 M | no |
| `tool/node` | 200 M | only for building |
| `codelinter` | 196 M | no |
| `ohpm` | 114 M | only for building |
| `sdk/default/openharmony/toolchains` | **108 M** | **yes** |
| `sdk/default/openharmony/js` | 246 M | no |

If you only ever sign and install prebuilt HAPs, keeping `toolchains/` plus
`version.txt` is enough. Deleting the rest is irreversible (re-download to get it
back), so only do it if you are sure you will not build on this machine.

## Alternative when you cannot download the CLT

Huawei's public cloud mirror carries the full **OpenHarmony SDK** without a
login. It is not the CLT (no `hvigorw`/`ohpm`), but it contains `hdc` and
`hap-sign-tool.jar` for Linux:

```bash
V=7.0-Release
curl -s "https://repo.huaweicloud.com/harmonyos/os/$V/ohos-sdk-windows_linux-public_20260829.tar.gz" \
  | tar -xz --wildcards --occurrence=1 'linux/toolchains*' -C /tmp/ohos
# -> /tmp/ohos/linux/toolchains-linux-x64-<ver>-Release.zip  (~30 MB)

unzip -q /tmp/ohos/linux/toolchains-linux-x64-*.zip -d ~/opt/apps/harmonyos/<ver>
```

`--occurrence=1` makes `tar` stop as soon as the matching member is written, so
this streams a little over 1 GB instead of the whole 2.5–4.5 GB archive.

The trade-off: the SDK build of `hdc` may lag behind the CLT one. If a device
refuses to talk, download the real CLT.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `hapd: HarmonyOS Command Line Tools not found` | not in any default location | set `HAPD_TOOLCHAIN` or `COMMANDLINE_TOOL_DIR` |
| `command not found: hdc` | `toolchains/` not on `PATH` | `HDC_HOME` lives in `sdk/default/openharmony/toolchains`, **not** in `bin/` |
| `hvigorw` uses your system Node | `tool/node/bin` not first in `PATH` | prepend it, or move it ahead of `/usr/bin` |
| `UnsupportedClassVersionError` | JDK too old for the CLT | CLT 26.x → JDK 21; 5.x → JDK 17 |
| `GLIBC_2.28 not found` | distro too old | use a newer distro (no clean workaround) |
| `hdc` sees the device as `Unauthorized` | debug authorization not accepted on the phone | unlock, tap *always allow*, then `hdc kill` and reconnect |
| `error while loading shared libraries: libusb_shared.so` | running `hdc` outside its directory | run it by absolute path or keep `toolchains/` on `PATH` |
| USB device invisible | missing udev rule / permissions | use wireless debugging (`hapd connect ip:port`) instead |

## Upgrading

CLT releases are independent archives; install the new version side by side and
switch with `module load harmonyos/<new-version>`. Keep the old directory until
you have signed and installed once with the new one — `hdc` incompatibilities
show up immediately, and rolling back is then just a `module load` away.
