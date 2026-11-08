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


def make_hap(path, bundle="com.example.app", permissions=("ohos.permission.INTERNET",),
             kind="entry"):
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
            "type": kind,
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

    def test_missing_file_raises_with_code_2(self):
        with self.assertRaises(hapd.HapdError) as cm:
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
        with self.assertRaises(hapd.HapdError):
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
        with open(cer, "w") as out:                     # AGC order: root, inter, leaf
            for p in (root, inter, leaf):
                with open(p) as src:
                    out.write(src.read())
        out = os.path.join(self.tmp, "ordered.pem")
        _, n = hapd.order_chain(cer, out)
        self.assertEqual(n, 3)
        with open(out) as f:
            text = f.read()
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
        with open(a) as f:
            pem_a = f.read()
        with open(b) as f:
            pem_b = hapd._pem_blocks(f.read())[0]
        # different certificates, different keys -> different fingerprints
        self.assertNotEqual(hapd.pubkey_fp(pem_a), hapd.pubkey_fp(pem_b))
        # same certificate -> same fingerprint
        self.assertEqual(hapd.pubkey_fp(pem_a), hapd.pubkey_fp(pem_a))


class TestModuleType(TempDir):
    def test_entry_and_shared_are_distinguished(self):
        hap = make_hap(os.path.join(self.tmp, "a.hap"), kind="entry")
        hsp = make_hap(os.path.join(self.tmp, "b.hsp"), kind="shared")
        self.assertEqual(hapd.hap_info(hap)["module_type"], "entry")
        self.assertEqual(hapd.hap_info(hsp)["module_type"], "shared")

    def test_order_puts_shared_first(self):
        hap = make_hap(os.path.join(self.tmp, "entry.hap"), kind="entry")
        hsp1 = make_hap(os.path.join(self.tmp, "lib1.hsp"), kind="shared")
        hsp2 = make_hap(os.path.join(self.tmp, "lib2.hsp"), kind="shared")
        shared, normal = hapd.order_for_install([hap, hsp1, hsp2])
        self.assertEqual(shared, [hsp1, hsp2])
        self.assertEqual(normal, [hap])

    def test_unknown_packages_are_treated_as_normal(self):
        good = make_hap(os.path.join(self.tmp, "ok.hap"))
        junk = os.path.join(self.tmp, "junk.hap")
        with open(junk, "wb") as f:
            f.write(b"not a zip")
        shared, normal = hapd.order_for_install([junk, good])
        self.assertEqual(shared, [])
        self.assertIn(good, normal)


class TestCliOffline(TempDir):
    """End-to-end CLI behaviour with a stub toolchain, no SDK or device."""

    def setUp(self):
        super().setUp()
        clt = os.path.join(self.tmp, "clt")
        tc = os.path.join(clt, "sdk", "default", "openharmony", "toolchains")
        os.makedirs(os.path.join(tc, "lib"))
        for f in (os.path.join(tc, "hdc"), os.path.join(tc, "lib", "hap-sign-tool.jar")):
            open(f, "w").close()
        self.env = dict(os.environ, HAPD_TOOLCHAIN=clt, HAPD_P12="", HAPD_CERT="",
                        HAPD_PROFILE="", HAPD_P12_PWD="")

    def _run(self, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "hapd")] + list(args),
                              capture_output=True, text=True, env=self.env)

    def test_dry_run_deploy_orders_hsp_before_hap(self):
        hap = make_hap(os.path.join(self.tmp, "entry-unsigned.hap"), kind="entry")
        hsp = make_hap(os.path.join(self.tmp, "lib-unsigned.hsp"), kind="shared")
        r = self._run("--dry-run", "deploy", hap, hsp)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        installs = [ln for ln in lines if "install -r" in ln]
        self.assertEqual(len(installs), 2)
        self.assertIn("-r -s", installs[0])          # shared bundle first, with -s
        self.assertIn(".hsp", installs[0])
        self.assertNotIn("-s", installs[1])

    def test_dry_run_sign_does_not_need_material(self):
        hap = make_hap(os.path.join(self.tmp, "a-unsigned.hap"))
        r = self._run("--dry-run", "sign", hap)
        # no signing material configured -> must fail cleanly, not traceback
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(r.returncode, (0, 3))

    def test_explain_needs_no_toolchain(self):
        r = self._run("--json", "explain", "9568257")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["code"], "9568257")

    def test_info_needs_no_toolchain(self):
        hap = make_hap(os.path.join(self.tmp, "a.hap"))
        r = self._run("info", hap)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("com.example.app", r.stdout)

    def test_info_json_is_machine_readable(self):
        hap = make_hap(os.path.join(self.tmp, "a.hap"))
        r = self._run("--json", "info", hap)
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["bundle_name"], "com.example.app")
        self.assertEqual(doc["module_type"], "entry")


class TestVersionParsing(unittest.TestCase):
    def test_picks_the_bundle_version_not_a_dependency(self):
        # a shared-bundle dependency carries a much larger, date-based code
        dump = """
        {
            "appId": "com.x_y",
            "applicationInfo": {
                "versionCode": 1010850,
                "minCompatibleVersionCode": 1010850
            },
            "hspList": [{"versionCode": 2026110201}],
            "entryModuleName": "entry"
        }
        """
        self.assertEqual(hapd.parse_version_code(dump), 1010850)

    def test_ignores_nested_module_application_info(self):
        # real `bm dump` output has a nested applicationInfo with versionCode 0
        dump = (
            'org.xbgroup.clashbox:\n'
            '{\n'
            '    "applicationInfo": {\n'
            '        "name": "x"\n'
            '    },\n'
            '    "moduleInfos": [{"applicationInfo": {"versionCode": 0}}],\n'
            '    "versionCode": 2010016\n'
            '}'
        )
        self.assertEqual(hapd.parse_version_code(dump), 2010016)

    def test_falls_back_to_top_level(self):
        dump = '{\n    "versionCode": 42,\n    "appId": "com.x_y"\n}'
        self.assertEqual(hapd.parse_version_code(dump), 42)

    def test_returns_none_when_absent(self):
        self.assertIsNone(hapd.parse_version_code("error: bundle not found"))

    def test_error_table_covers_blocking_codes(self):
        for code in ("9568263", "9568266", "9568332"):
            self.assertIn(code, hapd.ERRORS)


class TestErrorTable(unittest.TestCase):
    def test_known_codes_have_guidance(self):
        for code in ("9568257", "9568289", "9568322", "9568332", "10106102"):
            self.assertIn(code, hapd.ERRORS)
            title, why, fix = hapd.ERRORS[code]
            self.assertTrue(all([title, why, fix]))


class TestConsistency(unittest.TestCase):
    def test_version_file_matches_script(self):
        with open(os.path.join(ROOT, "VERSION")) as f:
            v = f.read().strip()
        with open(os.path.join(ROOT, "hapd")) as f:
            m = [l for l in f if l.startswith("VERSION = ")]
        self.assertTrue(m, "VERSION assignment not found in hapd")
        self.assertIn(f'"{v}"', m[0], f"VERSION file says {v}, hapd says {m[0].strip()}")

    def test_changelog_has_current_version(self):
        with open(os.path.join(ROOT, "VERSION")) as f:
            v = f.read().strip()
        with open(os.path.join(ROOT, "CHANGELOG.md")) as f:
            self.assertIn(f"## {v} ", f.read())

    def test_modulefile_template_exists_for_version(self):
        with open(os.path.join(ROOT, "VERSION")) as f:
            v = f.read().strip()
        self.assertTrue(os.path.isfile(
            os.path.join(ROOT, "modulefiles", "hapd", f"{v}.in")))

    def test_no_signing_material_tracked(self):
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        bad = [f for f in out.stdout.split() if f.endswith(
            (".p12", ".p7b", ".cer", ".csr", ".hap", ".hsp")) or f == "hapd.local.tcl"]
        self.assertEqual(bad, [])


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
