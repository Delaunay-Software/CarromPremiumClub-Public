namespace CarromContentAdmin.Services;

/// <summary>
/// Bound from the "Admin" section of appsettings.json. Every path is optional —
/// <see cref="RepoContext"/> auto-resolves the games-repo root (the folder holding
/// <c>games/</c> + <c>project.godot</c>) and derives sensible defaults, so a fresh
/// clone works with no config. Override any value in appsettings when a tool lives
/// somewhere non-standard.
/// </summary>
public sealed class AdminOptions
{
    public const string SectionName = "Admin";

    /// <summary>Explicit games-repo root. Empty → auto-resolve by walking up from
    /// the app's content root until a folder with games/ + project.godot is found.</summary>
    public string RepoPath { get; set; } = "";

    /// <summary>Python interpreter used to run tools/*.py. Default "python" (on PATH).</summary>
    public string Python { get; set; } = "python";

    /// <summary>Godot mono console executable for headless pack export. Falls back to
    /// the GODOT env var, then this value.</summary>
    public string Godot { get; set; } =
        @"C:\Users\User\Godot\Godot_v4.7-stable_mono_win64\Godot_v4.7-stable_mono_win64_console.exe";

    /// <summary>ECDSA-P256 private signing key (PEM). Default is the sibling
    /// cpc-publish/ workspace next to the repo; overridable.</summary>
    public string SigningKey { get; set; } = "";

    /// <summary>GitHub repo (owner/name) the signed packs publish to as Release assets.</summary>
    public string ReleaseRepo { get; set; } = "Delaunay-Software/CarromPremiumClub-Public";
}
