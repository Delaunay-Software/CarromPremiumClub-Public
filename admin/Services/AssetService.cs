namespace CarromContentAdmin.Services;

public sealed record AssetEntry(string RelPath, long Bytes, bool IsBinary);

/// <summary>
/// Browses and mutates a content node's OWN asset files. Enumeration stops at any
/// subfolder that carries its own manifest.json (that's a child node), so a group's
/// asset list never bleeds in its children's files. Writes are sandboxed to the
/// node's folder.
/// </summary>
public sealed class AssetService
{
    private static readonly string[] BinaryExts = { ".png", ".jpg", ".jpeg", ".mp3", ".glb", ".ogg", ".webp" };

    public IReadOnlyList<AssetEntry> List(ContentNode node)
    {
        var results = new List<AssetEntry>();
        Walk(node.Dir, node.Dir, results, isRoot: true);
        results.Sort((a, b) => string.Compare(a.RelPath, b.RelPath, StringComparison.OrdinalIgnoreCase));
        return results;
    }

    private static void Walk(string dir, string baseDir, List<AssetEntry> acc, bool isRoot)
    {
        // A non-root folder holding its own manifest.json is a child node — don't descend.
        if (!isRoot && File.Exists(Path.Combine(dir, "manifest.json"))) return;

        foreach (var f in Directory.EnumerateFiles(dir))
        {
            var name = Path.GetFileName(f);
            if (name.Equals("manifest.json", StringComparison.OrdinalIgnoreCase)) continue;
            if (name.EndsWith(".import", StringComparison.OrdinalIgnoreCase)) continue; // Godot sidecar
            var rel = Path.GetRelativePath(baseDir, f).Replace('\\', '/');
            var ext = Path.GetExtension(f).ToLowerInvariant();
            acc.Add(new AssetEntry(rel, new FileInfo(f).Length, BinaryExts.Contains(ext)));
        }
        foreach (var sub in Directory.EnumerateDirectories(dir))
            Walk(sub, baseDir, acc, isRoot: false);
    }

    public string AbsPath(ContentNode node, string relPath)
    {
        var full = Path.GetFullPath(Path.Combine(node.Dir, relPath.Replace('/', Path.DirectorySeparatorChar)));
        var root = Path.GetFullPath(node.Dir);
        // Require the separator so a sibling whose name shares this node's prefix
        // (e.g. ".../casino" vs ".../casino-x") can't be written through.
        if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("path escapes the node folder");
        return full;
    }

    public async Task SaveAsync(ContentNode node, string relPath, Stream content, CancellationToken ct = default)
    {
        var dest = AbsPath(node, relPath);
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        await using var fs = File.Create(dest);
        await content.CopyToAsync(fs, ct);
    }

    public void Delete(ContentNode node, string relPath)
    {
        var dest = AbsPath(node, relPath);
        if (File.Exists(dest)) File.Delete(dest);
        var sidecar = dest + ".import";
        if (File.Exists(sidecar)) File.Delete(sidecar);
    }
}
