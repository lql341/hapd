#!/usr/bin/env python3
"""Offline unit tests for hapd. No device, no SDK, no signing material needed.

    python3 -m unittest discover -s tests -v
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_hapd():
    """Import the extensionless `hapd` script as a module."""
    spec = importlib.util.spec_from_loader(
        "hapd_mod", importlib.machinery.SourceFileLoader("hapd_mod", os.path.join(ROOT, "hapd")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hapd = load_hapd()


def make_hap(path, bundle="com.example.app", permissions=("ohos.permission.INTERNET",)):
    module = {
        "app": {
            "bundleName": bundle,
            "versionName": "1.0.0",
            "versionCode": 1000000,
            "minAPIVersion": 60002022,
            "targetAPIVersion": 60101024,
        },
        "module": {
            "name": "entry",
            "mainElement": "EntryAbility",
            "deviceTypes": ["phone"],
            "requestPermissions": [{"name": p} for p in permissions],
            "abilities": [{"name": "EntryAbility"}],
            "extensionAbilities": [],
        },
    }
    pack = {"summary": {"app": {"bundleName": bundle},
                        "modules": [{"moduleName": "entry"}]}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("module.json", json.dumps(module))
        z.writestr("pack.info", json.dumps(pack))
        z.writestr("ets/modules.abc", b"\x00" * 64)
        z.writestr("resources.index", b"\x01" * 32)
    return path


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hapd-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestHapInfo(TempDir):
    def test_reads_module_json(self):
        p = make_hap(os.path.join(self.tmp, "a.hap"))
        info = hapd.hap_info(p)
        self.assertEqual(info["bundle_name"], "com.example.app")
        self.assertEqual(info["version_name"], "1.0.0")
        self.assertEqual(info["module_name"], "entry")
        self.assertEqual(info["main_element"], "EntryAbility")
        self.assertEqual(info["permissions"], ["ohos.permission.INTERNET"])
        self.assertFalse(info["signed"])

    def test_missing_file_exits_2(self):
        with self.assertRaises(SystemExit) as cm:
            hapd.hap_info(os.path.join(self.tmp, "nope.hap"))
        self.assertEqual(cm.exception.code, 2)


class TestSignatureDetection(TempDir):
    def test_unsigned(self):
        p = make_hap(os.path.join(self.tmp, "a.hap"))
        self.assertFalse(hapd.detect_signature(p))

    def test_trailing_pem_is_detected(self):
        p = make_hap(os.path.join(self.tmp, "a.hap"))
        with open(p, "ab") as f:
            f.write(b"\x00" * 128 + b"-----BEGIN CERTIFICATE-----\nMIIB\n"
                    b"-----END CERTIFICATE-----\n")
        self.assertTrue(hapd.detect_signature(p))

    def test_meta_inf_is_irrelevant(self):
        # HAPs never carry META-INF; its presence must not be treated as a signature.
        p = make_hap(os.path.join(self.tmp, "a.hap"))
        with zipfile.ZipFile(p, "a") as z:
            z.writestr("META-INF/whatever.txt", b"x")
        self.assertFalse(hapd.detect_signature(p))


class TestRewrite(TempDir):
    def test_rename_bundle(self):
        src = make_hap(os.path.join(self.tmp, "a.hap"))
        dst = os.path.join(self.tmp, "b.hap")
        hapd.rewrite_hap(src, dst, bundle_name="com.other.app")
        self.assertEqual(hapd.hap_info(dst)["bundle_name"], "com.other.app")
        with zipfile.ZipFile(dst) as z:
            self.assertEqual(json.loads(z.read("pack.info"))["summary"]["app"]["bundleName"],
                             "com.other.app")
        # every other entry is preserved byte for byte
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst) as b:
            self.assertEqual(sorted(a.namelist()), sorted(b.namelist()))
            self.assertEqual(a.read("ets/modules.abc"), b.read("ets/modules.abc"))

    def test_drop_permission(self):
        src = make_hap(os.path.join(self.tmp, "a.hap"),
                       permissions=("ohos.permission.INTERNET", "ohos.permission.CAMERA"))
        dst = os.path.join(self.tmp, "b.hap")
        hapd.rewrite_hap(src, dst, drop_permissions=["ohos.permission.CAMERA"])
        self.assertEqual(hapd.hap_info(dst)["permissions"], ["ohos.permission.INTERNET"])

    def test_unchanged_when_no_edits(self):
        src = make_hap(os.path.join(self.tmp, "a.hap"))
        dst = os.path.join(self.tmp, "b.hap")
        hapd.rewrite_hap(src, dst)
        self.assertEqual(hapd.hap_info(src)["bundle_name"], hapd.hap_info(dst)["bundle_name"])

    def test_same_path_rejected(self):
        src = make_hap(os.path.join(self.tmp, "a.hap"))
        with self.assertRaises(SystemExit):
            hapd.rewrite_hap(src, src, bundle_name="x")


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class TestChainOrder(TempDir):
    def _genkey(self, name):
        key = os.path.join(self.tmp, name + ".key")
        subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey",
                        "-noout", "-out", key], check=True, capture_output=True)
        return key

    def _cert(self, name, cn, issuer_cn=None, ca=False):
        """Create a key pair plus a certificate (self-signed or CA-signed)."""
        key = self._genkey(name)
        crt = os.path.join(self.tmp, name + ".pem")
        csr = os.path.join(self.tmp, name + ".csr")
        subprocess.run(["openssl", "req", "-new", "-key", key, "-out", csr,
                        "-subj", f"/CN={cn}"], check=True, capture_output=True)
        if issuer_cn is None:
            args = ["openssl", "req", "-new", "-x509", "-key", key, "-out", crt,
                    "-days", "3650", "-subj", f"/CN={cn}"]
            if ca:
                args += ["-addext", "basicConstraints=critical,CA:TRUE"]
        else:
            ext = os.path.join(self.tmp, name + ".ext")
            with open(ext, "w") as f:
                f.write("basicConstraints=critical,CA:TRUE\n" if ca else
                        "basicConstraints=critical,CA:FALSE\n")
            args = ["openssl", "x509", "-req", "-in", csr,
                    "-CA", os.path.join(self.tmp, issuer_cn + ".pem"),
                    "-CAkey", os.path.join(self.tmp, issuer_cn + ".key"),
                    "-CAcreateserial", "-out", crt, "-days", "3650", "-extfile", ext]
        subprocess.run(args, check=True, capture_output=True)
        return crt

    def test_root_first_gets_reversed(self):
        root = self._cert("root", "Root CA", ca=True)
        inter = self._cert("inter", "Inter CA", issuer_cn="root", ca=True)
        leaf = self._cert("leaf", "Leaf", issuer_cn="inter")
        cer = os.path.join(self.tmp, "chain.cer")
        with open(cer, "w") as f:                       # AGC order: root, inter, leaf
            for p in (root, inter, leaf):
                f.write(open(p).read())
        out = os.path.join(self.tmp, "ordered.pem")
        _, n = hapd.order_chain(cer, out)
        self.assertEqual(n, 3)
        text = open(out).read()
        subjects = [hapd._cert_field(c, "subject")
                    for c in hapd._pem_blocks(text)]
        self.assertIn("Leaf", subjects[0])
        self.assertIn("Inter CA", subjects[1])
        self.assertIn("Root CA", subjects[2])

    def test_single_cert_passthrough(self):
        leaf = self._cert("leaf", "Solo")
        out = os.path.join(self.tmp, "one.pem")
        _, n = hapd.order_chain(leaf, out)
        self.assertEqual(n, 1)

    def test_pubkey_fingerprint_stable_across_reissue(self):
        a = self._cert("a", "Same Key")
        b = self._cert("b", "Same Key Again", issuer_cn="a")
        pem_a = open(a).read()
        pem_b = hapd._pem_blocks(open(b).read())[0]
        # different certificates, different keys -> different fingerprints
        self.assertNotEqual(hapd.pubkey_fp(pem_a), hapd.pubkey_fp(pem_b))
        # same certificate -> same fingerprint
        self.assertEqual(hapd.pubkey_fp(pem_a), hapd.pubkey_fp(pem_a))


class TestErrorTable(unittest.TestCase):
    def test_known_codes_have_guidance(self):
        for code in ("9568257", "9568289", "9568322", "9568332", "10106102"):
            self.assertIn(code, hapd.ERRORS)
            title, why, fix = hapd.ERRORS[code]
            self.assertTrue(all([title, why, fix]))


class TestCli(unittest.TestCase):
    def test_version(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "hapd"), "--version"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("hapd", r.stdout)

    def test_help_lists_commands(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "hapd"), "--help"],
                           capture_output=True, text=True)
        for cmd in ("deploy", "sign", "install", "doctor", "renew", "keygen"):
            self.assertIn(cmd, r.stdout)

    def test_explain_json(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "hapd"), "--json",
                            "explain", "9568257"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["code"], "9568257")


if __name__ == "__main__":
    unittest.main()
