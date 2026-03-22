"""
deck.py  —  Deck loading with front/back card support.

A deck folder may contain:
  card_001.png … card_NNN.png   (fronts, from pdf_to_cards)
  back.png  (or .jpg/.jpeg/.webp)  (single card back image)

Double-sided piles (no back.* file, files named *F.ext / *B.ext):
  - Each card front (*F.*) is paired with its own back (*B.*)
  - PileTop.{ext} is an optional thumbnail used in the sidebar pile list

If a back image exists the deck operates in "face-down" mode:
  - Random draw shows the back until placed on table (then reveals front)
  - Cards drawn this session are removed from the draw pile (not the browse list)
  - Reshuffle resets the draw pile

If no back image the deck behaves as before (all fronts visible).

Deck discovery (load_decks):
  - Top-level folders under decks_root are "deck collections"
  - Each subfolder with card images becomes a separate pile
  - If the collection root itself has card images it also becomes a pile
  - Collections with no sub-piles and card images in root become a single flat pile
"""

import os
import json
import random
from card import Card

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
BACK_STEM = "back"
PILETOP_STEM = "piletop"


def _find_back(folder):
    """Return path to back.{png,jpg,jpeg,webp} in folder, or None."""
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        p = os.path.join(folder, f"back{ext}")
        if os.path.isfile(p):
            return p
    return None


def _find_piletop(folder):
    """Return path to PileTop.{png,jpg,jpeg,webp} in folder, or None."""
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        p = os.path.join(folder, f"PileTop{ext}")
        if os.path.isfile(p):
            return p
    return None


def _is_doublesided_pile(folder):
    """
    Return True if folder contains F/B paired card files and no back.* file.
    A folder is doublesided when at least one *F.ext file has a matching *B.ext.
    """
    if _find_back(folder):
        return False
    try:
        files = set(os.listdir(folder))
    except OSError:
        return False
    for f in files:
        stem, ext = os.path.splitext(f)
        if ext.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if stem[-1:].upper() != "F":
            continue
        back_file = stem[:-1] + "B" + ext
        if back_file in files or (stem[:-1] + "b" + ext) in files:
            return True
    return False


def _has_card_images(folder):
    """Return True if folder contains at least one card-front image file."""
    try:
        for f in os.listdir(folder):
            stem, ext = os.path.splitext(f)
            if (ext.lower() in SUPPORTED_EXTENSIONS
                    and stem.lower() not in (BACK_STEM, PILETOP_STEM)):
                return True
    except OSError:
        pass
    return False


def _load_collection_config(folder_path):
    """Load deck.json from a collection folder, return config dict or {}."""
    config_path = os.path.join(folder_path, "deck.json")
    if not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[deck.json] Warning: could not parse {config_path}: {e}")
        return {}


class Deck:
    def __init__(self, folder_path, display_name=None, parent_name=None,
                 card_w=500, card_h=500):
        self.folder_path     = folder_path
        self.collection_path = folder_path   # overridden by load_decks for sub-piles
        self.name            = os.path.basename(folder_path)
        self.display_name    = display_name or self.name
        self.parent_name     = parent_name  or self.name
        self.card_w          = card_w
        self.card_h          = card_h
        self.back_path       = None
        self.pile_top_path = None
        self.is_doublesided = False
        self._all_fronts   = []
        self._card_backs   = {}   # front_path → back_path (doublesided only)
        self._draw_pile     = []
        self._drawn_paths   = set()
        self._trashed_paths = set()
        self._browse_index  = 0
        self._load()

    def _load(self):
        self.back_path     = _find_back(self.folder_path)
        self.pile_top_path = _find_piletop(self.folder_path)
        self.is_doublesided = False

        if _is_doublesided_pile(self.folder_path):
            self.is_doublesided = True
            self._load_doublesided()
        else:
            self._load_standard()
        self.shuffle()

    def _load_standard(self):
        files = sorted([
            f for f in os.listdir(self.folder_path)
            if (os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
                and os.path.splitext(f)[0].lower() not in (BACK_STEM, PILETOP_STEM))
        ])
        self._all_fronts = [os.path.join(self.folder_path, f) for f in files]
        self._card_backs = {}

    def _load_doublesided(self):
        """Load F files as fronts; match each with its corresponding B file."""
        try:
            all_files = set(os.listdir(self.folder_path))
        except OSError:
            self._all_fronts = []
            self._card_backs = {}
            return

        fronts = []
        backs  = {}
        for f in sorted(all_files):
            stem, ext = os.path.splitext(f)
            if ext.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if stem.lower() in (BACK_STEM, PILETOP_STEM):
                continue
            if stem[-1:].upper() != "F":
                continue
            front_path = os.path.join(self.folder_path, f)
            # Find matching back — prefer uppercase B, fallback lowercase b
            back_path = None
            for b_char in ("B", "b"):
                candidate = stem[:-1] + b_char + ext
                if candidate in all_files:
                    back_path = os.path.join(self.folder_path, candidate)
                    break
            fronts.append(front_path)
            backs[front_path] = back_path

        self._all_fronts = fronts
        self._card_backs = backs

    def shuffle(self):
        self._draw_pile = [p for p in self._all_fronts if p not in self._trashed_paths]
        random.shuffle(self._draw_pile)
        self._drawn_paths = set()

    @property
    def has_back(self):
        return self.back_path is not None or self.is_doublesided

    @property
    def cards_remaining(self):
        return len(self._draw_pile)

    @property
    def cards_drawn(self):
        return len(self._drawn_paths)

    def draw_random(self, face_down=False):
        """
        Draw next card from shuffled pile.
        face_down=True shows the back until revealed; requires deck to have a back image.
        Reshuffles automatically when exhausted.
        """
        if not self._draw_pile:
            self.shuffle()

        front_path = self._draw_pile.pop()
        self._drawn_paths.add(front_path)
        name = _card_name(front_path, self.is_doublesided)

        # Resolve card-specific back (doublesided) or pile-level back (standard)
        card_back = (self._card_backs.get(front_path) if self.is_doublesided
                     else self.back_path)

        if card_back and face_down:
            card = Card(card_back, self.display_name, name)
            card.front_path   = front_path
            card.back_path    = card_back
            card.is_face_down = True
        else:
            card = Card(front_path, self.display_name, name)
            card.front_path   = front_path
            card.back_path    = card_back
            card.is_face_down = False

        card.card_w = self.card_w
        card.card_h = self.card_h
        card._surface_cache.clear()
        return card

    def draw_current_browse(self):
        """Return the currently browsed card (always face-up front). Non-destructive."""
        if not self._all_fronts:
            return None
        front_path = self._all_fronts[self._browse_index]
        name = _card_name(front_path, self.is_doublesided)
        card = Card(front_path, self.display_name, name)
        card.front_path  = front_path
        card.back_path   = (self._card_backs.get(front_path) if self.is_doublesided
                            else self.back_path)
        card.is_face_down = False
        card.card_w = self.card_w
        card.card_h = self.card_h
        card._surface_cache.clear()
        return card

    def card_back_for(self, front_path):
        """Return the back path for a given front path (works for both modes)."""
        if self.is_doublesided:
            return self._card_backs.get(front_path)
        return self.back_path

    def mark_drawn(self, front_path):
        """Mark a specific card as drawn (e.g. when picked directly from browse).
        Also restores the card if it was previously trashed."""
        self._trashed_paths.discard(front_path)
        self._drawn_paths.add(front_path)
        try:
            self._draw_pile.remove(front_path)
        except ValueError:
            pass  # already removed or was never in pile

    def mark_trashed(self, front_path):
        """Mark a card as permanently deleted (trashed) from this session."""
        self._drawn_paths.discard(front_path)
        self._trashed_paths.add(front_path)
        try:
            self._draw_pile.remove(front_path)
        except ValueError:
            pass

    def return_card(self, card):
        """Return a card to the draw pile (un-draws and un-trashes it)."""
        front = getattr(card, "front_path", card.image_path)
        in_drawn = front in self._drawn_paths
        in_trash = front in self._trashed_paths
        self._drawn_paths.discard(front)
        self._trashed_paths.discard(front)
        if in_drawn or in_trash:
            insert_at = random.randint(0, len(self._draw_pile))
            self._draw_pile.insert(insert_at, front)

    # ── Browse ────────────────────────────────────────────────────────────────

    def browse_next(self):
        if self._all_fronts:
            self._browse_index = (self._browse_index + 1) % len(self._all_fronts)

    def browse_prev(self):
        if self._all_fronts:
            self._browse_index = (self._browse_index - 1) % len(self._all_fronts)

    @property
    def browse_card_path(self):
        if not self._all_fronts:
            return None
        return self._all_fronts[self._browse_index]

    @property
    def browse_position(self):
        return self._browse_index + 1, len(self._all_fronts)

    def __len__(self):
        return len(self._all_fronts)


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _card_name(front_path, is_doublesided):
    """Return a display name for a card, stripping trailing F for doublesided."""
    stem = _stem(front_path)
    if is_doublesided and stem[-1:].upper() == "F":
        return stem[:-1]
    return stem


def _resolve_card_size(config, pile_key, default_card_w, default_card_h):
    """
    Resolve card dimensions for a pile using the fallback chain:
      pile-level (card_size.<pile_key>) → collection-level (card_width/card_height)
      → global default (default_card_w, default_card_h)
    """
    pile_size = config.get("card_size", {}).get(pile_key)
    if pile_size and len(pile_size) == 2:
        return int(pile_size[0]), int(pile_size[1])
    cw = int(config.get("card_width",  default_card_w))
    ch = int(config.get("card_height", default_card_h))
    return cw, ch


def load_decks(decks_root="decks", default_card_w=500, default_card_h=500):
    """
    Discover all piles under decks_root.

    Top-level folders are "deck collections".  Each subfolder that contains
    card images becomes a separate pile.  If the collection root itself has
    card images it also becomes a pile.  Collections with no sub-piles that
    have card images in the root become a single flat pile.

    An optional deck.json in each collection folder may specify pile order and
    card dimensions:
        {
          "piles": ["Agents", "Engines", ".", "Aspects"],
          "card_width": 500,
          "card_height": 750,
          "card_size": { "Agents": [375, 525], ".": [500, 750] }
        }
    Dimension fallback: pile-level → collection-level → default_card_w/h.
    Piles omitted from "piles" list are appended alphabetically (root last).
    """
    decks = []
    if not os.path.isdir(decks_root):
        return decks

    for top_entry in sorted(os.listdir(decks_root)):
        top_path = os.path.join(decks_root, top_entry)
        if not os.path.isdir(top_path):
            continue

        config     = _load_collection_config(top_path)
        pile_order = config.get("piles", [])

        subdirs_with_cards = sorted([
            d for d in os.listdir(top_path)
            if os.path.isdir(os.path.join(top_path, d))
            and _has_card_images(os.path.join(top_path, d))
        ])

        if subdirs_with_cards:
            # Build a name → Deck map for all available piles
            pile_by_name = {}
            for sub in subdirs_with_cards:
                sub_path = os.path.join(top_path, sub)
                cw, ch = _resolve_card_size(config, sub, default_card_w, default_card_h)
                deck = Deck(sub_path,
                            display_name=f"{top_entry} / {sub}",
                            parent_name=top_entry,
                            card_w=cw, card_h=ch)
                deck.collection_path = top_path
                if len(deck) > 0:
                    pile_by_name[sub] = deck
            # Root cards (if any) are referenced as "."
            if _has_card_images(top_path):
                cw, ch = _resolve_card_size(config, ".", default_card_w, default_card_h)
                deck = Deck(top_path,
                            display_name=top_entry,
                            parent_name=top_entry,
                            card_w=cw, card_h=ch)
                deck.collection_path = top_path
                if len(deck) > 0:
                    pile_by_name["."] = deck

            # Emit in config order, then remaining (subdirs alpha, root last)
            if pile_order:
                emitted = set()
                for name in pile_order:
                    if name in pile_by_name:
                        decks.append(pile_by_name[name])
                        emitted.add(name)
                for name in sorted(k for k in pile_by_name if k not in emitted and k != "."):
                    decks.append(pile_by_name[name])
                if "." in pile_by_name and "." not in emitted:
                    decks.append(pile_by_name["."])
            else:
                # Default: subdirs alphabetically, root pile last
                for name in sorted(k for k in pile_by_name if k != "."):
                    decks.append(pile_by_name[name])
                if "." in pile_by_name:
                    decks.append(pile_by_name["."])

        elif _has_card_images(top_path):
            # Flat deck — no sub-pile directories
            cw, ch = _resolve_card_size(config, ".", default_card_w, default_card_h)
            deck = Deck(top_path,
                        display_name=top_entry,
                        parent_name=top_entry,
                        card_w=cw, card_h=ch)
            deck.collection_path = top_path
            if len(deck) > 0:
                decks.append(deck)

        else:
            # Empty collection folder — no cards yet, but still show in picker
            deck = Deck(top_path,
                        display_name=top_entry,
                        parent_name=top_entry)
            deck.collection_path = top_path
            decks.append(deck)

    return decks


def _pile_key(deck):
    """Return the deck.json key for a deck: '.' for root pile, subfolder name otherwise."""
    if deck.folder_path == deck.collection_path:
        return "."
    return os.path.basename(deck.folder_path)


def save_collection_config(collection_path, updates):
    """Merge updates into deck.json (creating it if absent), preserving existing keys.

    Args:
        collection_path: path to the collection folder containing deck.json
        updates: dict of keys to set (e.g. {"piles": ["Agents", "Engines"]})
    """
    config_path = os.path.join(collection_path, "deck.json")
    config = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"[deck.json] Warning: could not read {config_path}: {e}")
    config.update(updates)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        print(f"[deck.json] Error writing {config_path}: {e}")
