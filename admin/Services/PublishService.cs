namespace CarromContentAdmin.Services;

/// <summary>
/// Orchestrates the content build/sign step: runs tools/build_all_content_pcks.py
/// (Godot headless export → per-pack ECDSA-P256 signature → signed packs-index.json)
/// with the GODOT env var pointed at the configured editor. Git commit/push and the
/// GitHub Release upload are separate services the Publish page sequences.
/// </summary>
public sealed class PublishService
{
    private readonly RepoContext _repo;
    private readonly ProcessRunner _proc;
    public PublishService(RepoContext repo, ProcessRunner proc) { _repo = repo; _proc = proc; }

    public sealed record Preflight(bool Ok, IReadOnlyList<string> Problems);

    public Preflight Check()
    {
        var problems = new List<string>();
        if (!File.Exists(_repo.BuildAllScript)) problems.Add($"build script missing: {_repo.BuildAllScript}");
        if (!_repo.GodotExists) problems.Add($"Godot not found: {_repo.Godot}");
        if (!_repo.SigningKeyExists) problems.Add($"signing key not found: {_repo.SigningKey}");
        return new Preflight(problems.Count == 0, problems);
    }

    // Packed text types (mirrors .gitattributes `text eol=lf`). Packs embed these
    // files' raw bytes, so CRLF in the working tree would be signed as CRLF while git
    // stores LF — breaking deterministic hashing. Normalise before every sign.
    private static readonly string[] TextExts = { ".json", ".import", ".bbcode", ".svg", ".md" };

    /// <summary>Strip CR bytes from every packed text file under games/ so the signed
    /// packs are byte-identical to the LF-normalised git source. Byte-level (0x0D
    /// only ever appears as CR in UTF-8, so this is safe for multibyte + BOM) and
    /// idempotent — untouched files aren't rewritten. Returns the count changed.</summary>
    public int NormalizeContentLineEndings(Action<string> onLine)
    {
        int changed = 0;
        foreach (var f in Directory.EnumerateFiles(_repo.GamesRoot, "*", SearchOption.AllDirectories))
        {
            if (!TextExts.Contains(Path.GetExtension(f).ToLowerInvariant())) continue;
            var bytes = File.ReadAllBytes(f);
            if (Array.IndexOf(bytes, (byte)'\r') < 0) continue;
            File.WriteAllBytes(f, bytes.Where(b => b != (byte)'\r').ToArray());
            onLine($"  LF {Path.GetRelativePath(_repo.RepoRoot, f).Replace('\\', '/')}");
            changed++;
        }
        return changed;
    }

    /// <summary>Rebuild + sign every pack into dist/. Normalises CRLF→LF on packed
    /// text FIRST (the signature must cover LF content). Uses --skip-gen when the pack
    /// file-lists are unchanged (a manifest value edit), so the tracked
    /// export_presets.cfg isn't rewritten.</summary>
    public Task<ProcessResult> BuildAndSignAsync(bool skipGen, Action<string> onLine, CancellationToken ct = default)
    {
        onLine("── Normalize line endings (CRLF→LF) ──");
        var n = NormalizeContentLineEndings(onLine);
        onLine(n == 0 ? "  already LF" : $"  normalized {n} file(s)");

        var args = new List<string>
        {
            _repo.BuildAllScript,
            _repo.RepoRoot,
            _repo.DistRoot,
            _repo.SigningKey,
        };
        if (skipGen) args.Add("--skip-gen");

        var env = new Dictionary<string, string> { ["GODOT"] = _repo.Godot };
        onLine($"$ {_repo.Python} tools/build_all_content_pcks.py {(skipGen ? "--skip-gen" : "")}");
        return _proc.RunAsync(_repo.Python, args, _repo.RepoRoot, env, onLine, ct);
    }

    /// <summary>Default release tag — stable, sortable, no clock dependency beyond
    /// the caller's supplied stamp.</summary>
    public static string DefaultTag(DateTimeOffset now) => $"content-{now:yyyyMMdd-HHmmss}";
}
