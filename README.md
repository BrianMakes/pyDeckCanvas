# pyDeckCanvas

A desktop app for working with card spreads of any kind — games, oracles, tarot, prompt decks, flashcards, and custom collections. Draw cards, arrange them on a canvas, browse and select specific cards, and save your spreads as images or reloadable state.

## Setup

Need Updated Setup Instructions

```bash
pip install -r requirements.txt
python main.py
```

---

## Adding Your Cards

Put each deck collection in its own folder under `decks/`. Piles can be subfolders or the root folder itself:

```
decks/
├── My Homebrew Deck (With Sub Decks)/             <- collection (groups piles in the sidebar)
│   ├── deck.json                   <- optional pile order config
│   ├── Pile1/
│   │   ├── card01.jpeg
│   │   └── back.jpeg               <- pile-level card back
│   ├── Pile2/
│   ├── AnotherPile/
│   ├── PileFour/
│   └── ...
├── My Homebrew Deck (Single Deck)/               <- flat collection (root folder = one pile)
│   ├── card01.png
│   └── back.png
└── My Homebrew Deck (Double Sided)/             <- double-sided cards (no back.png needed)
    └── SubDeck 1/
        ├── 0000_01F.jpeg           <- front (filename ends in F)
        ├── 0000_01B.jpeg           <- matching back (same name, ends in B)
        └── PileTop.png             <- optional sidebar thumbnail
        ├── PileTwo/
│   └── ...
```

- Card images: square **PNG / JPG / WebP** (recommended: 500×500 px)
- Each subfolder with images becomes one pile, grouped under its parent collection
- `back.png` (or `.jpg` / `.jpeg` / `.webp`) sets the pile-level card back
- **Double-sided**: pair `*F.ext` + `*B.ext` files — the absence of `back.*` triggers this mode
- `PileTop.{ext}` is displayed as the sidebar thumbnail; it is never drawn as a card

### deck.json — Custom pile order

Add a `deck.json` file inside a collection folder to control the order piles appear in the sidebar:

```json
{ "piles": ["Explorer", "Power", "System", "Threat", "World"] }
```

`"."` refers to cards in the collection root itself. Piles not listed are appended alphabetically.
Use **Save Deck Sort** in the Session Panel to write the current pile order back to `deck.json`.

---

## Interface Overview

```
┌──────────────┬──────────────────────────────────────┬───────────────┐
│  Deck        │                                      │  Session      │
│  Sidebar     │           Canvas                     │  Panel        │
│              │     (cards, zoom, pan)               │               │
│  [pile list] │                                      │  [optional]   │
│              │                                      │               │
│  [buttons]   │                                      │               │
└──────────────┴──────────────────────────────────────┴───────────────┘
```

### Deck Sidebar

The sidebar shows all active piles. Buttons run bottom-to-top:

| Button | Action |
|---|---|
| **▶ / Options** | Toggle Session Panel / Options panel |
| **Reset** | Clear the table, discard pile, and trash; reshuffle all piles |
| **Browse Pile...** | Open the card browser for the focused pile |
| **Draw All** | Draw one card from each selected pile |
| **Draw Random** | Draw one card from the combined pool of selected piles (weighted by pile size) |
| **Choose Decks...** | Activate or deactivate deck collections |

### Pile List

- Collections show a `v` / `>` header — click to collapse / expand
- **Click** a pile row to focus it (used by Browse Pile)
- **Ctrl+click** a pile row to add/remove it from the draw selection
- **Right-click** a pile row to draw directly from that pile
- **Ctrl+Alt+click** a pile — selects/deselects all piles sharing the same name across collections
- **Ctrl+Alt+right-click** a pile — draws one card from the combined pool of all matching piles
- **Drag** a pile row to reorder it within its collection
- **Drag a collection header** to reorder the entire group
- **Ctrl+click a collection header** — collapse/expand all collections at once

---

## Session Panel (▶)

Click **▶** in the lower-left to open the Session Panel. It has three sections:

### SPREADS
Save and load the complete session state: card positions, zoom, pan, active decks, discard pile, and the draw-pile order of every deck.

| Button | Action |
|---|---|
| **Save Spread...** | Save the full session state to a `.json` file in `spreads/` |
| **Load Spread...** | Restore a previously saved spread (restores all state) |

> `Ctrl+Shift+S` / `Ctrl+O` also save/load layout files (any location; table cards only).

### DECK LISTS
Save and restore which deck collections are active.

| Button | Action |
|---|---|
| **Save Deck List...** | Save the current set of active collections (and their collapsed/expanded state) to `loadouts/` |
| **Load Deck List...** | Load a saved deck list. When **Reset on Load** is off (default), only adds missing decks additively. When on, returns all cards to piles and replaces the active set. Collapsed/expanded state is restored either way. |
| **Save Deck Sort** | Write the current pile order to each collection's `deck.json` |

### ARROWS
Draw annotation arrows on the canvas to mark connections or highlight cards.

| Control | Description |
|---|---|
| **+ Add Arrow** | Toggle arrow placement mode (or press `,`) |
| **→ / ↔** | Arrowhead at tail end only / at both ends |
| **Plain / Rope / Chain** | Arrow shaft style |
| Color swatches | Set arrow color for new arrows |
| **− / + (weight)** | Adjust weight for new arrows (session only; default set in Options) |

Arrow placement: click-drag on the canvas to set start and end points. Right-click or press `,` / `Esc` to cancel.

### DISCARD
The discard pile sits at the bottom of the Session Panel. Cards dropped onto the panel while it is open are sent to the discard pile.

- **Left-click** the discard area to include/exclude it from random draws
- **Left-click** the card thumbnail to drag the top discard card onto the canvas
- **Right-click** the card thumbnail to return the top card to the table (face-up)
- **Browse Discard** — open the discard browser; double-click to move a card back to the table

---

## Options Panel

Click **Options** in the sidebar to open the Options panel.

| Toggle | Default | Description |
|---|---|---|
| PileTop Thumbnail | Off | Show `PileTop` image as thumbnail for double-sided piles |
| Draw Face Down | Off | Cards start face-down; double-click or press `F` to reveal |
| Random Rotation | Off | Each drawn card gets a random 0/90/180/270° rotation |
| Tuck (place under) | Off | New cards go *under* existing cards (hold `Ctrl` on drop to toggle per-card) |
| Snap to Grid | Off | Snapping on drop; `−`/`+` buttons adjust grid size (25–500 px) |
| Default W / Default H | 500 / 500 | Global fallback card dimensions for piles without a `deck.json`; `−`/`+` adjust in 25 px steps (100–2000), `R` resets to 500 |
| Save w/ Background | Off | Include the background image/color when exporting PNG |
| Ctrl+S → Clipboard | Off | When on, `Ctrl+S` copies the PNG to the clipboard instead of saving to a file |
| Arrow Weight | 3 | Default starting weight for new arrows (1–10); adjust per-session in the Session Panel |
| Confirm Delete | On | Show a confirmation dialog before permanently removing a card |
| Delete → Discard | Off | `Delete` key sends cards to the discard pile instead of removing them |
| Keep Discard Orient. | Off | Preserve card rotation and face when discarding |
| Browse Dim | 100 | Darkness of the overlay on already-drawn cards in the Browse grid (0 = no dim, 200 = nearly black) |
| Browse: Shuf. Order | Off | Browse overlay shows available cards in the current draw-pile order |
| Dot Grid | Off | Show a subtle dot grid on the canvas background |
| Reset on Load | Off | When loading a loadout: return all table and discard cards to their piles, then replace active decks. When **off**: loading a loadout only *adds* missing decks — nothing is removed or cleared |
| Warn Before Load | On | Show a confirmation dialog before the reset (only relevant when Reset on Load is on) |

Action buttons:

- **📄 Import PDF Deck** — PDF import is still in development
- **❓ Controls** — Open the scrollable Controls help overlay
- **🎨 Background...** — Open the background picker (image, tiled/centered, or solid color)
- **📂 Startup Loadout...** — Pick a loadout file to apply automatically each time the app starts; click the ✖ button beside it to clear

---

## Controls

### Card Interaction

| Action | Effect |
|---|---|
| **Click** a card | Select it (clears other selection) |
| **Double-click** a card | Flip it (face-up ↔ face-down) |
| **Ctrl+click** a card | Toggle that card in/out of the selection |
| **Drag** a card | Move it — does not change selection |
| **Drag** a selected card | Moves all selected cards together |

### Card Actions (selection or hovered card)

| Key | Action |
|---|---|
| `D` | Draw one card from selected piles (weighted by pile size) |
| `A` | Draw one card from *each* selected pile |
| `F` | Flip card face-up / face-down |
| `T` | Rotate card 180° |
| `R` / `E` | Rotate card clockwise / counter-clockwise 90° |
| `Y` / `U` | Rotate card 45° clockwise / reset to 0° |
| `V` | Random rotation (0 / 90 / 180 / 270°) |
| `C` | Duplicate card(s) — copy inherits face/rotation, placed 20 px offset, auto-selected |
| `Z` | Return card to its source pile |
| `X` | Send card to the discard pile |
| `Delete` | Remove card (behavior set by Options: confirm / discard) |
| `]` / `[` | Move card forward / backward in z-order |
| `Home` / `End` | Bring to top / send to bottom of z-order |

All card actions apply to **all selected cards** if a selection exists, or to the hovered card otherwise.

### Multi-Select

| Key / Action | Effect |
|---|---|
| `Ctrl+A` | Select all cards on the table |
| `Esc` | Clear the selection |
| Drag on empty canvas | Box-select cards in the drawn region |
| `Ctrl+drag` on canvas | Additive box-select (adds to existing selection) |

### Bulk Table Actions

| Key | Action |
|---|---|
| `Ctrl+Z` | Return **all** table cards to their source piles |
| `Ctrl+X` | Send **all** table cards to the discard pile |
| `Ctrl+Delete` | Delete **all** table cards and arrows (per Options settings) |

### Drop Modifiers

| Modifier | Effect |
|---|---|
| `Ctrl` held on drop | Toggle tuck mode for that drop only |
| `Alt` held on drop | Toggle snap-to-grid for that drop only |

### Arrow Annotations

| Key / Action | Effect |
|---|---|
| `,` | Toggle arrow placement mode |
| Click-drag on canvas | Draw a new arrow (start → end point) |
| Right-click | Cancel placement mode |
| Drag arrow body | Move the arrow |
| Drag endpoint | Resize / reposition that end |
| `Ctrl+A` | Select all cards *and* arrows |
| Box-select | Includes arrows whose endpoints fall in the region |
| `X` / `Delete` | Remove hovered or selected arrows |
| Drag selected card | Moves all selected arrows with it |

Arrow styles, color, and weight are set in the Session Panel (▶). Arrows are saved and restored with **Save/Load Spread** and included in **Ctrl+S** PNG export.

### Canvas Navigation

| Action | Key / Mouse |
|---|---|
| Zoom | Scroll wheel on canvas |
| Pan | Middle-click drag or right-click drag |

### File & Session

| Key | Action |
|---|---|
| `Ctrl+S` | Export current layout as a PNG image (or copy to clipboard — see Options) |
| `Ctrl+Shift+S` | Save layout state to a JSON file |
| `Ctrl+O` | Load layout state from a JSON file |
| `?` | Toggle the Controls help overlay |

---

## Tips

- **Weighted draw**: `D` picks from the combined pool of all selected piles so every *card* (not every *pile*) has equal probability — larger piles contribute more draws proportionally.
- **Browse mode**: Focus a pile, click **Browse Pile...** to see all cards in a scrollable grid. Double-click to add a card to the table. Ctrl+scroll to resize thumbnails.
- **Duplicate**: Press `C` to copy the hovered or selected card(s). Each copy inherits the original's face, rotation, and size, is placed 20 px offset, and is immediately selected so you can drag it into position.
- **Group drag**: Ctrl+click or box-select multiple cards, then drag any one to move the whole group while preserving their layout.
- **Reordering piles**: Drag pile rows within a collection to reorder. Drag a collection header to reorder entire groups. Click **Save Deck Sort** in the Session Panel to persist the order.
- **Deck Lists**: Save which deck collections are active as a named deck list. Load it via the Session Panel, or set a startup deck list in Options (📂 Startup Loadout...) to apply it automatically on launch.
- **Spreads**: Save the full session state (cards, positions, zoom, active decks, discard pile, deck draw order) to `spreads/` and reload it any time from the Session Panel.
- **Snap to grid**: Enable in Options, then use Alt+drop to toggle grid snapping per-card drop.
- **Tuck mode**: Place new cards under existing ones — useful when building a stack in order. Ctrl+drop overrides tuck mode for a single drop.
- **Background**: Choose a solid color or a background image from `tables/` via Options → Background. Images can be tiled or centered.
- **Discard pile**: Toggle the discard area in the Session Panel to include it in random draws. Drag the top card thumbnail back to the canvas, or browse the full discard pile.
- **Arrows**: Press `,` or click **+ Add Arrow** in the Session Panel, then click-drag on the canvas. Choose Plain, Rope, or Chain style; pick a color swatch; and adjust weight with `−`/`+`. Arrows are included in spread saves and PNG exports. Set the default weight in Options.

---

## Double-Sided Decks

1. Name front images with a trailing `F`: `0001F.png`, `0002F.png`, ...
2. Name matching backs with a trailing `B`: `0001B.png`, `0002B.png`, ...
3. Do **not** include a `back.png` — its absence triggers double-sided mode
4. Optionally add `PileTop.png` as a cover image shown in the sidebar

Each card's back is its individual paired file. Double-click or press `F` while hovering to flip front/back.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**. See [LICENSE](LICENSE) for the full text.

In plain terms:
- You are free to use, modify, and share this software
- If you distribute a modified version, you must also release it under GPL-3.0 and make the source available
- Commercial use is permitted, but you cannot distribute closed-source derivatives

**Card assets are not covered by this license.** Any card images, decks, or artwork you use with this app are subject to their own respective licenses and copyrights. Nothing in the GPL-3.0 license affects your rights or obligations regarding those assets.

This project uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL-3.0) for PDF extraction, [pygame](https://www.pygame.org/) (LGPL-2.1), and [Pillow](https://python-pillow.org/) (HPND). GPL-3.0 is compatible with all of these.