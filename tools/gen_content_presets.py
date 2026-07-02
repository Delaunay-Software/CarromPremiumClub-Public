#!/usr/bin/env python3
"""Generate the per-flavour + per-group-common content export presets in
export_presets.cfg by scanning the games/ tree.

Deterministic and Godot-free ON PURPOSE: headless Godot has no "create preset"
command and CORRUPTS export_presets.cfg on exit (it drops custom presets +
hand-set filters), so presets are authored by writing the .cfg text directly.
Godot headless is used only to EXPORT each pack afterwards (see
tools/build_content_pck.sh, which guards the .cfg around the export).

Pack decomposition — every packable file lands in exactly ONE pack, chosen by
its deepest owning node (mirrors FlavourPath's cascade so nothing duplicates):

  common          games/ root            (manifest.json, _schema/**)
  purist-common   games/purist/ root     (group manifest + shared rules/poster)
  casino-common   games/casino/ root     (flavour manifest + shared assets)
  <leaf>          games/purist/games/<leaf>/**   (icf, funfair, riviera, woodland)
  casino-<sub>    games/casino/games/<sub>/**    (blackjack, slots, roulette, ...)

The platform presets (Windows/macOS/etc.) are preserved verbatim; only presets
whose name starts with "Content" are replaced. Writes a sibling packs.json
(pack id -> tier) that the build loop + ContentSync read.

Usage:  python tools/gen_content_presets.py [games_dir] [--cfg export_presets.cfg]
"""
import argparse, json, os, re, sys

# Non-resource file types Godot won't pack via export_files (they aren't
# "resources") — they must go through a per-pack include_filter instead.
NON_RESOURCE_EXT = ("json", "bbcode")
# File types we never ship (docs / scratch).
SKIP_EXT = ("md", "txt")


def ext(rel: str) -> str:
    return rel.rsplit(".", 1)[-1].lower() if "." in rel else ""


# Files that never belong in a pack: Godot import sidecars (Godot regenerates
# them), doc/scratch files, and the "Extract Textures" mesh artifacts (the .glb
# embeds them; Godot re-derives them and pulls them as GLB dependencies anyway).
def is_skippable(rel: str) -> bool:
    if rel.endswith(".import") or ext(rel) in SKIP_EXT:
        return True
    parts = rel.split("/")
    if "assets" in parts and "meshes" in parts and ext(rel) in ("png", "jpg", "jpeg"):
        return True
    return False


def is_non_resource(rel: str) -> bool:
    return ext(rel) in NON_RESOURCE_EXT


def is_card_asset(rel: str) -> bool:
    """The light bits the menu carousel needs to render a leaf WITHOUT its heavy
    assets: the leaf's own manifest, its hero poster, and its icon. These go into
    a tiny `<leaf>-card` pack (tier common) mounted at boot; everything else in the
    leaf is the heavy `<leaf>` pack (tier flavour) mounted lazily when it's opened."""
    base = rel.rsplit("/", 1)[-1]
    return (base == "manifest.json"
            or rel.endswith("assets/images/poster.png")
            or rel.endswith("assets/images/icon.svg"))


def pack_for(rel: str) -> str:
    """Deepest owning node for a games-relative path — with a card/heavy split on
    leaf flavours so the carousel can boot from the card packs and the heavy
    per-flavour assets download+mount lazily on open."""
    seg = rel.split("/")
    top = seg[0]
    base, is_leaf = None, False
    if top == "casino":
        if len(seg) >= 3 and seg[1] == "games":
            base, is_leaf = f"casino-{seg[2]}", True
        else:
            base = "casino-common"
    elif top == "purist":
        if len(seg) >= 3 and seg[1] == "games":
            base, is_leaf = seg[2], True          # leaf: icf / funfair / riviera / woodland / cafe
        else:
            base = "purist-common"
    else:
        base = "common"                           # games/ root (manifest, index, _schema)
    if is_leaf and is_card_asset(rel):
        return f"{base}-card"
    return base


def tier_for(pack: str) -> str:
    # -common group packs + every -card pack mount at boot; heavy leaf packs lazily.
    if pack in ("common", "purist-common", "casino-common") or pack.endswith("-card"):
        return "common"
    return "flavour"                              # mounted when its flavour is played


# ── export_presets.cfg block model ───────────────────────────────────────────
# The file is a sequence of [section] blocks. A preset "unit" is a [preset.N]
# block immediately followed by its [preset.N.options] block.
SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
PRESET_RE = re.compile(r"^preset\.(?P<idx>\d+)$")
PRESET_OPT_RE = re.compile(r"^preset\.(?P<idx>\d+)\.options$")


def parse_sections(text):
    """Return ordered [(header, body_str)] where header is the [..] label."""
    out, cur_head, cur_body = [], None, []
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            if cur_head is not None:
                out.append((cur_head, "\n".join(cur_body).strip("\n")))
            cur_head, cur_body = m.group("name"), []
        else:
            if cur_head is None:
                # leading blank/junk before first section — ignore
                continue
            cur_body.append(line)
    if cur_head is not None:
        out.append((cur_head, "\n".join(cur_body).strip("\n")))
    return out


def name_of(body: str) -> str:
    m = re.search(r'^name="(.*)"$', body, re.M)
    return m.group(1) if m else ""


def q(path: str) -> str:
    return f'"res://games/{path}"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games_dir", nargs="?", default="games")
    ap.add_argument("--cfg", default="export_presets.cfg")
    ap.add_argument("--packs-out", default=None, help="packs.json path (default: <games_dir>/packs.json)")
    args = ap.parse_args()

    games_dir = args.games_dir.rstrip("/\\")
    if not os.path.isdir(games_dir):
        sys.exit(f"no games dir: {games_dir}")

    # 1. Bucket every packable file into its pack.
    buckets = {}
    for root, _dirs, files in os.walk(games_dir):
        for f in files:
            abs_ = os.path.join(root, f)
            rel = os.path.relpath(abs_, games_dir).replace("\\", "/")
            if is_skippable(rel):
                continue
            buckets.setdefault(pack_for(rel), []).append(rel)
    if not buckets:
        sys.exit("no packable files found")

    # 2. Parse the existing cfg; keep everything that isn't a Content* preset.
    with open(args.cfg, encoding="utf-8") as fh:
        sections = parse_sections(fh.read())

    # Pair preset units; find an options template to clone (prefer an existing
    # Content preset's options, else any Windows Desktop preset's options).
    units, other = [], []          # units: (name, header_body, options_body_or_None)
    i = 0
    opt_template = None
    while i < len(sections):
        head, body = sections[i]
        pm = PRESET_RE.match(head)
        if pm:
            nm = name_of(body)
            opt_body = None
            if i + 1 < len(sections):
                om = PRESET_OPT_RE.match(sections[i + 1][0])
                if om and om.group("idx") == pm.group("idx"):
                    opt_body = sections[i + 1][1]
                    i += 1
            units.append((nm, body, opt_body))
            if opt_body and opt_template is None and (nm.startswith("Content") or 'platform="Windows Desktop"' in body):
                opt_template = opt_body
        else:
            other.append((head, body))
        i += 1
    if opt_template is None:
        sys.exit("no Windows Desktop / Content preset to clone options from")
    # Content packs carry RESOURCES ONLY — the .NET assembly + runtime live in the
    # engine exe. embed_build_outputs=true bakes ~78 MB of managed DLLs (Carrom.dll,
    # GodotSharp, godotsteam) into EVERY pack; force it off for content packs.
    opt_template = opt_template.replace(
        "dotnet/embed_build_outputs=true", "dotnet/embed_build_outputs=false")

    kept = [(nm, hb, ob) for (nm, hb, ob) in units if not nm.startswith("Content")]

    # 3. Build fresh Content preset units (one per pack), sorted for stable diffs.
    #    Resources (png/glb/mp3/svg/...) go in export_files (packed WITH their
    #    dependencies). Non-resources (json/bbcode) aren't packable that way, so
    #    each pack lists its OWN via include_filter as exact res:// paths — this
    #    keeps manifests/rules in the pack without the monolith's "*.json" glob
    #    that would leak every flavour's manifests into every pack.
    def preset_header(name, files):
        resources = sorted(p for p in files if not is_non_resource(p))
        nonres    = sorted(p for p in files if is_non_resource(p))
        listing = ", ".join(q(p) for p in resources)
        # include_filter matches PROJECT-RELATIVE paths (no res:// prefix) — verified
        # by export. res://-prefixed patterns silently match nothing.
        include = ",".join(f"games/{p}" for p in nonres)
        return (
            f'name="{name}"\n'
            'platform="Windows Desktop"\n'
            "dedicated_server=false\n"
            'custom_features=""\n'
            'export_filter="resources"\n'
            f"export_files=PackedStringArray({listing})\n"
            f'include_filter="{include}"\n'
            'exclude_filter=""\n'
            'export_path=""\n'
            "patches=PackedStringArray()\n"
            "patch_delta_encoding=false\n"
            "patch_delta_compression_level_zstd=19\n"
            "patch_delta_min_reduction=0.1\n"
            'patch_delta_include_filters="*"\n'
            'patch_delta_exclude_filters=""\n'
            'encryption_include_filters=""\n'
            'encryption_exclude_filters=""\n'
            "seed=0\n"
            "encrypt_pck=false\n"
            "encrypt_directory=false\n"
            "script_export_mode=2"
        )

    new_units = []
    for pack in sorted(buckets):
        new_units.append((f"Content - {pack}", preset_header(f"Content - {pack}", buckets[pack]), opt_template))

    all_units = kept + new_units

    # 4. Emit: non-preset sections first (runnable_presets etc.), then renumbered units.
    out = []
    for head, body in other:
        out.append(f"[{head}]\n\n{body}\n")
    for n, (_nm, hb, ob) in enumerate(all_units):
        out.append(f"[preset.{n}]\n\n{hb}\n")
        if ob is not None:
            out.append(f"[preset.{n}.options]\n\n{ob}\n")

    with open(args.cfg, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out).rstrip("\n") + "\n")

    # 5. packs.json — pack id -> tier, for the build loop + ContentSync.
    packs = {pack: {"tier": tier_for(pack), "files": len(buckets[pack])} for pack in sorted(buckets)}
    packs_out = args.packs_out or os.path.join(games_dir, "packs.json")
    with open(packs_out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "packs": packs}, fh, indent=2)
        fh.write("\n")

    print(f"wrote {len(new_units)} Content presets ({len(kept)} platform presets kept) -> {args.cfg}")
    print(f"packs.json -> {packs_out}")
    for pack in sorted(buckets):
        print(f"  {pack:20s} {tier_for(pack):8s} {len(buckets[pack])} file(s)")


if __name__ == "__main__":
    main()
