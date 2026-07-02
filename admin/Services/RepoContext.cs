using Microsoft.Extensions.Options;

namespace CarromContentAdmin.Services;

/// <summary>
/// Resolves and exposes the games-repo layout once at startup. Everything else
/// (tree scan, asset I/O, publish pipeline) asks this for absolute paths so there
/// is a single source of truth for where the repo, its tools, and the signing key
/// live.
/// </summary>
public sealed class RepoContext
{
    public string RepoRoot { get; }
    public string GamesRoot => Path.Combine(RepoRoot, "games");
    public string ToolsRoot => Path.Combine(RepoRoot, "tools");
    public string DistRoot => Path.Combine(RepoRoot, "dist");
    public string PacksJson => Path.Combine(GamesRoot, "packs.json");
    public string SchemaJson => Path.Combine(GamesRoot, "_schema", "game.schema.json");
    public string RootManifest => Path.Combine(GamesRoot, "manifest.json");

    public string BuildAllScript => Path.Combine(ToolsRoot, "build_all_content_pcks.py");
    public string GenPresetsScript => Path.Combine(ToolsRoot, "gen_content_presets.py");

    public string Python { get; }
    public string Godot { get; }
    public string SigningKey { get; }
    public string ReleaseRepo { get; }

    public RepoContext(IOptions<AdminOptions> options, IHostEnvironment env)
    {
        var o = options.Value;
        RepoRoot = string.IsNullOrWhiteSpace(o.RepoPath)
            ? ResolveRepoRoot(env.ContentRootPath)
            : Path.GetFullPath(o.RepoPath);

        Python = string.IsNullOrWhiteSpace(o.Python) ? "python" : o.Python;

        var envGodot = Environment.GetEnvironmentVariable("GODOT");
        Godot = !string.IsNullOrWhiteSpace(envGodot) ? envGodot : o.Godot;

        SigningKey = string.IsNullOrWhiteSpace(o.SigningKey)
            ? Path.GetFullPath(Path.Combine(RepoRoot, "..", "cpc-publish", "content_signing_priv.pem"))
            : Path.GetFullPath(o.SigningKey);

        ReleaseRepo = o.ReleaseRepo;
    }

    /// <summary>Walk up from the app's content root until a folder carries both
    /// <c>games/</c> and <c>project.godot</c> — that's the content repo root. The
    /// admin tool lives at <c>&lt;repo&gt;/admin</c>, so the parent is the usual hit.</summary>
    private static string ResolveRepoRoot(string start)
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "games"))
                && File.Exists(Path.Combine(dir.FullName, "project.godot")))
                return dir.FullName;
            dir = dir.Parent;
        }
        // Fallback: parent of the content root (admin/ → repo).
        return Directory.GetParent(start)?.FullName ?? start;
    }

    public bool SigningKeyExists => File.Exists(SigningKey);
    public bool GodotExists => File.Exists(Godot);
}
