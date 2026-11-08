# How HarmonyOS signing actually works

Everything here was established empirically on a commercial device
(HUAWEI Mate 70 Pro+, HarmonyOS 7.0.0.111, API 26) using
HarmonyOS Command Line Tools 26.0.0.865 on Debian 13.

## The pieces

| File | What it is | Who creates it |
|---|---|---|
| `.p12` | Your key pair, in a PKCS#12 keystore | `keytool` on your machine |
| `.csr` | Certificate signing request (public key + subject) | `keytool -certreq` |
| `.cer` | **Debug certificate** — your public key, signed by Huawei | AppGallery Connect |
| `.p7b` | **Debug profile** — bundle name, allowed permissions, device UDIDs, validity | AppGallery Connect |

A HAP carries the `.p7b` inside it plus a signature block computed with the key in
your `.p12`. At install time the device checks:

1. the certificate chain reaches a root it trusts,
2. the profile's `bundle-name` equals the HAP's `bundleName`,
3. the profile's `debug-info.device-ids` contains this device's UDID,
4. the profile and certificate are inside their validity windows,
5. the profile's `distribution-certificate` matches the signing certificate,
6. the requested permissions are covered by the profile.

All of this is **offline**. The device never calls AppGallery Connect, so a package
that is already signed keeps working even if you delete the app from AGC, until it
expires.

## Why community certificates fail

The SDK ships `OpenHarmony.p12`, `OpenHarmonyProfileDebug.pem` and
`UnsgnedDebugProfileTemplate.json` in `toolchains/lib/`, enough to sign a HAP
locally with no account at all. The package verifies fine with
`hap-sign-tool verify-app`, but a commercial device rejects the install:

```
hdc install -r app-signed.hap
→ code:9568257 error: fail to verify pkcs7 file
```

Device logs:

```
HapVerify: hap_cert_verify_openssl_utils.cpp(GetCertsChain:322)
  it do not come from trusted root,
  issuer: C=CN, O=OpenHarmony, OU=OpenHarmony Team, CN=OpenHarmony Application Root CA
BMS: hap files check signature info failed 8519743
```

The community root is simply not in the device's trust store. This is **not** a
version problem: the community keystore is byte-identical across SDK 5.1, 6.1 and
CLT 26. There is no `bm install` bypass flag either
(`hdc smode` is refused on non-rootable builds). Community certificates only work
on OpenHarmony hardware (e.g. DAYU200) and emulators.

## The certificate chain ordering trap

AppGallery Connect hands you `hap-debug.cer` in **root-first** order:

```
[0] CN=Huawei CBG Root CA G2
[1] CN=Huawei CBG Developer Relations CA G2
[2] CN=<you>\,Development
```

`hap-sign-tool -appCertFile` expects **leaf-first**:

```
leaf → intermediate CA → root
```

Feeding it the file as downloaded fails with `verify certificate chain failed`
(or with a `9568257` at install time if it slips through). `hapd` reorders by
matching `issuer`/`subject` DN pairs, so either order works.

The downloaded `.cer` also carries the `\,Development` suffix in the leaf CN —
that is how you can tell a debug certificate from a release one, along with
`Extended Key Usage: Code Signing` and `Basic Constraints: CA:FALSE`.

## Code signing (`-signCode 1`)

From HarmonyOS NEXT Beta1 onward, HAPs must be code-signed or they will not
install. `hap-sign-tool sign-app -signCode 1` walks every `.so` and `.abc` inside
the package and appends per-file digests to the signing block. Always use it;
`hapd` does by default (`--no-code-sign` disables it for diagnostic purposes).

Cost: roughly 4–6 seconds for a 79 MB package.

## What the profile controls

Decoded with `hap-sign-tool verify-profile -inFile x.p7b -outFile x.json`:

```json
{
  "type": "debug",
  "bundle-info": {
    "bundle-name": "com.example.app",
    "apl": "normal",
    "app-feature": "hos_normal_app",
    "developer-id": "350086000123848559",
    "development-certificate": "-----BEGIN CERTIFICATE-----..."
  },
  "validity": {"not-before": 1794118150, "not-after": 1825654150},
  "debug-info": {"device-id-type": "udid", "device-ids": ["01EB73..."]},
  "acls": {"allowed-acls": []},
  "permissions": {"restricted-permissions": []}
}
```

Practical consequences:

- **`bundle-name`** is the hard constraint. A HAP with another bundle name is
  rejected with `9568322`. Two options: create a profile for that bundle name, or
  rewrite `module.json`'s `app.bundleName` inside the HAP before signing
  (`hapd sign --rename-bundle`).
- **`device-ids`** is why a single profile only installs on your own device(s).
  Up to 100 devices can be bound; changing the device list produces a **new**
  profile that must be downloaded and re-applied.
- **`allowed-acls` / `restricted-permissions`** limit what the app may request.
  A HAP asking for something outside the list fails with `9568289`. Stripping the
  permission from `module.json` and re-signing is the workaround
  (`hapd sign --strip-unsupported`) — but the feature that needed it will not work.
- **`type`** must be `debug` for debug installs. A release profile cannot be
  installed on a device for debugging.

## Renewal

The debug certificate and the debug profile normally expire after one year
(the observed pair: 2026-11-08 → 2027-11-08). When they do, the installed app
stops launching.

**Reuse the same `.csr`** when re-applying for the certificate. The certificate
is issued for that public key, so the signing identity stays the same and the new
build can be installed over the old one, keeping app data. Generating a fresh
`.p12`/`.csr` changes the identity and forces an uninstall → reinstall, which
loses app data.

## Minimal manual sequence

For reference, this is what `hapd` automates:

```bash
TC=$HOME/opt/apps/harmonyos/<ver>/command-line-tools/sdk/default/openharmony/toolchains

# 1. reorder the chain: leaf → intermediate → root
python3 - <<'PY'      # (what hapd's order_chain does)
...
PY

# 2. sign
java -jar "$TC/lib/hap-sign-tool.jar" sign-app \
  -keyAlias my-key -signAlg SHA256withECDSA -mode localSign \
  -appCertFile chain.pem -profileFile my.p7b \
  -inFile app-unsigned.hap -outFile app-signed.hap \
  -keystoreFile my.p12 -keyPwd "$PW" -keystorePwd "$PW" -signCode 1

# 3. verify
java -jar "$TC/lib/hap-sign-tool.jar" verify-app -inFile app-signed.hap \
  -outCertChain out.cer -outProfile out.p7b

# 4. install and launch
"$TC/hdc" install -r app-signed.hap
"$TC/hdc" shell aa start -a EntryAbility -b com.example.app -m entry

# 5. logs
"$TC/hdc" shell hilog
```

## Useful device commands

```bash
hdc list targets -v                       # connected targets
hdc tconn <ip>:<port>                     # wireless connect
hdc shell bm get --udid                   # UDID for AGC
hdc shell bm dump -n <bundle>             # installed bundle metadata
hdc shell snapshot_display -f /data/local/tmp/s.jpeg   # screenshot
hdc file recv /data/local/tmp/s.jpeg ./s.jpeg
hdc shell aa start -a <ability> -b <bundle> -m <module>
hdc shell hilog | grep -i <tag>
hdc uninstall <bundle>
```

`aa start` is refused while the screen is locked (`10106102`) — a physical
constraint, not a bug.

## Auth notes

The first `hdc` connection to a device generates `~/.harmony/hdckey` and asks for
confirmation on the phone. Until the user taps *always allow* the target shows as
`Unauthorized`. USB access additionally needs udev rules for the device's vendor
ID; wireless debugging avoids that entirely and is therefore the recommended path
on Linux.
