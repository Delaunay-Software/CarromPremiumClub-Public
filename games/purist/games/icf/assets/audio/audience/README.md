# ICF audience audio — drop-in guide

`AudioManager` scans these folders at runtime and plays a **random** clip from
the matching pool (any filenames; `.mp3` / `.ogg` / `.wav`). Drop the sourced
Pixabay clips straight into the right folder — no code or manifest change needed.
Audience playback self-gates on pool presence: shipping any clips here turns the
audience on for this flavour; an empty tree leaves it silent.

| Folder | When it plays | What to source (Pixabay search) |
|---|---|---|
| `idle/` | Random ambient crowd between shots (idle scheduler) | "crowd cough", "audience murmur", "throat clear", "chair shuffle", "polite crowd ambience" — short (1–4 s), sparse |
| `reactions/` | One-off on notable gameplay events (`PlayAudienceReaction`) | "crowd ooh", "audience gasp", "aww disappointed", "ohh surprise" — short (1–2 s) |
| `applause/polite/` | Grade 1–2 shots (a double / covered queen) | "polite applause", "light clapping", "small applause" — 2–4 s |
| `applause/strong/` | Grade 3 shots | "applause", "crowd clapping medium" — 3–5 s |
| `applause/roaring/` | Grade 4+ (multi-pocket / winning shot) | "big applause cheer", "crowd cheering ovation", "stadium applause" — 4–6 s |

Notes:
- Multiple files per folder is encouraged — the engine picks randomly with no
  immediate repeat, so 3–6 clips per pool keeps it from sounding looped.
- Keep clips loudness-matched and trimmed to a clean head/tail (no long silence).
- `applause/` (flat, no tier subfolder) is a fallback if a tier folder is empty.
- **Licensing:** verify each track's Pixabay Content License before committing;
  keep an attribution note here if any track requires it.
