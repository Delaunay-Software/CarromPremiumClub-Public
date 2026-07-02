namespace CarromContentAdmin.Services;

public sealed record GitStatus(string Branch, IReadOnlyList<string> Changes)
{
    public bool Clean => Changes.Count == 0;
}

/// <summary>Git porcelain over <see cref="ProcessRunner"/>, scoped to the repo root.</summary>
public sealed class GitService
{
    private readonly RepoContext _repo;
    private readonly ProcessRunner _proc;
    public GitService(RepoContext repo, ProcessRunner proc) { _repo = repo; _proc = proc; }

    public async Task<GitStatus> StatusAsync(CancellationToken ct = default)
    {
        var branch = (await _proc.RunAsync("git", new[] { "rev-parse", "--abbrev-ref", "HEAD" }, _repo.RepoRoot, ct: ct))
            .Output.Trim();
        var res = await _proc.RunAsync("git", new[] { "status", "--porcelain" }, _repo.RepoRoot, ct: ct);
        var changes = res.Output
            .Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Select(l => l.TrimEnd())
            .ToList();
        return new GitStatus(branch, changes);
    }

    public Task<ProcessResult> AddAllAsync(Action<string>? onLine = null, CancellationToken ct = default)
        => _proc.RunAsync("git", new[] { "add", "-A" }, _repo.RepoRoot, onLine: onLine, ct: ct);

    public Task<ProcessResult> CommitAsync(string message, Action<string>? onLine = null, CancellationToken ct = default)
        => _proc.RunAsync("git", new[] { "commit", "-m", message }, _repo.RepoRoot, onLine: onLine, ct: ct);

    /// <summary>Push, setting upstream on first push so a fresh local branch with no
    /// tracking ref (bare `git push` → "no upstream branch") still works. Idempotent
    /// once tracking is set.</summary>
    public Task<ProcessResult> PushAsync(Action<string>? onLine = null, CancellationToken ct = default)
        => _proc.RunAsync("git", new[] { "push", "-u", "origin", "HEAD" }, _repo.RepoRoot, onLine: onLine, ct: ct);

    public async Task<string> HeadShaAsync(CancellationToken ct = default)
        => (await _proc.RunAsync("git", new[] { "rev-parse", "HEAD" }, _repo.RepoRoot, ct: ct)).Output.Trim();
}
