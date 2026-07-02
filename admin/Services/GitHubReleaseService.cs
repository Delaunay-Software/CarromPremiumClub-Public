using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace CarromContentAdmin.Services;

/// <summary>
/// Publishes the signed content packs as GitHub Release assets via the REST API —
/// no dependency on the `gh` CLI. ContentSync pulls from the repo's "latest"
/// release, so each publish creates a fresh release (marked latest) and uploads
/// every dist/ artifact. Auth is a PAT with repo scope from the GITHUB_TOKEN /
/// GH_TOKEN env var (or the AdminOptions/appsettings override).
/// </summary>
public sealed class GitHubReleaseService
{
    private readonly RepoContext _repo;
    private readonly HttpClient _http;

    public GitHubReleaseService(RepoContext repo, HttpClient http)
    {
        _repo = repo;
        _http = http;
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("CarromContentAdmin/1.0");
        _http.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
        _http.DefaultRequestHeaders.Add("X-GitHub-Api-Version", "2022-11-28");
    }

    public static string? ResolveToken() =>
        Environment.GetEnvironmentVariable("GITHUB_TOKEN")
        ?? Environment.GetEnvironmentVariable("GH_TOKEN");

    public bool HasToken => !string.IsNullOrEmpty(ResolveToken());

    /// <summary>Files ContentSync expects as release assets: every pack, its
    /// signature, and the signed pack index.</summary>
    public IReadOnlyList<string> DistAssets()
    {
        if (!Directory.Exists(_repo.DistRoot)) return Array.Empty<string>();
        return Directory.EnumerateFiles(_repo.DistRoot)
            .Where(f => f.EndsWith(".pck") || f.EndsWith(".pck.sig")
                     || Path.GetFileName(f) is "packs-index.json" or "packs-index.json.sig")
            .OrderBy(f => f)
            .ToList();
    }

    /// <summary>Create a release (tag = <paramref name="tag"/>, marked latest) and
    /// upload every dist asset. Streams progress via <paramref name="onLine"/>.</summary>
    public async Task PublishAsync(string tag, string title, string body, Action<string> onLine, CancellationToken ct = default)
    {
        var token = ResolveToken();
        if (string.IsNullOrEmpty(token))
            throw new InvalidOperationException("No GitHub token — set GITHUB_TOKEN (repo scope) and restart.");
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);

        var assets = DistAssets();
        if (assets.Count == 0)
            throw new InvalidOperationException("dist/ has no packs to publish — build + sign first.");

        onLine($"Creating release '{tag}' on {_repo.ReleaseRepo} …");
        var createBody = new JsonObject
        {
            ["tag_name"] = tag,
            ["name"] = title,
            ["body"] = body,
            ["draft"] = false,
            ["prerelease"] = false,
            ["make_latest"] = "true",
        };
        var createResp = await _http.PostAsJsonAsync(
            $"https://api.github.com/repos/{_repo.ReleaseRepo}/releases", createBody, ct);
        var createText = await createResp.Content.ReadAsStringAsync(ct);
        if (!createResp.IsSuccessStatusCode)
            throw new InvalidOperationException($"create release failed ({(int)createResp.StatusCode}): {createText}");

        var created = JsonNode.Parse(createText)!;
        var releaseId = created["id"]!.GetValue<long>();
        // upload_url is templated: ".../assets{?name,label}" — strip the template.
        var uploadBase = created["upload_url"]!.GetValue<string>();
        var brace = uploadBase.IndexOf('{');
        if (brace >= 0) uploadBase = uploadBase[..brace];
        onLine($"Release #{releaseId} created. Uploading {assets.Count} assets …");

        int done = 0;
        foreach (var file in assets)
        {
            ct.ThrowIfCancellationRequested();
            var name = Path.GetFileName(file);
            await using var fs = File.OpenRead(file);
            using var content = new StreamContent(fs);
            content.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
            var up = await _http.PostAsync($"{uploadBase}?name={Uri.EscapeDataString(name)}", content, ct);
            if (!up.IsSuccessStatusCode)
            {
                var t = await up.Content.ReadAsStringAsync(ct);
                throw new InvalidOperationException($"upload {name} failed ({(int)up.StatusCode}): {t}");
            }
            onLine($"  ✓ {name} ({++done}/{assets.Count})");
        }
        onLine($"Published {done} assets to {_repo.ReleaseRepo} release '{tag}'.");
    }
}
