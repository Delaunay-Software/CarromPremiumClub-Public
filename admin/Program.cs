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
builder.Services.AddSingleton<AssetService>();
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

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
