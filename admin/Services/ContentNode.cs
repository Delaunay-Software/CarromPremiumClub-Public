namespace CarromContentAdmin.Services;

/// <summary>
/// One node in the recursive games/ content tree. A node with a <c>rule_set</c> in
/// its own manifest is a playable LEAF (flavour / mini-game); a node without one is
/// a GROUP the carousel drills into. Mirrors the engine's FlavourLoader.ScanTree
/// classification so the admin view matches what the game actually surfaces.
/// </summary>
public sealed class ContentNode
{
    /// <summary>Folder name (the node id), e.g. "casino", "icf".</summary>
    public required string Id { get; init; }

    /// <summary>Path relative to games/, e.g. "casino/games/poker". "" for the root.</summary>
    public required string RelPath { get; init; }

    /// <summary>Absolute path to this node's manifest.json.</summary>
    public required string ManifestPath { get; init; }

    /// <summary>Absolute path to this node's folder.</summary>
    public required string Dir { get; init; }

    /// <summary>This node's OWN manifest rule_set ("icf"/"casual"/"arcade"), or null.
    /// Presence ⇒ leaf; absence ⇒ group. NOT inherited (matches the engine rule).</summary>
    public string? RuleSet { get; init; }

    /// <summary>Display name from the manifest (name/title), falling back to Id.</summary>
    public required string DisplayName { get; init; }

    public bool IsLeaf => RuleSet is not null;

    public List<ContentNode> Children { get; } = new();

    /// <summary>True when this node ships a poster.png (section/hero card).</summary>
    public bool HasPoster { get; init; }
}
