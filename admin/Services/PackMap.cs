namespace CarromContentAdmin.Services;

/// <summary>
/// Maps a games-relative file path (and a <see cref="ContentNode"/>) to the content
/// PACK it ships in — a faithful C# port of <c>tools/gen_content_presets.py:pack_for</c>
/// so the admin's "which packs are dirty" answer matches exactly what the build tool
/// would produce. This is the seam that lets Save / Sign / Publish target ONLY the
/// packs whose files actually changed.
/// </summary>
public sealed class PackMap
{
    private readonly RepoContext _repo;
    private readonly GitService _git;
    public PackMap(RepoContext repo, GitService git) { _repo = repo; _git = git; }

    /// <summary>Card assets are the light bits the carousel needs without the heavy
    /// pack: a leaf's manifest, hero poster, and icon. They ship in <c>&lt;leaf&gt;-card</c>.</summary>
    private static bool IsCardAsset(string rel)
    {
        var baseName = rel.Contains('/') ? rel[(rel.LastIndexOf('/') + 1)..] : rel;
        return baseName == "manifest.json"
            || rel.EndsWith("assets/images/poster.png", StringComparison.OrdinalIgnoreCase)
            || rel.EndsWith("assets/images/icon.svg", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>Never-packed files: Godot import sidecars, docs/scratch, and the
    /// "Extract Textures" mesh image artifacts (the GLB embeds them).</summary>
    private static bool IsSkippable(string rel)
    {
        if (rel.EndsWith(".import", StringComparison.OrdinalIgnoreCase)) return true;
        var ext = Ext(rel);
        if (ext is "md" or "txt") return true;
        var parts = rel.Split('/');
        if (Array.IndexOf(parts, "assets") >= 0 && Array.IndexOf(parts, "meshes") >= 0
            && ext is "png" or "jpg" or "jpeg") return true;
        return false;
    }

    private static string Ext(string rel)
        => rel.Contains('.') ? rel[(rel.LastIndexOf('.') + 1)..].ToLowerInvariant() : "";

    /// <summary>The pack id a games-relative path ships in. Mirrors the Python tool
    /// byte-for-byte: casino leaves → <c>casino-&lt;sub&gt;</c>, purist leaves → the bare
    /// leaf id, group roots → <c>&lt;group&gt;-common</c>, games/ root → <c>common</c>;
    /// leaf card assets split into <c>&lt;base&gt;-card</c>.</summary>
    public static string PackForRel(string rel)
    {
        rel = rel.Replace('\\', '/').TrimStart('/');
        var seg = rel.Split('/');
        var top = seg[0];
        string @base;
        bool isLeaf = false;
        if (top == "casino")
        {
            if (seg.Length >= 3 && seg[1] == "games") { @base = $"casino-{seg[2]}"; isLeaf = true; }
            else @base = "casino-common";
        }
        else if (top == "purist")
        {
            if (seg.Length >= 3 && seg[1] == "games") { @base = seg[2]; isLeaf = true; }
            else @base = "purist-common";
        }
        else @base = "common";
        return isLeaf && IsCardAsset(rel) ? $"{@base}-card" : @base;
    }

    /// <summary>The distinct pack ids a node's OWN files span (both the heavy leaf
    /// pack and its <c>-card</c> split for a playable leaf). A manifest-only edit on a
    /// leaf touches the <c>-card</c> pack; an asset edit touches the heavy pack.</summary>
    public IReadOnlyCollection<string> PacksForNode(ContentNode node)
    {
        var packs = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        if (!Directory.Exists(node.Dir)) return packs;
        foreach (var f in Directory.EnumerateFiles(node.Dir, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(_repo.GamesRoot, f).Replace('\\', '/');
            if (IsSkippable(rel)) continue;
            // Stop at a child node's folder — those files belong to the child's packs.
            if (BelongsToChild(node, f)) continue;
            packs.Add(PackForRel(rel));
        }
        return packs;
    }

    /// <summary>A file under <paramref name="node"/> that lives beneath a nested
    /// manifest.json belongs to that child node, not this one.</summary>
    private static bool BelongsToChild(ContentNode node, string file)
    {
        var dir = Path.GetDirectoryName(file);
        var nodeDir = Path.GetFullPath(node.Dir);
        while (dir != null && Path.GetFullPath(dir).Length > nodeDir.Length)
        {
            if (File.Exists(Path.Combine(dir, "manifest.json"))) return true;
            dir = Path.GetDirectoryName(dir);
        }
        return false;
    }

    /// <summary>Pack ids with uncommitted changes, derived from <c>git status</c> over
    /// games/. This is the authoritative "dirty" set the publish step targets — it
    /// catches edits made by ANY means (this tool, a text editor, git operations),
    /// not just this session's in-memory edits.</summary>
    public async Task<IReadOnlyCollection<string>> DirtyPacksAsync(CancellationToken ct = default)
    {
        var status = await _git.StatusAsync(ct);
        var packs = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in status.Changes)
        {
            // porcelain: "XY <path>" (renames: "R  old -> new"); take the final path.
            var path = line.Length > 3 ? line[3..].Trim() : "";
            if (path.Contains("->")) path = path[(path.IndexOf("->") + 2)..].Trim();
            path = path.Trim('"').Replace('\\', '/');
            const string prefix = "games/";
            if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) continue;
            var rel = path[prefix.Length..];
            if (rel.StartsWith("packs.json") || rel.StartsWith("_schema/")) { packs.Add("common"); continue; }
            if (IsSkippable(rel)) continue;
            packs.Add(PackForRel(rel));
        }
        return packs;
    }
}
