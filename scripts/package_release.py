"""Empacota o executavel PyInstaller para a matriz de Release."""
import argparse
from pathlib import Path
import tarfile
import zipfile

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--platform", choices=["linux","windows"], required=True)
    args = p.parse_args()
    out = Path("release")
    out.mkdir(exist_ok=True)
    if args.platform == "linux":
        executable = Path("dist/ourgit")
        assert executable.is_file()
        with tarfile.open(out / "ourgit-linux-x86_64.tar.gz", "w:gz") as tar:
            tar.add(executable, arcname="ourgit")
    else:
        executable = Path("dist/ourgit.exe")
        assert executable.is_file()
        with zipfile.ZipFile(out / "ourgit-windows-x86_64.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(executable, arcname="ourgit.exe")
    print("Pacote criado:", out.resolve())

if __name__ == "__main__":
    main()
