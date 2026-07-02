using CarromContentAdmin.Components;
using CarromContentAdmin.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

// Content-admin services.
builder.Services.Configure<AdminOptions>(builder.Configuration.GetSection(AdminOptions.SectionName));
builder.Services.AddSingleton<RepoContext>();
builder.Services.AddSingleton<ProcessRunner>();
builder.Services.AddSingleton<GamesTreeService>();
builder.Services.AddSingleton<SchemaService>();
builder.Services.AddSingleton<ChoicesService>();
builder.Services.AddSingleton<AssetService>();
builder.Services.AddSingleton<EditSession>();
builder.Services.AddSingleton<PackMap>();
builder.Services.AddSingleton<GitService>();
builder.Services.AddSingleton<PublishService>();
builder.Services.AddHttpClient<GitHubReleaseService>();

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}

app.UseStaticFiles();
app.UseAntiforgery();

// Serve a content asset for in-form image previews. Sandboxed strictly under games/
// (no traversal outside the tree). Path is games-relative, e.g. /asset/casino/assets/images/poster.png.
app.MapGet("/asset/{**relPath}", (string relPath, RepoContext repo) =>
{
    var full = Path.GetFullPath(Path.Combine(repo.GamesRoot, relPath.Replace('/', Path.DirectorySeparatorChar)));
    var root = Path.GetFullPath(repo.GamesRoot);
    if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
        return Results.NotFound();
    var ext = Path.GetExtension(full).ToLowerInvariant();
    var mime = ext switch
    {
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".webp" => "image/webp",
        ".svg" => "image/svg+xml",
        _ => "application/octet-stream",
    };
    return Results.File(full, mime);
});

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
