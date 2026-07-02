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

    /// <summary>Rebuild + sign every pack into dist/. Uses --skip-gen when the pack
    /// file-lists are unchanged (a manifest value edit), so the tracked
    /// export_presets.cfg isn't rewritten.</summary>
    public Task<ProcessResult> BuildAndSignAsync(bool skipGen, Action<string> onLine, CancellationToken ct = default)
    {
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
