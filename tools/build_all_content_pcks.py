#!/usr/bin/env python3
"""Build + sign EVERY per-flavour/common content pack (the split delivery — see
docs/CONTENT-PCK-MIGRATION.md). Supersedes the single-monolith build_content_pck.sh.

Pipeline:
  1. (re)generate the per-pack export presets from the current games/ tree
     (tools/gen_content_presets.py — Godot-free, deterministic).
  2. for each pack in games/packs.json:
       godot --headless --export-pack "Content - <pack>"  ->  <out>/<pack>.pck
       sign it                                             ->  <out>/<pack>.pck.sig   (ECDSA-P256 DER, base64)
       sha256                                              ->  version stamp
  3. write + sign the pack index                           ->  <out>/packs-index.json(.sig)
       { schema, packs: { <id>: { version(sha256), tier } } }
     ContentSync fetches + verifies this index, then mounts each pack.

Headless Godot re-saves export_presets.cfg on exit and DROPS custom presets, so
the authored cfg is backed up once and restored at the end.

Usage:
  GODOT="/c/.../Godot_v4.7-stable_mono_win64_console.exe" \
    python tools/build_all_content_pcks.py <project_dir> <out_dir> <priv_key.pem>
"""
import argparse, base64, hashlib, json, os, shutil, subprocess, sys


def sha256_hex(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_detached(key, path, out):
    """ECDSA-P256 DER signature, base64 (no newline) — matches index.json.sig
    and ContentSync's Rfc3279DerSequence verify."""
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key, path],
                         check=True, capture_output=True).stdout
    with open(out, "wb") as f:
        f.write(base64.b64encode(der))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("out")
    ap.add_argument("key")
    ap.add_argument("--skip-gen", action="store_true", help="use the existing presets, don't regenerate")
    ap.add_argument("--only", default="", help="comma-separated pack ids to (re)build; others are kept from the existing signed index (dirty-only publish)")
    args = ap.parse_args()

    godot = os.environ.get("GODOT", "godot")
    project = os.path.abspath(args.project)
    out = os.path.abspath(args.out)
    key = os.path.abspath(args.key)
    cfg = os.path.join(project, "export_presets.cfg")
    packs_json = os.path.join(project, "games", "packs.json")

    if not shutil.which("openssl"):
        sys.exit("openssl not found")
    if not os.path.isfile(key):
        sys.exit(f"signing key not found: {key}")
    if not os.path.isdir(os.path.join(project, "games")):
        sys.exit(f"no games/ under {project} — copy it in from the content repo first")

    # 1. regenerate presets from the live games/ tree (unless told to skip).
    if not args.skip_gen:
        subprocess.run([sys.executable, os.path.join(project, "tools", "gen_content_presets.py"),
                        os.path.join(project, "games"), "--cfg", cfg], check=True)

    packs = json.load(open(packs_json, encoding="utf-8"))["packs"]
    os.makedirs(out, exist_ok=True)

    # Targeted (dirty-only) build: rebuild just --only packs and MERGE them into the
    # existing signed index so every other pack keeps its published version. Full build
    # (no --only) rebuilds everything from a fresh index.
    only = [p.strip() for p in args.only.split(",") if p.strip()]
    idx_path_existing = os.path.join(out, "packs-index.json")
    if only:
        unknown = [p for p in only if p not in packs]
        if unknown:
            sys.exit(f"--only names unknown pack(s): {', '.join(unknown)}")
        targets = sorted(only)
        if os.path.isfile(idx_path_existing):
            index = json.load(open(idx_path_existing, encoding="utf-8"))
            index.setdefault("schema", 1)
            index.setdefault("packs", {})
        else:
            print("no existing packs-index.json to merge into — building the FULL index", flush=True)
            targets = sorted(packs)
            index = {"schema": 1, "packs": {}}
    else:
        targets = sorted(packs)
        index = {"schema": 1, "packs": {}}

    # 2. export + sign each target pack. Guard export_presets.cfg (headless corrupts it).
    bak = cfg + ".prebuild.bak"
    shutil.copy(cfg, bak)
    try:
        for pid in targets:
            pck = os.path.join(out, f"{pid}.pck")
            print(f"== exporting {pid} ==", flush=True)
            subprocess.run([godot, "--headless", "--path", project,
                            "--export-pack", f"Content - {pid}", pck], check=True)
            if not (os.path.exists(pck) and os.path.getsize(pck) > 0):
                sys.exit(f"export produced no pck for {pid}")
            sign_detached(key, pck, pck + ".sig")
            index["packs"][pid] = {"version": sha256_hex(pck), "tier": packs[pid]["tier"]}
    finally:
        shutil.move(bak, cfg)   # restore the authored cfg no matter what

    # 3. write + sign the pack index.
    idx = os.path.join(out, "packs-index.json")
    with open(idx, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    sign_detached(key, idx, idx + ".sig")

    def size_of(p):
        f = os.path.join(out, f"{p}.pck")
        return os.path.getsize(f) if os.path.isfile(f) else 0
    if only:
        print(f"\ntargeted build: (re)signed {len(targets)} pack(s), merged into {len(index['packs'])}-pack index -> {out}")
        print(f"  rebuilt: {', '.join(targets)}")
    else:
        total = sum(size_of(p) for p in index["packs"])
        print(f"\nbuilt {len(index['packs'])} packs, {total // (1024*1024)} MB total -> {out}")
    for pid in sorted(index["packs"]):
        mb = size_of(pid) // (1024 * 1024)
        mark = " *" if pid in targets else ""
        print(f"  {pid:20s} {index['packs'][pid]['tier']:8s} {mb} MB  {index['packs'][pid]['version'][:12]}{mark}")
    print("Upload every <out>/*.pck, *.pck.sig, packs-index.json + .sig as GitHub Release assets.")


if __name__ == "__main__":
    main()
