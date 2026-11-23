#!/usr/bin/env python3
"""Put the pinned source-library embedding model into the public-rag model cache.

  install-library-embedder.py --office-state "$OFFICE_STATE_DIR"                 # fetch the pinned revision from Hugging Face
  install-library-embedder.py --office-state "$OFFICE_STATE_DIR" --from-dir DIR  # copy model.onnx and tokenizer.json already on this machine

Every file is checked against the pinned size and SHA-256 before it is moved into place.
A mismatch stops the install and leaves the cache as it was. Nothing is paid for and no account is used.
"""
import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from office import public_evidence as pe  # noqa: E402

REMOTE = {"model.onnx": "onnx/model.onnx", "tokenizer.json": "tokenizer.json"}
SHA256 = {"model.onnx": "17c8809b2f4893a3c3641cc0bfb84861484f97f1f3cd22a68580e36bf3fbabe4",
          "tokenizer.json": "a6dd38d692ac1caa6d5dbc195d92f1f978b5c74ec60e02ed15fdf04404742fe3"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def verified(path: Path, name: str) -> bool:
    return path.is_file() and path.stat().st_size == pe._LIBRARY_MODEL_FILES[name] and digest(path) == SHA256[name]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--office-state", required=True)
    parser.add_argument("--from-dir")
    args = parser.parse_args()
    cache = Path(args.office_state).expanduser() / "public-rag" / "model-cache"
    target = cache / pe._LIBRARY_MODEL_DIR / pe._LIBRARY_MODEL_REVISION
    if all(verified(target / name, name) for name in REMOTE):
        print(f"이미 설치되어 있습니다: {target}")
        return 0
    if not cache.is_dir():
        print(f"모델 보관 폴더가 없습니다: {cache}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(dir=cache) as scratch:
        for name, remote in REMOTE.items():
            part = Path(scratch) / name
            if args.from_dir:
                shutil.copyfile(Path(args.from_dir).expanduser() / name, part)
            else:
                urllib.request.urlretrieve(
                    f"https://huggingface.co/{pe._LIBRARY_MODEL}/resolve/{pe._LIBRARY_MODEL_REVISION}/{remote}", part)
            if not verified(part, name):
                print(f"{name}: 크기나 SHA-256이 고정한 값과 다릅니다. 설치하지 않았습니다.", file=sys.stderr)
                return 1
        target.mkdir(parents=True, exist_ok=True)
        for name in REMOTE:
            os.chmod(Path(scratch) / name, 0o600)
            os.replace(Path(scratch) / name, target / name)
    print(f"설치했습니다: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
