using System.Text.Json;
using System.Text.Json.Nodes;

namespace CarromContentAdmin.Services;

/// <summary>
/// Holds the in-progress manifest edits for the cockpit so switching Game / Section
/// zones never loses changes, and so dirty state can be shown at every level
/// (field → section → game). One working <see cref="JsonObject"/> per node plus a
/// snapshot of the on-disk original; dirtiness is a value comparison against the
/// snapshot. Singleton — this is a single-operator local tool.
/// </summary>
public sealed class EditSession
{
    private readonly GamesTreeService _tree;
    public EditSession(GamesTreeService tree) => _tree = tree;

    private sealed class Entry
    {
        public required JsonObject Working;
        public required string OriginalCanonical;
        public required string ManifestPath;
    }

    private readonly Dictionary<string, Entry> _entries = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>Working model for a node, loaded (and cached) from disk on first ask.
    /// Subsequent edits mutate this same object. Returns null if the manifest is
    /// malformed (caller falls back to the raw JSON editor).</summary>
    public JsonObject? Working(ContentNode node)
    {
        if (_entries.TryGetValue(node.RelPath, out var e)) return e.Working;
        JsonObject? obj;
        try { obj = JsonNode.Parse(_tree.ReadRaw(node.ManifestPath))?.AsObject(); }
        catch { return null; }
        if (obj is null) return null;
        _entries[node.RelPath] = new Entry
        {
            Working = obj,
            OriginalCanonical = Canonical(obj),
            ManifestPath = node.ManifestPath,
        };
        return obj;
    }

    /// <summary>Discard cached working edits for a node (revert to disk on next load).</summary>
    public void Forget(string relPath) => _entries.Remove(relPath);

    public bool IsNodeDirty(ContentNode node)
        => _entries.TryGetValue(node.RelPath, out var e) && Canonical(e.Working) != e.OriginalCanonical;

    /// <summary>Dirty at a single top-level manifest key (a Section or Basics field).</summary>
    public bool IsKeyDirty(ContentNode node, string key)
    {
        if (!_entries.TryGetValue(node.RelPath, out var e)) return false;
        var orig = JsonNode.Parse(e.OriginalCanonical)?.AsObject();
        return NodeJson(e.Working[key]) != NodeJson(orig?[key]);
    }

    /// <summary>Any of the given top-level keys dirty (a Section groups several).</summary>
    public bool IsAnyKeyDirty(ContentNode node, IEnumerable<string> keys)
        => keys.Any(k => IsKeyDirty(node, k));

    /// <summary>Persist the working model to disk (LF-normalised, validated) and reset
    /// the dirty snapshot. Returns null on success, else the validation error.</summary>
    public string? Save(ContentNode node)
    {
        if (!_entries.TryGetValue(node.RelPath, out var e)) return null;
        var text = e.Working.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        var err = _tree.SaveRaw(e.ManifestPath, text);
        if (err is null) e.OriginalCanonical = Canonical(e.Working);
        return err;
    }

    // ── Canonicalisation (order-independent value comparison) ────────────────
    private static string Canonical(JsonNode? node) => NodeJson(SortKeys(node));

    private static string NodeJson(JsonNode? n)
        => n?.ToJsonString() ?? "null";

    /// <summary>Deep copy with object keys sorted so key-reorder isn't seen as a change.</summary>
    private static JsonNode? SortKeys(JsonNode? node)
    {
        switch (node)
        {
            case JsonObject o:
                var sorted = new JsonObject();
                foreach (var kv in o.OrderBy(k => k.Key, StringComparer.Ordinal))
                    sorted[kv.Key] = SortKeys(kv.Value);
                return sorted;
            case JsonArray a:
                var arr = new JsonArray();
                foreach (var it in a) arr.Add(SortKeys(it));
                return arr;
            case JsonValue v:
                return JsonNode.Parse(v.ToJsonString());
            default:
                return null;
        }
    }
}
