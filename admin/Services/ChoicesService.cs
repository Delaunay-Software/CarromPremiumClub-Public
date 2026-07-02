using Microsoft.Extensions.Options;

namespace CarromContentAdmin.Services;

/// <summary>
/// Supplies closed-choice option lists for manifest fields whose values come from a
/// known set rather than free text — currently PbrTextureSetRegistry ids (wood /
/// metal / stone texture sets). The list is the configured engine seeds unioned with
/// any texture-set folders shipped inside the content tree.
/// </summary>
public sealed class ChoicesService
{
    private readonly RepoContext _repo;
    private readonly string[] _known;
    private IReadOnlyList<string>? _textureSets;

    public ChoicesService(RepoContext repo, IOptions<AdminOptions> options)
    {
        _repo = repo;
        _known = options.Value.KnownTextureSets ?? System.Array.Empty<string>();
    }

    public IReadOnlyList<string> TextureSets()
    {
        if (_textureSets is not null) return _textureSets;
        var set = new SortedSet<string>(_known, StringComparer.OrdinalIgnoreCase);
        // Union any texture-set folders shipped under the content tree (games-local sets).
        if (Directory.Exists(_repo.GamesRoot))
            foreach (var dir in Directory.EnumerateDirectories(_repo.GamesRoot, "textures", SearchOption.AllDirectories))
                if (Path.GetFileName(Path.GetDirectoryName(dir)) == "assets")
                    foreach (var sub in Directory.EnumerateDirectories(dir))
                        set.Add(Path.GetFileName(sub));
        return _textureSets = set.ToList();
    }
}
