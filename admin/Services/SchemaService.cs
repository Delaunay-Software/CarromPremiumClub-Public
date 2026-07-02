using System.Text.Json.Nodes;

namespace CarromContentAdmin.Services;

/// <summary>
/// One node of the parsed manifest JSON Schema (draft-07 subset): type(s),
/// description, enum, pattern, numeric bounds, nested object properties, and array
/// item schema. Drives the strict 1-to-1 manifest form — every field renders from
/// its schema entry (label, help text, type-appropriate input, allowed values).
/// </summary>
public sealed class SchemaNode
{
    public string Key = "";
    public List<string> Types = new();
    public string? Description;
    public string? DefaultHint;   // parsed from the description ("Default X" / "Defaults to X")
    public List<string>? Enum;
    public string? Pattern;
    public double? Min, Max;
    public bool AdditionalProperties;
    public Dictionary<string, SchemaNode> Properties = new();
    public SchemaNode? Items;

    public bool Nullable => Types.Contains("null");
    public string PrimaryType => Types.FirstOrDefault(t => t != "null") ?? "string";
    public bool IsObject => PrimaryType == "object" || Properties.Count > 0;
    public bool IsArray => PrimaryType == "array";
    public bool IsBool => PrimaryType == "boolean";
    public bool IsNumber => PrimaryType is "number" or "integer";
    public bool IsColor => Pattern is { } p && p.Contains("#") && p.Contains("6");

    /// <summary>Field whose value is a PbrTextureSetRegistry id (wood/metal/stone set) —
    /// rendered as a dropdown of known texture sets. Detected from the schema description
    /// so it needs no per-key hardcoding.</summary>
    public bool IsTextureSet => Description is { } d && d.Contains("PbrTextureSetRegistry");

    /// <summary>Asset-path field by the engine's suffix convention (FlavourPath) plus
    /// the well-known bare keys. Rendered as a conventional-path asset picker.</summary>
    public bool IsAssetPath =>
        PrimaryType == "string" && !IsColor && (
            Key.EndsWith("_dir") || Key.EndsWith("_texture") || Key.EndsWith("_image")
            || Key.EndsWith("_path") || Key.EndsWith("_mesh") || Key.EndsWith("_glb")
            || Key.EndsWith("_png") || Key.EndsWith("_icon")
            || Key is "poster" or "backdrop" or "card_texture" or "white_mesh"
                   or "black_mesh" or "queen_mesh");
}

/// <summary>Loads + parses games/_schema/game.schema.json into a navigable tree,
/// resolving internal <c>#/definitions/*</c> $refs. Cached for the app lifetime
/// (the schema is static content).</summary>
public sealed class SchemaService
{
    private readonly RepoContext _repo;
    private SchemaNode? _root;
    private JsonObject? _defs;

    public SchemaService(RepoContext repo) => _repo = repo;

    public SchemaNode Root => _root ??= Load();

    private SchemaNode Load()
    {
        var text = File.ReadAllText(_repo.SchemaJson);
        var obj = JsonNode.Parse(text)!.AsObject();
        _defs = obj["definitions"]?.AsObject();
        return Parse("", obj, depth: 0);
    }

    private SchemaNode Parse(string key, JsonObject o, int depth)
    {
        // Resolve a $ref against #/definitions/<name> before reading anything else.
        if (o["$ref"]?.GetValue<string>() is { } refPath && depth < 12)
        {
            var name = refPath.Split('/').Last();
            if (_defs?[name] is JsonObject target)
                o = target;
        }

        var node = new SchemaNode { Key = key, Description = o["description"]?.GetValue<string>() };
        node.DefaultHint = ExtractDefault(node.Description);

        // type: string | [string, ...]
        switch (o["type"])
        {
            case JsonValue v when v.TryGetValue<string>(out var t): node.Types.Add(t); break;
            case JsonArray arr:
                foreach (var it in arr) if (it?.GetValue<string>() is { } s) node.Types.Add(s);
                break;
        }

        if (o["enum"] is JsonArray en)
            node.Enum = en.Select(e => e?.ToString() ?? "").ToList();
        node.Pattern = o["pattern"]?.GetValue<string>();
        if (o["minimum"] is JsonValue mn && mn.TryGetValue<double>(out var mnv)) node.Min = mnv;
        if (o["maximum"] is JsonValue mx && mx.TryGetValue<double>(out var mxv)) node.Max = mxv;
        node.AdditionalProperties = o["additionalProperties"]?.GetValue<bool>() ?? false;

        if (o["properties"] is JsonObject props)
        {
            if (!node.Types.Contains("object")) node.Types.Add("object");
            foreach (var kv in props)
                if (kv.Value is JsonObject childObj)
                    node.Properties[kv.Key] = Parse(kv.Key, childObj, depth + 1);
        }

        if (o["items"] is JsonObject items)
        {
            if (!node.Types.Contains("array")) node.Types.Add("array");
            node.Items = Parse(key + "[]", items, depth + 1);
        }

        return node;
    }

    /// <summary>Pull a short default out of a description ("Default 1.0", "Defaults to
    /// the flavour id", "Default true (…)") for placeholder hint text. Null if none.</summary>
    private static string? ExtractDefault(string? desc)
    {
        if (string.IsNullOrEmpty(desc)) return null;
        var m = System.Text.RegularExpressions.Regex.Match(
            desc, @"Default(?:s to)?\s+'?([^.'()]+?)'?\s*[.(]");
        if (!m.Success) return null;
        var val = m.Groups[1].Value.Trim();
        return val.Length is > 0 and <= 40 ? val : null;
    }

    /// <summary>Humanise a snake_case key for a field label ("card_texture" → "Card texture").</summary>
    public static string Label(string key)
    {
        if (string.IsNullOrEmpty(key)) return key;
        var words = key.Replace('_', ' ').Trim();
        return char.ToUpperInvariant(words[0]) + words[1..];
    }

    /// <summary>A cockpit "Section" zone — a named group of top-level manifest keys.
    /// <see cref="Fields"/> is the schema node(s) rendered when the section is active;
    /// <see cref="Keys"/> is the top-level manifest keys it owns (for dirty roll-up).</summary>
    public sealed record Section(string Id, string Title, IReadOnlyList<SchemaNode> Fields, IReadOnlyList<string> Keys);

    /// <summary>Split the schema root into cockpit sections: one "Basics" group holding
    /// every scalar/array/enum top-level field, then one section per top-level OBJECT
    /// (frame, coins, mechanic, economy, audio, …). The UI appends a synthetic
    /// "Assets" section. Ordering: Basics first, then objects in schema order.</summary>
    public IReadOnlyList<Section> Sections()
    {
        var basics = new List<SchemaNode>();
        var sections = new List<Section>();
        foreach (var p in Root.Properties.Values)
        {
            if (p.IsObject) sections.Add(new Section(p.Key, Label(p.Key), new[] { p }, new[] { p.Key }));
            else basics.Add(p);
        }
        sections.Insert(0, new Section("_basics", "Basics", basics, basics.Select(b => b.Key).ToList()));
        return sections;
    }
}
