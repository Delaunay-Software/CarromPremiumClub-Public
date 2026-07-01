#!/usr/bin/env python3
"""Build (and optionally sign) the remote-content index for ContentSync.

The remote repo's content root mirrors the game's `games/` tree. This walks it,
records every file's sha256 + size grouped by top-level section, writes
`index.json`, and — given an EC private key — signs the exact index bytes with
openssl to produce the detached `index.json.sig` that ContentSync verifies against
the public key baked into the binary.

Usage:
  # one-time: make a P-256 keypair (bake the printed public PEM into ContentSync)
  python tools/build_content_index.py --genkey content_signing

  # build + sign
  python tools/build_content_index.py games/ --out dist/ --key content_signing_priv.pem

Signing/keygen shell out to `openssl` (no python deps). Index build is stdlib-only.
"""
import argparse, hashlib, json, os, subprocess, sys, base64


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


SKIP = {".git", ".DS_Store"}

_MESH_TEX_EXT = (".jpg", ".jpeg", ".png")


def _is_mesh_texture_artifact(rel):
    """Godot 'Extract Textures' writes each GLB's embedded images out as loose files
    in the mesh folder; they regenerate on import and are NOT delivered (the .glb is
    the source, images embedded). Mirror .gitignore so the index never lists them."""
    parts = rel.split("/")
    if "meshes" not in parts:
        return False
    low = rel.lower()
    if low.endswith(".import"):
        low = low[: -len(".import")]
    return low.endswith(_MESH_TEX_EXT)


def build_index(content_dir):
    content_dir = os.path.abspath(content_dir)
    sections = {}  # top-level subfolder -> list of file entries
    for dirpath, dirnames, filenames in os.walk(content_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for fn in filenames:
            if fn in SKIP or fn == "index.json" or fn == "index.json.sig":
                continue
            rel_check = os.path.relpath(os.path.join(dirpath, fn), content_dir).replace(os.sep, "/")
            if _is_mesh_texture_artifact(rel_check):
                continue
            abs_p = os.path.join(dirpath, fn)
            rel = os.path.relpath(abs_p, content_dir).replace(os.sep, "/")
            top = rel.split("/", 1)[0] if "/" in rel else "_root"
            sections.setdefault(top, []).append({
                "path": rel,
                "sha256": sha256_file(abs_p),
                "bytes": os.path.getsize(abs_p),
            })
    games = []
    for sec in sorted(sections):
        files = sorted(sections[sec], key=lambda e: e["path"])
        # version = short hash of the section's file hashes → changes iff content does
        ver = hashlib.sha256("".join(f["sha256"] for f in files).encode()).hexdigest()[:12]
        games.append({"id": sec, "version": ver, "files": files})
    return {"schema": 1, "games": games}


def genkey(prefix):
    priv = f"{prefix}_priv.pem"
    subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey",
                    "-noout", "-out", priv], check=True)
    pub = subprocess.run(["openssl", "ec", "-in", priv, "-pubout"],
                         check=True, capture_output=True, text=True).stdout
    print(f"Private key written to {priv} (keep OFFLINE - never commit).")
    print("Bake this PUBLIC key into ContentSync.PublicKeyPem:\n")
    print(pub)


def sign(index_path, key_path, out_sig):
    # DER ECDSA signature over the exact index bytes, base64 for text-safe transport.
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path, index_path],
                         check=True, capture_output=True).stdout
    with open(out_sig, "wb") as f:
        f.write(base64.b64encode(der))
    print(f"Signed -> {out_sig}")


def main():
    ap = argparse.ArgumentParser(description="Build/sign the ContentSync index.")
    ap.add_argument("content_dir", nargs="?", help="content root (mirrors games/)")
    ap.add_argument("--out", default=".", help="output dir for index.json[.sig]")
    ap.add_argument("--key", help="EC private key PEM to sign with (openssl)")
    ap.add_argument("--genkey", metavar="PREFIX", help="generate a P-256 keypair and exit")
    args = ap.parse_args()

    if args.genkey:
        genkey(args.genkey)
        return 0
    if not args.content_dir:
        ap.error("content_dir is required (or use --genkey)")

    os.makedirs(args.out, exist_ok=True)
    index = build_index(args.content_dir)
    index_path = os.path.join(args.out, "index.json")
    # LF + trailing newline always, so the committed baseline is byte-stable across
    # platforms (the CI freshness check diffs a fresh build against it).
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    nfiles = sum(len(g["files"]) for g in index["games"])
    print(f"Wrote {index_path}: {len(index['games'])} section(s), {nfiles} file(s).")

    if args.key:
        sign(index_path, args.key, os.path.join(args.out, "index.json.sig"))
    else:
        print("No --key: unsigned. ContentSync REQUIRES a signed index - sign before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
