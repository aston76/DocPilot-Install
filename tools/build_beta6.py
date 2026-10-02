"""Reproduce the public beta.6 package from the beta.5 release."""
import hashlib, pathlib, subprocess, sys, urllib.request, zipfile
ROOT = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path("release-package")
OUT.mkdir(exist_ok=True)
source = OUT / "beta5.zip"
url = "https://github.com/aston76/DocPilot-Install/releases/download/v0.1.0-beta.5/DocPilot-Windows-portable.zip"
with urllib.request.urlopen(url, timeout=120) as response, source.open("wb") as dest:
    while chunk := response.read(1024 * 1024):
        dest.write(chunk)
expected_source = "44217f5b74aaa0aa8d5e71c5bb679c00b9057cd6ecb694250384ce95cf3e37e9"
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected_source
original = OUT / "original.exe"
patched = OUT / "patched.exe"
with zipfile.ZipFile(source) as archive:
    assert archive.testzip() is None
    original.write_bytes(archive.read("DocPilot.exe"))
subprocess.run([sys.executable, str(ROOT / "hotfix_probe_timeout.py"), str(original), str(patched)], check=True)
exe = patched.read_bytes()
assert hashlib.sha256(exe).hexdigest() == "81e4103f7a138023766e59fe798f8110fc5ebff419eb079b8c289d4ceb1ab5c7"
target = OUT / "DocPilot-Windows-portable.zip"
with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as new:
    for info in old.infolist():
        new.writestr(info, exe if info.filename == "DocPilot.exe" else old.read(info))
with zipfile.ZipFile(source) as old, zipfile.ZipFile(target) as new:
    assert new.testzip() is None
    assert old.namelist() == new.namelist()
    changed = [n for n in old.namelist() if hashlib.sha256(old.read(n)).digest() != hashlib.sha256(new.read(n)).digest()]
    assert changed == ["DocPilot.exe"], changed
sha = hashlib.sha256(target.read_bytes()).hexdigest()
assert sha == "4298cb1c9ae6e4c5d7d1c64be1a28ecb2366fcff1f43fc4ba0570413a329634f", "Package must match the locally verified archive"
target.with_suffix(".zip.sha256").write_text(sha + "  " + target.name + "\n", encoding="ascii")
print("Verified package:", sha)
