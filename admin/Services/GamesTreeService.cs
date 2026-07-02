using System.Text.Json;
using System.Text.Json.Nodes;

namespace CarromContentAdmin.Services;

/// <summary>
/// Reads and mutates the games/ content tree: scans every manifest, reads/writes
/// manifest JSON (LF-normalised to satisfy .gitattributes so content hashes stay
/// byte-identical across platforms), and creates / deletes flavours and groups.
/// Raw manifest text is preserved on edit — only the bytes the user changed move.
/// </summary>
public sealed class GamesTreeService
{
    private readonly RepoContext _repo;
    public GamesTreeService(RepoContext repo) => _repo = repo;

    // ── Scan ────────────────────────────────────────────────────────────────

    /// <summary>Build the full manifest tree. Every folder under games/ that owns a
    /// manifest.json becomes a node, nested under its nearest manifest-bearing
    /// ancestor — so groups, leaf flavours, and arcade mini-games all appear.</summary>
    public ContentNode Scan()
    {
        var gamesRoot = _repo.GamesRoot;
        var manifests = Directory
            .EnumerateFiles(gamesRoot, "manifest.json", SearchOption.AllDirectories)
            .Where(p => !p.Replace('\\', '/').Contains("/_schema/"))
            .OrderBy(p => p.Length)
            .ToList();

        var byDir = new Dictionary<string, ContentNode>(StringComparer.OrdinalIgnoreCase);
        ContentNode? root = null;

        foreach (var mf in manifests)
        {
            var dir = Path.GetDirectoryName(mf)!;
            var node = BuildNode(dir, mf, gamesRoot);
            byDir[NormDir(dir)] = node;
            if (root is null && NormDir(dir) == NormDir(gamesRoot)) root = node;
        }

        // Nest each node under its nearest ancestor that also has a manifest.
        foreach (var (dir, node) in byDir)
        {
            if (node == root) continue;
            var parentDir = Directory.GetParent(dir)?.FullName;
            while (parentDir != null)
            {
                if (byDir.TryGetValue(NormDir(parentDir), out var parent))
                {
                    parent.Children.Add(node);
                    break;
                }
                if (NormDir(parentDir) == NormDir(gamesRoot)) break;
                parentDir = Directory.GetParent(parentDir)?.FullName;
            }
        }

        foreach (var node in byDir.Values)
            node.Children.Sort((a, b) => string.Compare(a.Id, b.Id, StringComparison.OrdinalIgnoreCase));

        return root ?? BuildNode(gamesRoot, _repo.RootManifest, gamesRoot);
    }

    private static ContentNode BuildNode(string dir, string manifestPath, string gamesRoot)
    {
        string? ruleSet = null, name = null;
        try
        {
            var json = JsonNode.Parse(File.ReadAllText(manifestPath));
            ruleSet = json?["rule_set"]?.GetValue<string>();
            name = json?["name"]?.GetValue<string>() ?? json?["title"]?.GetValue<string>();
        }
        catch { /* malformed manifest — still list it so it can be fixed */ }

        var rel = Path.GetRelativePath(gamesRoot, dir).Replace('\\', '/');
        if (rel == ".") rel = "";
        var id = rel == "" ? "games (root)" : Path.GetFileName(dir);

        return new ContentNode
        {
            Id = id,
            RelPath = rel,
            ManifestPath = manifestPath,
            Dir = dir,
            RuleSet = ruleSet,
            DisplayName = name ?? id,
            HasPoster = File.Exists(Path.Combine(dir, "poster.png")),
        };
    }

    private static string NormDir(string p) => Path.GetFullPath(p).TrimEnd('\\', '/');

    // ── Manifest read / write ────────────────────────────────────────────────

    public string ReadRaw(string manifestPath) => File.ReadAllText(manifestPath);

    /// <summary>Validate JSON, then write LF-normalised (no CRLF) so the content
    /// hash is deterministic. Returns null on success, else the parse error.</summary>
    public string? SaveRaw(string manifestPath, string text)
    {
        var err = Validate(text);
        if (err != null) return err;
        File.WriteAllText(manifestPath, Normalize(text));
        return null;
    }

    public static string? Validate(string text)
    {
        try { using var _ = JsonDocument.Parse(text); return null; }
        catch (JsonException e) { return e.Message; }
    }

    /// <summary>Pretty-print through System.Text.Json (2-space, LF) — a "tidy"
    /// affordance for the editor.</summary>
    public static string Pretty(string text)
    {
        var node = JsonNode.Parse(text);
        return Normalize(node!.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static string Normalize(string s)
    {
        s = s.Replace("\r\n", "\n").Replace("\r", "\n");
        if (!s.EndsWith("\n")) s += "\n";
        return s;
    }

    // ── Create / delete ────────────────────────────────────────────────────

    /// <summary>Scaffold a new node folder + manifest under <paramref name="parentRelPath"/>
    /// (relative to games/, "" = root). A rule_set makes it a playable leaf; null makes
    /// it a group. Creates an empty assets/ folder. Returns the new manifest path.</summary>
    public string CreateNode(string parentRelPath, string id, string? ruleSet, string displayName)
    {
        id = Sanitize(id);
        if (string.IsNullOrEmpty(id)) throw new InvalidOperationException("id required");

        // Groups nest a child under <parent>/games/<id>; the root's direct children
        // sit at games/<id>. Mirror the engine's per-folder layout.
        var parentDir = parentRelPath == ""
            ? _repo.GamesRoot
            : Path.Combine(_repo.GamesRoot, parentRelPath.Replace('/', Path.DirectorySeparatorChar));
        var container = parentRelPath == "" ? parentDir : Path.Combine(parentDir, "games");
        var dir = Path.Combine(container, id);
        if (Directory.Exists(dir)) throw new InvalidOperationException($"'{id}' already exists");

        Directory.CreateDirectory(Path.Combine(dir, "assets"));

        var manifest = new JsonObject { ["name"] = displayName };
        if (ruleSet != null) manifest["rule_set"] = ruleSet;
        var path = Path.Combine(dir, "manifest.json");
        File.WriteAllText(path, Normalize(manifest.ToJsonString(new JsonSerializerOptions { WriteIndented = true })));
        return path;
    }

    /// <summary>Delete a node's whole folder. Guarded to stay strictly inside games/
    /// and to never delete the games/ root itself.</summary>
    public void DeleteNode(ContentNode node)
    {
        var full = NormDir(node.Dir);
        var gamesRoot = NormDir(_repo.GamesRoot);
        if (full == gamesRoot) throw new InvalidOperationException("cannot delete the games/ root");
        if (!full.StartsWith(gamesRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            && !full.StartsWith(gamesRoot + "/", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("refusing to delete outside games/");
        Directory.Delete(node.Dir, recursive: true);
    }

    private static string Sanitize(string id) =>
        new string((id ?? "").Trim().ToLowerInvariant()
            .Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '-').ToArray())
            .Trim('-');
}
