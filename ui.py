import pygame
import os
from PIL import Image
import settings
from arrow import ARROW_SWATCHES

# Default sidebar width — stored as module constant for initial value only.
# At runtime, use sidebar.width (mutable instance variable).
SIDEBAR_WIDTH  = 220
SIDEBAR_MIN_W  = 160
SIDEBAR_MAX_W  = 500
RESIZE_ZONE    = 6          # px from border that activates the drag handle

RIGHT_PANEL_WIDTH = 220
RIGHT_PANEL_MIN_W = 160
RIGHT_PANEL_MAX_W = 500

SIDEBAR_BG     = (30, 30, 40)
TEXT_COLOR     = (220, 220, 220)
DIM_COLOR      = (140, 140, 160)
ACCENT         = (100, 180, 255)
BTN_BG         = (60, 60, 80)
BTN_HOVER      = (80, 100, 140)
BTN_ACTIVE     = (100, 140, 200)
BTN_WARN       = (160, 100, 40)
BTN_WARN_HOVER = (200, 130, 50)
CHK_ON         = (60, 120, 60)
CHK_ON_HOVER   = (80, 150, 80)

_BG_PRESET_SWATCHES = [
    (34,  34,  48),   # Default dark (matches app default)
    (15,  25,  50),   # Deep navy
    (20,  45,  25),   # Forest green
    (50,  15,  25),   # Deep burgundy
    (45,  48,  55),   # Slate gray
    (38,  28,  20),   # Warm brown
    (25,  20,  55),   # Indigo
    (28,  28,  28),   # Charcoal
]

# Pile list row geometry (constants — thumbnail max bounds, not forced size)
PILE_ROW_H    = 72
HEADER_ROW_H  = 22          # collection header row height
PILE_THUMB_W  = 48
PILE_THUMB_H  = 64
PILE_LIST_TOP = 64          # y where pile list starts

# Height of the fixed button area at the bottom of the sidebar
_BTN_AREA_H   = 216


def _pil_fit_surface(path, max_w, max_h):
    """Load image, fit within max_w×max_h preserving aspect ratio, return surface."""
    img = Image.open(path).convert("RGBA")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    data = img.tobytes()
    return pygame.image.fromstring(data, img.size, "RGBA").convert_alpha()


class Button:
    def __init__(self, rect, label, color=BTN_BG, hover_color=BTN_HOVER, font=None):
        self.rect        = pygame.Rect(rect)
        self.label       = label
        self.color       = color
        self.hover_color = hover_color
        self.font        = font
        self.hovered     = False

    def draw(self, screen):
        color = self.hover_color if self.hovered else self.color
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, (80, 80, 100), self.rect, 1, border_radius=6)
        if self.font:
            text = self.font.render(self.label, True, TEXT_COLOR)
            tr   = text.get_rect(center=self.rect.center)
            screen.blit(text, tr)

    def update(self, mx, my):
        self.hovered = self.rect.collidepoint(mx, my)

    def is_clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))


class Sidebar:
    def __init__(self, screen_height):
        self.screen_height    = screen_height
        self.width            = SIDEBAR_WIDTH   # mutable — can be dragged

        self.decks            = []
        self._active_parents   = set()
        self._collapsed_parents = set()   # collections rolled up in the sidebar
        self._selected_indices = set()
        self._focused_idx     = -1
        self._scroll_offset   = 0         # pixel scroll offset for pile list

        self._preview_cache   = {}
        self._browse_cache    = {}

        # Draw options
        self.draw_face_down       = False
        self.draw_random_rotation = False
        self.show_pile_top        = False   # use PileTop.ext as thumbnail for doublesided piles
        self.tuck_mode            = False   # place drawn cards under existing cards
        self.snap_to_grid         = False   # snap dropped cards to world grid
        self.snap_grid_size       = 125     # grid snap granularity in world px (default 25% of card)
        self.card_base_w          = 500     # global default card width in world px
        self.card_base_h          = 500     # global default card height in world px
        self._card_w_input        = ""      # text being typed in W input field
        self._card_h_input        = ""      # text being typed in H input field
        self._card_w_active       = False   # W input field is focused
        self._card_h_active       = False   # H input field is focused
        self.save_with_bg         = False   # include background in Ctrl+S PNG export
        self.save_to_clipboard    = False   # Ctrl+S copies to clipboard instead of file
        self.delete_confirm           = True   # show confirmation dialog before permanent delete
        self.delete_discards          = False  # Delete key sends to discard instead of removing
        self.keep_discard_orientation = False  # preserve face/rotation when discarding
        self.drawn_card_dim           = 100    # dim overlay alpha (0-200) for in-play cards in browse
        self.browse_shuffle_order     = False  # show available cards in draw pile order in browse
        self.show_grid                = False  # dot grid on canvas background

        # Confirm-delete dialog
        self.show_confirm_delete   = False
        self._confirm_delete_card  = None
        self._confirm_delete_bulk_n = 0   # >0 when confirming a bulk delete

        # Confirm-load-loadout dialog
        self.show_confirm_load    = False
        self._pending_loadout     = None  # list of active_parents pending confirmation
        self.load_confirm         = True   # show confirm dialog before loading a loadout (only when reset_on_loadout)
        self.reset_on_loadout     = False  # full reset (return cards, clear table) when loadout applied
        self.default_loadout_path = None   # loadout file applied automatically on startup

        # Session Panel (formerly Right Panel)
        self.show_right_panel  = False
        self.right_panel_width = RIGHT_PANEL_WIDTH

        # Discard pile
        self.discard_pile         = []     # Card objects; [-1] = top
        self.discard_selected     = False  # included in D-key draw pool when True
        self._browse_discard      = False  # browse overlay showing discard pile
        self._discard_rect        = None   # hit-test rects (set each draw frame)
        self._discard_card_rect   = None
        self._discard_browse_rect = None
        self._save_sort_rect      = None
        self._save_spread_rect    = None
        self._load_spread_rect    = None
        self._save_loadout_rect   = None
        self._load_loadout_rect   = None

        # Overlays
        self.show_deck_picker = False
        self.show_browse      = False
        self.show_help        = False
        self.show_options     = False
        self.show_bg_picker   = False
        self._picker_scroll   = 0
        self._browse_scroll   = 0
        self._browse_thumb_sz = 90
        self._browse_flipped          = set()   # front paths showing their back in browse
        self._browse_last_click_time  = 0       # ms timestamp of last browse grid click
        self._browse_last_click_pos   = (0, 0)  # (mx, my) of last click
        self._help_scroll             = 0       # pixel scroll offset for help overlay
        self._options_scroll_y        = 0       # pixel scroll offset for options panel

        # Background state
        self.bg_mode          = "color"      # "color" | "image"
        self.bg_color         = (34, 34, 48) # matches BG_COLOR in main.py
        self.bg_image_path    = None
        self.bg_image_fit     = "tile"       # "tile" | "center"
        self._bg_surface      = None         # cached pygame.Surface
        self._bg_cache_key    = None         # (path, w, h, fit) key
        self._bg_hex_input    = ""
        self._bg_hex_active   = False
        self._bg_hex_error    = False
        self._bg_img_scroll   = 0
        self._bg_table_images = []
        self._bg_thumb_cache  = {}

        # Arrow state (Session Panel)
        self.arrow_color     = (0, 0, 0)  # default black
        self.arrow_style     = "plain"    # "plain" | "rope" | "chain"
        self.arrow_both_ends = False      # True = arrowhead at both ends
        self.arrow_weight         = 3   # 1–10, session only (not persisted)
        self.default_arrow_weight = 3   # 1–10, persisted as the startup default
        self._arrow_placing  = False      # mirrors _arrow_placing in main.py (for button highlight)
        # Rects set each draw frame, used for hit-testing
        self._arrow_add_rect          = None
        self._arrow_dir_rect          = None
        self._arrow_style_rects       = {}   # "plain" / "rope" / "chain" → rect
        self._arrow_swatch_rects      = []   # list of (rect, color)
        self._arrow_weight_minus_rect = None
        self._arrow_weight_plus_rect  = None

        # Pile / header drag-to-reorder
        self._drag_pile_idx    = None
        self._drag_header_name = None   # parent_name of collection header being dragged
        self._drag_active      = False
        self._drag_pile_y      = 0
        self._drag_start_y     = 0

        self._font_large      = None
        self._font_med        = None
        self._font_small      = None
        self._font_icon       = None
        self._font_icon_bold  = None
        self._buttons     = {}
        self._initialized = False

    # ── Init / resize ─────────────────────────────────────────────────────────

    def init_fonts(self):
        pygame.font.init()
        self._font_large = pygame.font.SysFont("segoeui", 18, bold=True)
        self._font_med   = pygame.font.SysFont("segoeui", 15)
        self._font_small = pygame.font.SysFont("segoeui", 12)
        _assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        try:
            self._font_icon      = pygame.font.Font(
                os.path.join(_assets, "NotoEmoji-Regular.ttf"), 15)
            self._font_icon_bold = pygame.font.Font(
                os.path.join(_assets, "NotoEmoji-Bold.ttf"), 15)
        except Exception as e:
            print(f"[fonts] Could not load icon fonts: {e}")
            self._font_icon      = self._font_small
            self._font_icon_bold = self._font_small
        self._build_buttons()
        self._initialized = True

    def _build_buttons(self):
        x  = 10
        w  = self.width - 20
        sh = self.screen_height
        fm = self._font_med
        fs = self._font_small

        gap    = 4
        opt_w  = (w - gap) * 3 // 4
        rp_w   = w - gap - opt_w
        opt_x  = x + rp_w + gap

        fi = self._font_icon or fs   # icon font with emoji fallback to small
        self._buttons = {
            "right_panel":  Button((x,     sh - 44, rp_w,  30), "\u25b6",           font=fi),
            "options":      Button((opt_x, sh - 44, opt_w, 30), "Options",          font=fs),
            "reset":        Button((x, sh - 72,  w, 22), "Reset  (Ctrl-R)",         BTN_WARN, BTN_WARN_HOVER, font=fs),
            "browse_pile":  Button((x, sh - 102, w, 24), "Browse Pile...",          font=fs),
            "draw_all":     Button((x, sh - 136, w, 28), "Draw All  [A]",           font=fm),
            "draw":         Button((x, sh - 170, w, 28), "Draw Random  [D]",        BTN_ACTIVE, font=fm),
            "choose_decks": Button((x, sh - 202, w, 26), "Choose Decks...",         font=fs),
        }

    def set_decks(self, decks):
        self.decks = decks
        piles = self.active_piles
        self._selected_indices = {i for i in self._selected_indices if i < len(piles)}
        if self._focused_idx >= len(piles):
            self._focused_idx = len(piles) - 1

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def active_piles(self):
        return [d for d in self.decks if d.parent_name in self._active_parents]

    @property
    def selected_decks(self):
        piles = self.active_piles
        return [piles[i] for i in sorted(self._selected_indices) if i < len(piles)]

    @property
    def focused_deck(self):
        piles = self.active_piles
        if 0 <= self._focused_idx < len(piles):
            return piles[self._focused_idx]
        return None

    @property
    def selected_deck(self):
        return self.focused_deck

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _get_back_thumb(self, deck):
        if deck.is_doublesided:
            # Show PileTop when option is on and file exists; otherwise show top card
            if self.show_pile_top and deck.pile_top_path:
                path = deck.pile_top_path
            else:
                path = deck._all_fronts[0] if deck._all_fronts else None
        else:
            path = deck.back_path or (deck._all_fronts[0] if deck._all_fronts else None)

        if path is None:
            surf = pygame.Surface((PILE_THUMB_W, PILE_THUMB_H))
            surf.fill((80, 80, 80))
            return surf
        key = (path, PILE_THUMB_W, PILE_THUMB_H)
        if key not in self._preview_cache:
            try:
                self._preview_cache[key] = _pil_fit_surface(path, PILE_THUMB_W, PILE_THUMB_H)
            except Exception:
                surf = pygame.Surface((PILE_THUMB_W, PILE_THUMB_H))
                surf.fill((80, 80, 80))
                self._preview_cache[key] = surf
        return self._preview_cache[key]

    def _get_browse_thumb(self, path, size):
        key = (path, size)
        if key not in self._browse_cache:
            try:
                self._browse_cache[key] = _pil_fit_surface(path, size, size)
            except Exception:
                surf = pygame.Surface((size, size))
                surf.fill((60, 60, 60))
                self._browse_cache[key] = surf
        return self._browse_cache[key]

    def _get_card_thumb(self, card, size):
        """Return a thumbnail surface for a card, preserving its rotation and face."""
        key = (card.image_path, card.rotation, size)
        if key not in self._browse_cache:
            surf = card.get_surface()
            sw, sh = surf.get_size()
            scale = min(size / sw, size / sh)
            nw = max(1, int(sw * scale))
            nh = max(1, int(sh * scale))
            self._browse_cache[key] = pygame.transform.smoothscale(surf, (nw, nh))
        return self._browse_cache[key]

    # ── Resize ────────────────────────────────────────────────────────────────

    def resize(self, screen_height):
        self.screen_height = screen_height
        if self._initialized:
            self._build_buttons()

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _list_bot(self, sh):
        return sh - _BTN_AREA_H

    def _build_row_list(self):
        """Ordered list of virtual rows: ('header', parent_name) or ('pile', pile_idx).
        Header rows always appear; pile rows are omitted when their parent is collapsed."""
        piles = self.active_piles
        rows  = []
        last_parent = None
        for i, pile in enumerate(piles):
            if pile.parent_name != last_parent:
                rows.append(('header', pile.parent_name))
                last_parent = pile.parent_name
            if pile.parent_name not in self._collapsed_parents:
                rows.append(('pile', i))
        return rows

    def _total_content_h(self):
        """Total pixel height of all rows in the pile list."""
        rows = self._build_row_list()
        return sum(HEADER_ROW_H if r[0] == 'header' else PILE_ROW_H for r in rows)

    def _pile_row_at(self, my, sh):
        """Return ('header', name) or ('pile', idx) for the row at pixel y=my, else None."""
        list_bot = self._list_bot(sh)
        if not (PILE_LIST_TOP <= my < list_bot):
            return None
        y = PILE_LIST_TOP - self._scroll_offset
        for row in self._build_row_list():
            h = HEADER_ROW_H if row[0] == 'header' else PILE_ROW_H
            if y <= my < y + h:
                return row
            y += h
            if y > list_bot:
                break
        return None

    def _drag_insert_at(self, my, sh):
        """Return pile-list insertion index (0…len(piles)) for a drag y position."""
        list_bot = self._list_bot(sh)
        piles    = self.active_piles
        if my <= PILE_LIST_TOP:
            return 0
        if my >= list_bot:
            return len(piles)
        y            = PILE_LIST_TOP - self._scroll_offset
        insert_after = 0
        for row in self._build_row_list():
            if row[0] == 'header':
                y += HEADER_ROW_H
            else:
                pile_idx = row[1]
                mid = y + PILE_ROW_H / 2
                if my < mid:
                    return pile_idx
                insert_after = pile_idx + 1
                y += PILE_ROW_H
        return insert_after

    # ── Pile drag-and-drop reorder ────────────────────────────────────────────

    def handle_motion(self, mx, my, sh):
        """Called from main.py MOUSEMOTION when pile or header drag might be active."""
        if self._drag_pile_idx is None and self._drag_header_name is None:
            return
        if not self._drag_active:
            if abs(my - self._drag_start_y) > 8:
                self._drag_active = True
        if self._drag_active:
            self._drag_pile_y = my

    def _complete_pile_drag(self, src_idx, insert_idx):
        piles = self.active_piles
        # Adjust insert position for the removal of src
        dst = insert_idx if insert_idx <= src_idx else insert_idx - 1
        if dst == src_idx:
            return

        # Find positions of active piles within self.decks
        active_positions = [i for i, d in enumerate(self.decks)
                            if d.parent_name in self._active_parents]
        new_active = list(piles)
        pile = new_active.pop(src_idx)
        new_active.insert(dst, pile)
        for pos, deck in zip(active_positions, new_active):
            self.decks[pos] = deck

        # Remap selected indices
        def remap(i):
            if i == src_idx:
                return dst
            if src_idx < dst and src_idx < i <= dst:
                return i - 1
            if dst < src_idx and dst <= i < src_idx:
                return i + 1
            return i

        self._selected_indices = {remap(i) for i in self._selected_indices}
        if self._focused_idx >= 0:
            self._focused_idx = remap(self._focused_idx)

    def _header_insert_at(self, my, sh):
        """For a header drag: return the parent_name to insert BEFORE, or None = append at end.
        Skips the collection currently being dragged."""
        y = PILE_LIST_TOP - self._scroll_offset
        # Build (parent_name, group_mid_y) pairs, skipping the dragged group
        groups = []
        piles  = self.active_piles
        current = None
        top_y   = 0
        for row in self._build_row_list():
            if row[0] == 'header':
                if current and current != self._drag_header_name:
                    groups.append((current, top_y, y))
                current = row[1]
                top_y   = y
                y += HEADER_ROW_H
            else:
                y += PILE_ROW_H
        if current and current != self._drag_header_name:
            groups.append((current, top_y, y))

        for parent_name, top, bot in groups:
            if my < (top + bot) / 2:
                return parent_name
        return None  # insert at end

    def _complete_header_drag(self, src_parent, insert_before_parent):
        """Reorder self.decks so the src_parent collection moves before insert_before_parent
        (or to the end if insert_before_parent is None). Remaps selection indices."""
        old_active = self.active_piles   # snapshot before reorder

        src_decks   = [d for d in self.decks if d.parent_name == src_parent]
        other_decks = [d for d in self.decks if d.parent_name != src_parent]

        if insert_before_parent is None:
            self.decks = other_decks + src_decks
        else:
            pos = next((i for i, d in enumerate(other_decks)
                        if d.parent_name == insert_before_parent), None)
            self.decks = (other_decks[:pos] + src_decks + other_decks[pos:]
                          if pos is not None else other_decks + src_decks)

        new_active      = self.active_piles
        deck_to_new_idx = {d: i for i, d in enumerate(new_active)}

        self._selected_indices = {
            deck_to_new_idx[old_active[i]]
            for i in self._selected_indices
            if i < len(old_active) and old_active[i] in deck_to_new_idx
        }
        if 0 <= self._focused_idx < len(old_active):
            self._focused_idx = deck_to_new_idx.get(old_active[self._focused_idx], -1)

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event, decks, table, screen_size):
        if not self._initialized:
            return None

        sw, sh = screen_size
        mx, my = pygame.mouse.get_pos()

        # ── Overlays intercept all events ─────────────────────────────────────
        if self.show_deck_picker:
            return self._handle_picker_event(event, sw, sh, mx, my)

        if self.show_browse:
            return self._handle_browse_event(event, sw, sh, mx, my)

        if self.show_bg_picker:
            return self._handle_bg_picker_event(event, sw, sh, mx, my)

        # ── Help overlay: scroll or Escape/any-other-key closes it ──────────
        if self.show_help:
            if event.type == pygame.MOUSEWHEEL:
                self._help_scroll = max(0, self._help_scroll - event.y * 20)
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.show_help = False
                    self._help_scroll = 0
                elif event.key == pygame.K_DOWN:
                    self._help_scroll += 20
                elif event.key == pygame.K_UP:
                    self._help_scroll = max(0, self._help_scroll - 20)
                elif event.key == pygame.K_PAGEDOWN:
                    self._help_scroll += 200
                elif event.key == pygame.K_PAGEUP:
                    self._help_scroll = max(0, self._help_scroll - 200)
                else:
                    self.show_help = False
                    self._help_scroll = 0
                return None
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.show_help = False
                self._help_scroll = 0
            return None

        # ── Options panel scroll ──────────────────────────────────────────────
        if self.show_options and event.type == pygame.MOUSEWHEEL:
            content_h = self._options_rects(sw, sh)['_content_h']
            max_scroll = max(0, content_h - sh)
            self._options_scroll_y = max(0, min(max_scroll,
                                                self._options_scroll_y - event.y * 20))
            return None

        # ── Pile drag — MOUSEBUTTONUP completes the drag ──────────────────────
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_header_name is not None:
                if self._drag_active:
                    insert_before = self._header_insert_at(my, sh)
                    self._complete_header_drag(self._drag_header_name, insert_before)
                else:
                    # Was a plain click — toggle collapse/expand
                    name = self._drag_header_name
                    if name in self._collapsed_parents:
                        self._collapsed_parents.discard(name)
                    else:
                        self._collapsed_parents.add(name)
                self._drag_header_name = None
                self._drag_active      = False
            elif self._drag_pile_idx is not None:
                if self._drag_active:
                    dst = self._drag_insert_at(my, sh)
                    self._complete_pile_drag(self._drag_pile_idx, dst)
                self._drag_pile_idx = None
                self._drag_active   = False
            return None

        # ── Pile list scroll (mouse wheel over sidebar) ────────────────────────
        if event.type == pygame.MOUSEWHEEL and mx <= self.width:
            total_h    = self._total_content_h()
            list_h     = self._list_bot(sh) - PILE_LIST_TOP
            max_scroll = max(0, total_h - list_h)
            self._scroll_offset = max(0, min(max_scroll,
                                            self._scroll_offset - event.y * 30))
            return None

        # ── Pile row clicks ───────────────────────────────────────────────────
        if event.type == pygame.MOUSEBUTTONDOWN and mx <= self.width:
            hit = self._pile_row_at(my, sh)
            if hit is not None:
                kind, data = hit
                if kind == 'header':
                    if event.button == 1:
                        mods = pygame.key.get_mods()
                        if mods & pygame.KMOD_CTRL:
                            # Ctrl+click: collapse/expand ALL immediately (unambiguous)
                            all_parents = {p.parent_name for p in self.active_piles}
                            if data in self._collapsed_parents:
                                self._collapsed_parents -= all_parents
                            else:
                                self._collapsed_parents |= all_parents
                        else:
                            # Plain click/drag: start potential header drag.
                            # Collapse/expand only fires on MOUSEUP if no drag occurred.
                            self._drag_header_name = data
                            self._drag_start_y     = my
                            self._drag_active      = False
                    return None
                else:  # kind == 'pile'
                    idx   = data
                    piles = self.active_piles
                    mods  = pygame.key.get_mods()
                    ctrl  = bool(mods & pygame.KMOD_CTRL)
                    alt   = bool(mods & pygame.KMOD_ALT)
                    if event.button == 1:
                        if ctrl and alt:
                            # Ctrl+Alt+click: select/deselect all piles sharing this pile's name
                            match_name    = piles[idx].name
                            match_indices = {i for i, p in enumerate(piles)
                                             if p.name == match_name}
                            if match_indices.issubset(self._selected_indices):
                                self._selected_indices -= match_indices
                            else:
                                self._selected_indices |= match_indices
                            self._focused_idx = idx
                        elif ctrl:
                            # Ctrl+click: toggle add/remove
                            if idx in self._selected_indices:
                                self._selected_indices.discard(idx)
                            else:
                                self._selected_indices.add(idx)
                            self._focused_idx   = idx
                            # Start potential pile drag
                            self._drag_pile_idx = idx
                            self._drag_start_y  = my
                            self._drag_active   = False
                        else:
                            # Single click: exclusive select
                            self._selected_indices = {idx}
                            self._focused_idx   = idx
                            # Start potential pile drag
                            self._drag_pile_idx = idx
                            self._drag_start_y  = my
                            self._drag_active   = False
                        return None
                    elif event.button == 3:
                        self._focused_idx = idx
                        if ctrl and alt:
                            # Ctrl+Alt+right-click: draw one card from every pile with this name
                            return ("draw_matching_piles", piles[idx].name)
                        # Plain right-click: draw one card from this pile only
                        return ("draw_single_pile", idx)

        # ── Fixed buttons ─────────────────────────────────────────────────────
        for btn in self._buttons.values():
            btn.update(mx, my)

        for name, btn in self._buttons.items():
            if btn.is_clicked(event):
                if name == "draw":
                    return "draw_random"
                elif name == "draw_all":
                    return "draw_all"
                elif name == "choose_decks":
                    return "open_deck_picker"
                elif name == "reset":
                    return "reset"
                elif name == "browse_pile":
                    if self.focused_deck:
                        self._browse_scroll          = 0
                        self._browse_thumb_sz        = 90
                        self._browse_flipped         = set()
                        self._browse_last_click_time = 0
                        self.show_browse             = True
                elif name == "options":
                    self.show_options = not self.show_options
                    if not self.show_options:
                        self._options_scroll_y = 0
                elif name == "right_panel":
                    self.show_right_panel = not self.show_right_panel
                return None

        return None

    def _handle_browse_discard_event(self, event, sw, sh, mx, my):
        panel_x      = self.width + 20
        right_margin = self.right_panel_width if (self.show_right_panel or self.show_options) else 0
        panel_w      = sw - panel_x - 20 - right_margin
        panel_y = 20
        panel_h = sh - 40
        thumb_sz     = self._browse_thumb_sz
        cols         = max(1, (panel_w - 30) // (thumb_sz + 10))
        cell_w       = (panel_w - 20) // cols
        cell_h       = thumb_sz + 16
        grid_top     = panel_y + 50
        grid_h       = panel_h - 70
        n_cards      = len(self.discard_pile)
        rows         = max(1, (n_cards + cols - 1) // cols)
        visible_rows = max(1, grid_h // cell_h)
        max_scroll   = max(0, rows - visible_rows)

        if event.type == pygame.MOUSEWHEEL:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                factor = 1.15 if event.y > 0 else 1 / 1.15
                self._browse_thumb_sz = max(40, min(200, int(self._browse_thumb_sz * factor)))
                self._browse_cache.clear()
            else:
                self._browse_scroll = max(0, min(max_scroll, self._browse_scroll - event.y))
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.show_browse = False
            self._browse_discard = False
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        close_rect = pygame.Rect(panel_x + panel_w - 36, panel_y + 8, 28, 28)
        if close_rect.collidepoint(mx, my):
            self.show_browse = False
            self._browse_discard = False
            return None

        if (panel_x <= mx <= panel_x + panel_w
                and grid_top <= my <= panel_y + panel_h - 20):
            col = (mx - panel_x - 10) // cell_w
            row = (my - grid_top) // cell_h + self._browse_scroll
            idx = row * cols + col
            if 0 <= col < cols and 0 <= idx < n_cards:
                now = pygame.time.get_ticks()
                dx  = mx - self._browse_last_click_pos[0]
                dy  = my - self._browse_last_click_pos[1]
                if (now - self._browse_last_click_time < 400
                        and dx * dx + dy * dy < 100):
                    self._browse_last_click_time = 0
                    self.show_browse = False
                    self._browse_discard = False
                    return ("discard_browse_pick", idx)
                else:
                    self._browse_last_click_time = now
                    self._browse_last_click_pos  = (mx, my)
        return None

    # ── Deck picker overlay ───────────────────────────────────────────────────

    def _handle_picker_event(self, event, sw, sh, mx, my):
        panel_w = min(500, sw - self.width - 40)
        panel_h = min(500, sh - 80)
        px      = self.width + (sw - self.width - panel_w) // 2
        py      = (sh - panel_h) // 2

        parent_names = self._unique_parents()
        row_h        = 34
        list_top     = py + 50
        list_bot     = py + panel_h - 60
        visible_rows = max(1, (list_bot - list_top) // row_h)
        max_scroll   = max(0, len(parent_names) - visible_rows)

        if event.type == pygame.MOUSEWHEEL:
            self._picker_scroll = max(0, min(max_scroll, self._picker_scroll - event.y))
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        if not (px <= mx <= px + panel_w and py <= my <= py + panel_h):
            self.show_deck_picker = False
            return None

        if list_top <= my < list_bot:
            row = (my - list_top) // row_h
            idx = row + self._picker_scroll
            if 0 <= idx < len(parent_names):
                name = parent_names[idx]
                if name in self._active_parents:
                    self._active_parents.discard(name)
                else:
                    self._active_parents.add(name)
                self._selected_indices.clear()
                self._focused_idx   = -1
                self._scroll_offset = 0
            return None

        btn_y = py + panel_h - 52
        if btn_y <= my <= btn_y + 28:
            if px + 10 <= mx <= px + 140:
                self._active_parents = set(parent_names)
                self._selected_indices.clear()
                self._focused_idx = -1
            elif px + 150 <= mx <= px + 270:
                self._active_parents.clear()
                self._selected_indices.clear()
                self._focused_idx = -1
            elif mx >= px + panel_w - 120:
                self.show_deck_picker = False

        return None

    # ── Browse overlay ────────────────────────────────────────────────────────

    def _handle_browse_event(self, event, sw, sh, mx, my):
        if self._browse_discard:
            return self._handle_browse_discard_event(event, sw, sh, mx, my)
        deck = self.focused_deck
        if deck is None:
            self.show_browse = False
            return None

        panel_x      = self.width + 20
        right_margin = self.right_panel_width if (self.show_right_panel or self.show_options) else 0
        panel_w      = sw - panel_x - 20 - right_margin
        panel_y      = 20
        panel_h      = sh - 40

        thumb_sz     = self._browse_thumb_sz
        cols         = max(1, (panel_w - 30) // (thumb_sz + 10))
        cell_w       = (panel_w - 20) // cols
        cell_h       = thumb_sz + 16
        grid_top     = panel_y + 50
        grid_h       = panel_h - 70

        drawn      = deck._drawn_paths
        trashed    = deck._trashed_paths
        if self.browse_shuffle_order and deck._draw_pile:
            available = list(reversed(deck._draw_pile))
        else:
            available  = [p for p in deck._all_fronts if p not in drawn and p not in trashed]
        in_play    = [p for p in deck._all_fronts if p in drawn   and p not in trashed]
        trash_list = [p for p in deck._all_fronts if p in trashed]
        n_avail_rows = (len(available)  + cols - 1) // cols if available  else 0
        n_play_rows  = (len(in_play)    + cols - 1) // cols if in_play    else 0
        n_trash_rows = (len(trash_list) + cols - 1) // cols if trash_list else 0
        sep1_rows    = 1 if in_play    else 0
        sep2_rows    = 1 if trash_list else 0
        total_rows   = n_avail_rows + sep1_rows + n_play_rows + sep2_rows + n_trash_rows
        visible_rows = max(1, grid_h // cell_h)
        max_scroll   = max(0, total_rows - visible_rows)
        self._browse_scroll = min(self._browse_scroll, max_scroll)

        def _hit(virtual_row, col):
            """Map (virtual_row, col) → (front_path, section) or (None, None)."""
            if not (0 <= col < cols):
                return None, None
            # Available
            if virtual_row < n_avail_rows:
                idx = virtual_row * cols + col
                return (available[idx], 'available') if idx < len(available) else (None, None)
            off = n_avail_rows
            # Separator 1
            if sep1_rows and virtual_row == off:
                return None, 'sep1'
            off += sep1_rows
            # In-play
            if virtual_row < off + n_play_rows:
                idx = (virtual_row - off) * cols + col
                return (in_play[idx], 'in_play') if idx < len(in_play) else (None, None)
            off += n_play_rows
            # Separator 2
            if sep2_rows and virtual_row == off:
                return None, 'sep2'
            off += sep2_rows
            # Trash
            if virtual_row < off + n_trash_rows:
                idx = (virtual_row - off) * cols + col
                return (trash_list[idx], 'trash') if idx < len(trash_list) else (None, None)
            return None, None

        if event.type == pygame.MOUSEWHEEL:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                factor = 1.15 if event.y > 0 else 1 / 1.15
                self._browse_thumb_sz = max(40, min(200, int(self._browse_thumb_sz * factor)))
                self._browse_cache.clear()
            else:
                self._browse_scroll = max(0, min(max_scroll, self._browse_scroll - event.y))
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.show_browse = False
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            # Right-click: flip card preview front ↔ back
            if (panel_x <= mx <= panel_x + panel_w
                    and grid_top <= my <= panel_y + panel_h - 20):
                col  = (mx - panel_x - 10) // cell_w
                vrow = (my - grid_top) // cell_h + self._browse_scroll
                path, section = _hit(vrow, col)
                if path and section != 'separator':
                    back = deck.card_back_for(path)
                    if back:
                        if path in self._browse_flipped:
                            self._browse_flipped.discard(path)
                        else:
                            self._browse_flipped.add(path)
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        close_rect = pygame.Rect(panel_x + panel_w - 36, panel_y + 8, 28, 28)
        if close_rect.collidepoint(mx, my):
            self.show_browse = False
            return None

        if (panel_x <= mx <= panel_x + panel_w
                and grid_top <= my <= panel_y + panel_h - 20):
            col  = (mx - panel_x - 10) // cell_w
            vrow = (my - grid_top) // cell_h + self._browse_scroll
            path, section = _hit(vrow, col)
            if path:
                now = pygame.time.get_ticks()
                dx  = mx - self._browse_last_click_pos[0]
                dy  = my - self._browse_last_click_pos[1]
                if (now - self._browse_last_click_time < 400
                        and dx * dx + dy * dy < 100):
                    # Double-click: add to table
                    self._browse_last_click_time = 0
                    self.show_browse = False
                    return ("browse_pick", path, deck)
                else:
                    # First click: record for double-click detection
                    self._browse_last_click_time = now
                    self._browse_last_click_pos  = (mx, my)

        return None

    # ── Background helpers ─────────────────────────────────────────────────────

    def _scan_table_images(self):
        """Populate self._bg_table_images with image paths from the tables/ folder."""
        tables_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tables")
        self._bg_table_images = []
        if not os.path.isdir(tables_dir):
            return
        for entry in sorted(os.listdir(tables_dir)):
            if os.path.splitext(entry)[1].lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                self._bg_table_images.append(os.path.join(tables_dir, entry))

    def _apply_hex_color(self):
        """Parse _bg_hex_input as #RRGGBB and apply as solid background if valid."""
        raw = self._bg_hex_input.strip().lstrip("#")
        try:
            if len(raw) != 6:
                raise ValueError
            r = int(raw[0:2], 16)
            g = int(raw[2:4], 16)
            b = int(raw[4:6], 16)
            self.bg_color       = (r, g, b)
            self.bg_mode        = "color"
            self.bg_image_path  = None
            self._bg_surface    = None
            self._bg_hex_error  = False
            settings.save(self)
        except (ValueError, IndexError):
            self._bg_hex_error = True

    # ── Options overlay ───────────────────────────────────────────────────────

    def _options_rects(self, sw, sh, scroll_y=0):
        """Return dict of named rects for all interactive elements in the Options panel."""
        pw = self.right_panel_width
        px = sw - pw
        py = 0

        rects = {
            'panel': pygame.Rect(px, py, pw, sh),
        }

        y = py + 52 - scroll_y
        item_h, gap = 28, 4

        for name in ('pile_top_toggle', 'face_down_toggle', 'random_rotation_toggle',
                     'tuck_toggle', 'snap_to_grid_toggle', 'save_with_bg_toggle',
                     'save_to_clipboard_toggle',
                     'delete_confirm_toggle', 'delete_discards_toggle',
                     'keep_discard_orient_toggle', 'draw_dim_row',
                     'browse_shuffle_order_toggle', 'show_grid_toggle',
                     'load_confirm_toggle', 'reset_on_loadout_toggle'):
            rects[name] = pygame.Rect(px + 10, y, pw - 20, item_h)
            y += item_h + gap

        # +/- buttons embedded in the snap_to_grid_toggle row
        snap_row = rects['snap_to_grid_toggle']
        rects['snap_grid_minus'] = pygame.Rect(snap_row.right - 52, snap_row.y + 4, 20, 20)
        rects['snap_grid_plus']  = pygame.Rect(snap_row.right - 28, snap_row.y + 4, 20, 20)

        # +/- buttons embedded in the draw_dim_row
        dim_row = rects['draw_dim_row']
        rects['dim_minus'] = pygame.Rect(dim_row.right - 52, dim_row.y + 4, 20, 20)
        rects['dim_plus']  = pygame.Rect(dim_row.right - 28, dim_row.y + 4, 20, 20)

        # Arrow weight row (embedded +/- like snap_grid)
        rects['arrow_weight_row'] = pygame.Rect(px + 10, y, pw - 20, item_h)
        y += item_h + gap
        aw_row = rects['arrow_weight_row']
        rects['arrow_weight_minus'] = pygame.Rect(aw_row.right - 52, aw_row.y + 4, 20, 20)
        rects['arrow_weight_plus']  = pygame.Rect(aw_row.right - 28, aw_row.y + 4, 20, 20)

        # 3-line "Default Card Size" grouped box
        _ig, _lh = 4, 24   # inner gap, line height
        box_rect = pygame.Rect(px + 10, y, pw - 20, _ig + _lh + _ig + _lh + _ig + _lh + _ig)
        rects['card_size_box']    = box_rect
        rects['card_size_reset']  = pygame.Rect(box_rect.right - 54, y + _ig + 2, 48, 20)
        # Width row (line 2)
        _wy = y + _ig + _lh + _ig
        rects['card_w_row']   = pygame.Rect(px + 10, _wy, pw - 20, _lh)
        rects['card_w_plus']  = pygame.Rect(box_rect.right - 28, _wy + 2, 20, 20)
        rects['card_w_minus'] = pygame.Rect(box_rect.right - 52, _wy + 2, 20, 20)
        rects['card_w_field'] = pygame.Rect(px + 68, _wy + 2,
                                            rects['card_w_minus'].left - (px + 68) - 4, 20)
        # Height row (line 3)
        _hly = _wy + _lh + _ig
        rects['card_h_row']   = pygame.Rect(px + 10, _hly, pw - 20, _lh)
        rects['card_h_plus']  = pygame.Rect(box_rect.right - 28, _hly + 2, 20, 20)
        rects['card_h_minus'] = pygame.Rect(box_rect.right - 52, _hly + 2, 20, 20)
        rects['card_h_field'] = pygame.Rect(px + 68, _hly + 2,
                                            rects['card_h_minus'].left - (px + 68) - 4, 20)
        y += box_rect.height + gap

        y += 12  # separator gap

        for name in ('import_pdf', 'controls', 'background'):
            rects[name] = pygame.Rect(px + 10, y, pw - 20, item_h)
            y += item_h + gap

        # Startup loadout button (full width) with an overlaid × clear button
        rects['startup_loadout'] = pygame.Rect(px + 10, y, pw - 20, item_h)
        rects['startup_loadout_clear'] = pygame.Rect(
            rects['startup_loadout'].right - 28, y + 4, 20, 20)
        y += item_h + gap

        # Total unscrolled content height (for scrollbar calculations)
        rects['_content_h'] = y + scroll_y

        return rects

    def handle_options_event(self, event, sw, sh, mx, my):
        rects = self._options_rects(sw, sh, self._options_scroll_y)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._card_w_active = self._card_h_active = False
                self._card_w_input  = self._card_h_input  = ""
                self.show_options = False
                self._options_scroll_y = 0
                return None
            for is_active, inp_attr, val_attr, act_attr in (
                (self._card_w_active, '_card_w_input', 'card_base_w', '_card_w_active'),
                (self._card_h_active, '_card_h_input', 'card_base_h', '_card_h_active'),
            ):
                if is_active:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        try:
                            v = max(100, min(2000, int(getattr(self, inp_attr))))
                            setattr(self, val_attr, v)
                        except ValueError:
                            pass
                        setattr(self, inp_attr, "")
                        setattr(self, act_attr, False)
                        return "card_base_size_changed"
                    elif event.key == pygame.K_BACKSPACE:
                        setattr(self, inp_attr, getattr(self, inp_attr)[:-1])
                    elif event.unicode and event.unicode.isdigit():
                        if len(getattr(self, inp_attr)) < 4:
                            setattr(self, inp_attr, getattr(self, inp_attr) + event.unicode)
                    return None
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        changed = False
        # Deactivate card size input fields on any click (re-activated below if field clicked)
        self._card_w_active = self._card_h_active = False
        self._card_w_input  = self._card_h_input  = ""
        if rects['pile_top_toggle'].collidepoint(mx, my):
            self.show_pile_top = not self.show_pile_top
            self._preview_cache.clear()
            changed = True
        elif rects['face_down_toggle'].collidepoint(mx, my):
            self.draw_face_down = not self.draw_face_down
            changed = True
        elif rects['random_rotation_toggle'].collidepoint(mx, my):
            self.draw_random_rotation = not self.draw_random_rotation
            changed = True
        elif rects['tuck_toggle'].collidepoint(mx, my):
            self.tuck_mode = not self.tuck_mode
            changed = True
        elif rects['snap_grid_minus'].collidepoint(mx, my):
            self.snap_grid_size = max(25, self.snap_grid_size - 25)
            changed = True
        elif rects['snap_grid_plus'].collidepoint(mx, my):
            self.snap_grid_size = min(500, self.snap_grid_size + 25)
            changed = True
        elif rects['snap_to_grid_toggle'].collidepoint(mx, my):
            self.snap_to_grid = not self.snap_to_grid
            changed = True
        elif rects['save_with_bg_toggle'].collidepoint(mx, my):
            self.save_with_bg = not self.save_with_bg
            changed = True
        elif rects['save_to_clipboard_toggle'].collidepoint(mx, my):
            self.save_to_clipboard = not self.save_to_clipboard
            changed = True
        elif rects['delete_confirm_toggle'].collidepoint(mx, my):
            self.delete_confirm = not self.delete_confirm
            changed = True
        elif rects['delete_discards_toggle'].collidepoint(mx, my):
            self.delete_discards = not self.delete_discards
            changed = True
        elif rects['keep_discard_orient_toggle'].collidepoint(mx, my):
            self.keep_discard_orientation = not self.keep_discard_orientation
            changed = True
        elif rects['browse_shuffle_order_toggle'].collidepoint(mx, my):
            self.browse_shuffle_order = not self.browse_shuffle_order
            changed = True
        elif rects['show_grid_toggle'].collidepoint(mx, my):
            self.show_grid = not self.show_grid
            changed = True
        elif rects['load_confirm_toggle'].collidepoint(mx, my):
            if self.reset_on_loadout:  # only active when reset is on
                self.load_confirm = not self.load_confirm
                changed = True
        elif rects['reset_on_loadout_toggle'].collidepoint(mx, my):
            self.reset_on_loadout = not self.reset_on_loadout
            changed = True
        elif rects['arrow_weight_minus'].collidepoint(mx, my):
            self.default_arrow_weight = max(1, self.default_arrow_weight - 1)
            changed = True
        elif rects['arrow_weight_plus'].collidepoint(mx, my):
            self.default_arrow_weight = min(10, self.default_arrow_weight + 1)
            changed = True
        elif (self.default_loadout_path
              and rects['startup_loadout_clear'].collidepoint(mx, my)):
            return "clear_startup_loadout"
        elif rects['startup_loadout'].collidepoint(mx, my):
            return "pick_startup_loadout"
        elif rects['dim_minus'].collidepoint(mx, my):
            self.drawn_card_dim = max(0, self.drawn_card_dim - 20)
            changed = True
        elif rects['dim_plus'].collidepoint(mx, my):
            self.drawn_card_dim = min(200, self.drawn_card_dim + 20)
            changed = True
        elif rects['card_w_field'].collidepoint(mx, my):
            self._card_w_active = True
            self._card_w_input  = str(self.card_base_w)
        elif rects['card_w_minus'].collidepoint(mx, my):
            self.card_base_w = max(100, self.card_base_w - 25)
            return "card_base_size_changed"
        elif rects['card_w_plus'].collidepoint(mx, my):
            self.card_base_w = min(2000, self.card_base_w + 25)
            return "card_base_size_changed"
        elif rects['card_h_field'].collidepoint(mx, my):
            self._card_h_active = True
            self._card_h_input  = str(self.card_base_h)
        elif rects['card_h_minus'].collidepoint(mx, my):
            self.card_base_h = max(100, self.card_base_h - 25)
            return "card_base_size_changed"
        elif rects['card_h_plus'].collidepoint(mx, my):
            self.card_base_h = min(2000, self.card_base_h + 25)
            return "card_base_size_changed"
        elif rects['card_size_reset'].collidepoint(mx, my):
            self.card_base_w = 500
            self.card_base_h = 500
            return "card_base_size_changed"
        elif rects['import_pdf'].collidepoint(mx, my):
            return "import_pdf"
        elif rects['controls'].collidepoint(mx, my):
            self.show_help = True
        elif rects['background'].collidepoint(mx, my):
            self._scan_table_images()
            self._bg_img_scroll = 0
            self._bg_hex_input  = ""
            self._bg_hex_active = False
            self._bg_hex_error  = False
            self.show_bg_picker = True

        if changed:
            settings.save(self)
        return None

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, screen):
        if not self._initialized:
            return

        sw, sh = screen.get_size()
        self.screen_height = sh

        pygame.draw.rect(screen, SIDEBAR_BG, (0, 0, self.width, sh))
        pygame.draw.line(screen, (70, 70, 90), (self.width, 0), (self.width, sh), 2)

        x = 10

        title = self._font_large.render("Deck Panel", True, ACCENT)
        screen.blit(title, (x, 12))

        pygame.draw.line(screen, (70, 70, 90), (x, 40), (self.width - 10, 40), 1)

        lbl = self._font_small.render("DECKS & PILES", True, DIM_COLOR)
        screen.blit(lbl, (x, 48))

        self._draw_pile_list(screen, sh)

        self._reanchor_buttons(sh)
        # Highlight toggle buttons when their panel is active
        for name, active in (("options", self.show_options),
                              ("right_panel", self.show_right_panel)):
            if name in self._buttons:
                self._buttons[name].color = BTN_ACTIVE if active else BTN_BG
        for btn in self._buttons.values():
            btn.draw(screen)

        if self.show_deck_picker:
            self._draw_picker(screen, sw, sh)
        elif self.show_browse:
            self._draw_browse_overlay(screen, sw, sh)
        elif self.show_bg_picker:
            self._draw_bg_picker(screen, sw, sh)
        elif self.show_help:
            self._draw_help(screen)

        if self.show_right_panel:
            self._draw_right_panel(screen, sw, sh)

        if self.show_options:
            self._draw_options(screen, sw, sh)

        if self.show_confirm_delete:
            self.draw_confirm_delete(screen, sw, sh)

        if self.show_confirm_load:
            self.draw_confirm_load(screen, sw, sh)

    def _draw_right_panel(self, screen, sw, sh):
        px  = sw - self.right_panel_width
        pw  = self.right_panel_width
        mg  = 10
        iw  = pw - 2 * mg

        # Panel background + left border
        pygame.draw.rect(screen, SIDEBAR_BG, (px, 0, pw, sh))
        pygame.draw.line(screen, (70, 70, 90), (px, 0), (px, sh), 2)

        # Title — right-justified
        title = self._font_large.render("Session Panel", True, ACCENT)
        screen.blit(title, (sw - 12 - title.get_width(), 12))
        pygame.draw.line(screen, (70, 70, 90), (px + mg, 40), (sw - mg, 40), 1)

        btn_h = 22
        gap   = 4
        lbl_h = 14
        y     = 52
        mx_c, my_c = pygame.mouse.get_pos()

        def _btn(rect, label):
            hov = rect.collidepoint(mx_c, my_c)
            pygame.draw.rect(screen, BTN_HOVER if hov else BTN_BG, rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), rect, 1, border_radius=4)
            lbl = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

        # ── SPREADS ───────────────────────────────────────────────────────────
        screen.blit(self._font_small.render("SPREADS", True, DIM_COLOR), (px + mg, y))
        y += lbl_h + gap
        self._save_spread_rect = pygame.Rect(px + mg, y, iw, btn_h)
        _btn(self._save_spread_rect, "Save Spread...")
        y += btn_h + gap
        self._load_spread_rect = pygame.Rect(px + mg, y, iw, btn_h)
        _btn(self._load_spread_rect, "Load Spread...")
        y += btn_h + gap + 8

        # Separator after SPREADS
        pygame.draw.line(screen, (70, 70, 90), (px + mg, y), (sw - mg, y), 1)
        y += 10

        # ── ARROWS ────────────────────────────────────────────────────────────
        def _btn_state(rect, label, active=False):
            hov = rect.collidepoint(mx_c, my_c)
            bg  = BTN_ACTIVE if active else (BTN_HOVER if hov else BTN_BG)
            pygame.draw.rect(screen, bg, rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), rect, 1, border_radius=4)
            lbl = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

        screen.blit(self._font_small.render("ARROWS", True, DIM_COLOR), (px + mg, y))
        y += lbl_h + gap

        # Row 1: Add Arrow button + direction toggle
        dir_w = 28
        add_w = iw - dir_w - gap
        self._arrow_add_rect = pygame.Rect(px + mg, y, add_w, btn_h)
        self._arrow_dir_rect = pygame.Rect(px + mg + add_w + gap, y, dir_w, btn_h)
        add_lbl = "* Add Arrow" if self._arrow_placing else "+ Add Arrow"
        _btn_state(self._arrow_add_rect, add_lbl, active=self._arrow_placing)
        _btn_state(self._arrow_dir_rect, "\u2194" if self.arrow_both_ends else "\u2192",
                   active=self.arrow_both_ends)
        y += btn_h + gap

        # Row 2: Style selector  [Plain] [Rope] [Chain]
        style_w = (iw - 2 * gap) // 3
        self._arrow_style_rects = {}
        for i, style in enumerate(("plain", "rope", "chain")):
            rect = pygame.Rect(px + mg + i * (style_w + gap), y, style_w, btn_h)
            self._arrow_style_rects[style] = rect
            _btn_state(rect, style.capitalize(), active=(self.arrow_style == style))
        y += btn_h + gap

        # Row 3: swatches | [-][N][+] weight
        swatch_h    = 20
        wbtn_w      = 18   # width of each [-] / [+] button
        wnum_w      = 22   # width of weight number display
        weight_area = wbtn_w + wnum_w + wbtn_w  # [-][N][+] block
        sw_area     = iw - weight_area - gap
        n_sw        = len(ARROW_SWATCHES)
        sw_gap      = 2
        sw_w        = (sw_area - (n_sw - 1) * sw_gap) // n_sw
        self._arrow_swatch_rects = []
        for i, swatch_color in enumerate(ARROW_SWATCHES):
            sx_  = px + mg + i * (sw_w + sw_gap)
            rect = pygame.Rect(sx_, y, sw_w, swatch_h)
            self._arrow_swatch_rects.append((rect, swatch_color))
            pygame.draw.rect(screen, swatch_color, rect, border_radius=3)
            border_col = (255, 255, 255) if self.arrow_color == swatch_color else (80, 80, 100)
            border_w   = 2 if self.arrow_color == swatch_color else 1
            pygame.draw.rect(screen, border_col, rect, border_w, border_radius=3)
        # Weight [-][N][+]
        wx = px + mg + sw_area + gap
        self._arrow_weight_minus_rect = pygame.Rect(wx, y, wbtn_w, swatch_h)
        wnum_rect = pygame.Rect(wx + wbtn_w, y, wnum_w, swatch_h)
        self._arrow_weight_plus_rect  = pygame.Rect(wx + wbtn_w + wnum_w, y, wbtn_w, swatch_h)
        _btn_state(self._arrow_weight_minus_rect, "-")
        pygame.draw.rect(screen, (35, 35, 50), wnum_rect, border_radius=3)
        pygame.draw.rect(screen, (80, 80, 100), wnum_rect, 1, border_radius=3)
        wn = self._font_small.render(str(self.arrow_weight), True, TEXT_COLOR)
        screen.blit(wn, wn.get_rect(center=wnum_rect.center))
        _btn_state(self._arrow_weight_plus_rect, "+")
        y += swatch_h + 8

        pygame.draw.line(screen, (70, 70, 90), (px + mg, y), (sw - mg, y), 1)

        # ── DECK LISTS (anchored just above DISCARD) ──────────────────────────
        # Compute discard section top (same formula as _draw_discard_section)
        thumb_sz       = min(iw, 160)
        discard_sect_h = 18 + 4 + thumb_sz + 4 + 20 + 4
        discard_top    = sh - discard_sect_h - mg

        # DECK LISTS block height: top-sep(1+10) + label(18) + save(26) + load(34)
        #                          + mid-sep(1+10) + sort(34) + bot-gap(12)
        dl_h   = 1 + 10 + (lbl_h + gap) + (btn_h + gap) + (btn_h + gap + 8) \
               + 1 + 10 + (btn_h + gap + 8) + 12
        dl_top = discard_top - dl_h

        pygame.draw.line(screen, (70, 70, 90), (px + mg, dl_top), (sw - mg, dl_top), 1)
        dy = dl_top + 10

        screen.blit(self._font_small.render("DECK LISTS", True, DIM_COLOR), (px + mg, dy))
        dy += lbl_h + gap
        self._save_loadout_rect = pygame.Rect(px + mg, dy, iw, btn_h)
        _btn(self._save_loadout_rect, "Save Deck List...")
        dy += btn_h + gap
        self._load_loadout_rect = pygame.Rect(px + mg, dy, iw, btn_h)
        _btn(self._load_loadout_rect, "Load Deck List...")
        dy += btn_h + gap + 8

        pygame.draw.line(screen, (70, 70, 90), (px + mg, dy), (sw - mg, dy), 1)
        dy += 10
        self._save_sort_rect = pygame.Rect(px + mg, dy, iw, btn_h)
        _btn(self._save_sort_rect, "Save Deck Sort")

        # ── DISCARD (bottom-anchored) ─────────────────────────────────────────
        self._draw_discard_section(screen, px, sh)

    def _draw_discard_section(self, screen, px, sh):
        mg       = 10
        inner_w  = self.right_panel_width - 2 * mg
        thumb_sz = min(inner_w, 160)
        label_h  = 18
        btn_h    = 20
        pad      = 4
        sect_h   = label_h + pad + thumb_sz + pad + btn_h + pad
        sx       = px + mg
        sy       = sh - sect_h - mg
        card_x   = sx + (inner_w - thumb_sz) // 2
        card_y   = sy + label_h + pad

        self._discard_rect      = pygame.Rect(sx, sy, inner_w, sect_h)
        self._discard_card_rect = pygame.Rect(card_x, card_y, thumb_sz, thumb_sz)

        pygame.draw.rect(screen, (35, 35, 50), self._discard_rect, border_radius=6)
        bc = (255, 100, 100) if self.discard_selected else (180, 55, 55)
        pygame.draw.rect(screen, bc, self._discard_rect, 2, border_radius=6)

        count = len(self.discard_pile)
        lbl = self._font_small.render(f"DISCARD  ({count})", True, (210, 80, 80))
        screen.blit(lbl, (sx + 6, sy + 3))

        if self.discard_pile:
            for i in range(min(3, count - 1), 0, -1):
                offset = i * 4
                pygame.draw.rect(screen, (50, 50, 70),
                                 pygame.Rect(card_x + offset, card_y + offset, thumb_sz, thumb_sz),
                                 border_radius=4)
            thumb = self._get_card_thumb(self.discard_pile[-1], thumb_sz)
            tw, th = thumb.get_size()
            screen.blit(thumb, (card_x + (thumb_sz - tw) // 2, card_y + (thumb_sz - th) // 2))
        else:
            er = pygame.Rect(card_x, card_y, thumb_sz, thumb_sz)
            pygame.draw.rect(screen, (42, 42, 58), er, border_radius=4)
            pygame.draw.rect(screen, (70, 70, 90), er, 1, border_radius=4)
            el = self._font_small.render("empty", True, DIM_COLOR)
            screen.blit(el, el.get_rect(center=er.center))

        btn_y = card_y + thumb_sz + pad
        self._discard_browse_rect = pygame.Rect(sx + 4, btn_y, inner_w - 8, btn_h)
        pygame.draw.rect(screen, BTN_BG, self._discard_browse_rect, border_radius=4)
        bl = self._font_small.render("Browse Discard", True, TEXT_COLOR)
        screen.blit(bl, bl.get_rect(center=self._discard_browse_rect.center))

    def handle_right_panel_event(self, event, mx, my, sw, sh):
        """Handle a MOUSEBUTTONDOWN in the right panel area. Returns action or None."""
        if event.type != pygame.MOUSEBUTTONDOWN:
            return None

        # ── ARROWS section ────────────────────────────────────────────────────
        if event.button == 1:
            if self._arrow_add_rect and self._arrow_add_rect.collidepoint(mx, my):
                return "toggle_arrow_placing"
            if self._arrow_dir_rect and self._arrow_dir_rect.collidepoint(mx, my):
                self.arrow_both_ends = not self.arrow_both_ends
                import settings as _s; _s.save(self)
                return None
            for style, rect in self._arrow_style_rects.items():
                if rect.collidepoint(mx, my):
                    self.arrow_style = style
                    import settings as _s; _s.save(self)
                    return None
            for rect, swatch_color in self._arrow_swatch_rects:
                if rect.collidepoint(mx, my):
                    self.arrow_color = swatch_color
                    import settings as _s; _s.save(self)
                    return None
            if self._arrow_weight_minus_rect and self._arrow_weight_minus_rect.collidepoint(mx, my):
                self.arrow_weight = max(1, self.arrow_weight - 1)
                return None
            if self._arrow_weight_plus_rect and self._arrow_weight_plus_rect.collidepoint(mx, my):
                self.arrow_weight = min(10, self.arrow_weight + 1)
                return None

        # Session Panel — Spread buttons
        if self._save_spread_rect and self._save_spread_rect.collidepoint(mx, my):
            return "save_spread" if event.button == 1 else None
        if self._load_spread_rect and self._load_spread_rect.collidepoint(mx, my):
            return "load_spread" if event.button == 1 else None
        # Session Panel — Loadout buttons
        if self._save_loadout_rect and self._save_loadout_rect.collidepoint(mx, my):
            return "save_loadout" if event.button == 1 else None
        if self._load_loadout_rect and self._load_loadout_rect.collidepoint(mx, my):
            return "load_loadout" if event.button == 1 else None
        # Save Deck Sort button
        if self._save_sort_rect and self._save_sort_rect.collidepoint(mx, my):
            if event.button == 1:
                return "save_deck_sort"
            return None
        # Browse button
        if self._discard_browse_rect and self._discard_browse_rect.collidepoint(mx, my):
            if event.button == 1:
                self._browse_discard         = True
                self._browse_scroll          = 0
                self._browse_thumb_sz        = 90
                self._browse_flipped         = set()
                self._browse_last_click_time = 0
                self.show_browse      = True
            return None
        # Discard card thumbnail area
        if self._discard_card_rect and self._discard_card_rect.collidepoint(mx, my):
            if event.button == 1 and self.discard_pile:
                return "discard_drag_start"
            if event.button == 3 and self.discard_pile:
                return "discard_take_top"
            return None
        # Remainder of discard rect → toggle selection (left-click) or take top (right-click)
        if self._discard_rect and self._discard_rect.collidepoint(mx, my):
            if event.button == 1:
                self.discard_selected = not self.discard_selected
            elif event.button == 3 and self.discard_pile:
                return "discard_take_top"
        return None

    def _reanchor_buttons(self, sh):
        x  = 10
        w  = self.width - 20
        gap   = 4
        opt_w = (w - gap) * 3 // 4
        rp_w  = w - gap - opt_w
        opt_x = x + rp_w + gap
        positions = {
            "right_panel":  (x,     sh - 44, rp_w,  30),
            "options":      (opt_x, sh - 44, opt_w, 30),
            "reset":        (x, sh - 72,  w, 22),
            "browse_pile":  (x, sh - 102, w, 24),
            "draw_all":     (x, sh - 136, w, 28),
            "draw":         (x, sh - 170, w, 28),
            "choose_decks": (x, sh - 202, w, 26),
        }
        for name, rect in positions.items():
            if name in self._buttons:
                self._buttons[name].rect = pygame.Rect(rect)
        # Keep right_panel button color in sync with panel state
        if "right_panel" in self._buttons:
            self._buttons["right_panel"].color = BTN_ACTIVE if self.show_right_panel else BTN_BG

    def _draw_pile_list(self, screen, sh):
        piles    = self.active_piles
        x        = 10
        w        = self.width - 20
        list_bot = self._list_bot(sh)
        list_h   = list_bot - PILE_LIST_TOP

        # Clamp scroll to valid range
        total_h    = self._total_content_h()
        max_scroll = max(0, total_h - list_h)
        self._scroll_offset = max(0, min(max_scroll, self._scroll_offset))

        # Scrollbar
        if total_h > list_h:
            frac_top = self._scroll_offset / total_h
            frac_bot = min(1.0, (self._scroll_offset + list_h) / total_h)
            pygame.draw.rect(screen, (70, 70, 100),
                             (self.width - 5, PILE_LIST_TOP, 3, list_h))
            pygame.draw.rect(screen, ACCENT,
                             (self.width - 5,
                              PILE_LIST_TOP + int(frac_top * list_h),
                              3, max(8, int((frac_bot - frac_top) * list_h))))

        screen.set_clip(pygame.Rect(0, PILE_LIST_TOP, self.width, list_h))

        if not piles:
            screen.blit(self._font_small.render("No active decks.", True, DIM_COLOR),
                        (x + 4, PILE_LIST_TOP + 8))
            screen.blit(self._font_small.render("Use Choose Decks...", True, DIM_COLOR),
                        (x + 4, PILE_LIST_TOP + 24))
            screen.set_clip(None)
            return

        rows          = self._build_row_list()
        drag_insert   = (self._drag_insert_at(self._drag_pile_y, sh)
                         if self._drag_active and self._drag_pile_idx is not None else None)
        header_insert = (self._header_insert_at(self._drag_pile_y, sh)
                         if self._drag_active and self._drag_header_name is not None else None)
        y             = PILE_LIST_TOP - self._scroll_offset

        for row in rows:
            kind = row[0]

            # ── Collection header ─────────────────────────────────────────────
            if kind == 'header':
                parent_name  = row[1]
                ry = y
                y += HEADER_ROW_H
                if ry + HEADER_ROW_H <= PILE_LIST_TOP or ry >= list_bot:
                    continue

                # Header drag: drop indicator line before this collection
                if header_insert == parent_name:
                    pygame.draw.rect(screen, ACCENT, (x, ry - 2, w, 3), border_radius=2)

                is_header_dragging = (self._drag_active
                                      and self._drag_header_name == parent_name)
                collapsed = parent_name in self._collapsed_parents
                n_piles   = sum(1 for p in piles if p.parent_name == parent_name)
                n_sel     = sum(1 for i, p in enumerate(piles)
                                if p.parent_name == parent_name
                                and i in self._selected_indices)

                alpha = 60 if is_header_dragging else 255
                hdr_surf = pygame.Surface((w, HEADER_ROW_H - 2), pygame.SRCALPHA)
                hdr_surf.fill((40, 40, 55, alpha))
                screen.blit(hdr_surf, (x, ry + 1))

                arrow = ">" if collapsed else "v"
                label = parent_name
                max_label_w = w - 44
                while self._font_small.size(f"{arrow} {label}")[0] > max_label_w and len(label) > 4:
                    label = label[:-1]
                txt_color = (*ACCENT, alpha)
                screen.blit(self._font_small.render(f"{arrow} {label}", True, ACCENT),
                            (x + 4, ry + 4))

                cnt = f"{n_piles}" + (f"  ({n_sel})" if n_sel else "")
                cnt_surf = self._font_small.render(cnt, True, DIM_COLOR)
                screen.blit(cnt_surf, (x + w - cnt_surf.get_width() - 4, ry + 4))

            # ── Pile row ──────────────────────────────────────────────────────
            else:
                pile_idx = row[1]
                deck     = piles[pile_idx]
                row_y    = y
                y       += PILE_ROW_H
                if row_y + PILE_ROW_H <= PILE_LIST_TOP or row_y >= list_bot:
                    continue

                is_dragging = self._drag_active and pile_idx == self._drag_pile_idx
                selected    = pile_idx in self._selected_indices
                focused     = pile_idx == self._focused_idx

                # Drag insertion indicator (line before this pile)
                if drag_insert is not None and drag_insert == pile_idx:
                    pygame.draw.rect(screen, ACCENT,
                                     (x, row_y - 2, w, 3), border_radius=2)

                alpha    = 80 if is_dragging else 255
                bg       = BTN_ACTIVE if selected else (45, 45, 60)
                row_surf = pygame.Surface((w, PILE_ROW_H - 4), pygame.SRCALPHA)
                row_surf.fill((*bg, alpha))
                screen.blit(row_surf, (x, row_y + 2))

                if focused:
                    pygame.draw.rect(screen, ACCENT,
                                     (x, row_y + 2, w, PILE_ROW_H - 4), 2, border_radius=5)
                else:
                    pygame.draw.rect(screen, (*bg, alpha),
                                     (x, row_y + 2, w, PILE_ROW_H - 4), border_radius=5)

                # Thumbnail
                thumb   = self._get_back_thumb(deck)
                tw, th  = thumb.get_size()
                thumb_x = x + 4 + (PILE_THUMB_W - tw) // 2
                thumb_y = row_y + (PILE_ROW_H - th) // 2
                screen.blit(thumb, (thumb_x, thumb_y))

                # Text — strip parent prefix so "SE / Agents" shows as "Agents" under its header
                tx     = x + PILE_THUMB_W + 10
                tw_max = w - PILE_THUMB_W - 14
                prefix = deck.parent_name + " / "
                name   = deck.display_name
                if name.startswith(prefix):
                    name = name[len(prefix):]
                while self._font_small.size(name)[0] > tw_max and len(name) > 4:
                    name = name[:-1]
                screen.blit(self._font_small.render(name, True, TEXT_COLOR),
                            (tx, row_y + 10))
                count_str   = (f"{deck.cards_remaining}/{len(deck)}" if deck.has_back
                               else f"{len(deck)} cards")
                count_color = (200, 220, 255) if selected else DIM_COLOR
                screen.blit(self._font_small.render(count_str, True, count_color),
                            (tx, row_y + 26))

        # Insertion indicator after last pile (pile drag)
        if drag_insert is not None and drag_insert == len(piles):
            pygame.draw.rect(screen, ACCENT, (x, y - 2, w, 3), border_radius=2)

        # Insertion indicator after all groups (header drag — append at end)
        if self._drag_active and self._drag_header_name is not None and header_insert is None:
            pygame.draw.rect(screen, ACCENT, (x, y - 2, w, 3), border_radius=2)

        # Pile drag ghost
        if self._drag_active and self._drag_pile_idx is not None:
            drag_deck  = piles[self._drag_pile_idx]
            ghost_y    = self._drag_pile_y - PILE_ROW_H // 2
            ghost_surf = pygame.Surface((w, PILE_ROW_H - 4), pygame.SRCALPHA)
            ghost_surf.fill((100, 140, 200, 160))
            screen.blit(ghost_surf, (x, ghost_y))
            prefix = drag_deck.parent_name + " / "
            name   = drag_deck.display_name
            if name.startswith(prefix):
                name = name[len(prefix):]
            while self._font_small.size(name)[0] > w - 10 and len(name) > 4:
                name = name[:-1]
            screen.blit(self._font_small.render(name, True, TEXT_COLOR),
                        (x + 6, ghost_y + 10))

        # Header drag ghost
        if self._drag_active and self._drag_header_name is not None:
            ghost_y    = self._drag_pile_y - HEADER_ROW_H // 2
            ghost_surf = pygame.Surface((w, HEADER_ROW_H - 2), pygame.SRCALPHA)
            ghost_surf.fill((80, 110, 180, 200))
            screen.blit(ghost_surf, (x, ghost_y))
            label = self._drag_header_name
            while self._font_small.size(f"= {label}")[0] > w - 10 and len(label) > 4:
                label = label[:-1]
            screen.blit(self._font_small.render(f"= {label}", True, TEXT_COLOR),
                        (x + 4, ghost_y + 4))

        screen.set_clip(None)
        pygame.draw.line(screen, (70, 70, 90),
                         (x, list_bot + 2), (x + w, list_bot + 2), 1)

    # ── Deck picker overlay ───────────────────────────────────────────────────

    def _draw_picker(self, screen, sw, sh):
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        panel_w = min(500, sw - self.width - 40)
        panel_h = min(500, sh - 80)
        px      = self.width + (sw - self.width - panel_w) // 2
        py      = (sh - panel_h) // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((20, 20, 35, 245))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, ACCENT, (px, py, panel_w, panel_h), 2, border_radius=8)

        screen.blit(self._font_large.render("Select Active Decks", True, ACCENT),
                    (px + 12, py + 12))

        parent_names = self._unique_parents()
        row_h        = 34
        list_top     = py + 50
        list_bot     = py + panel_h - 60
        visible_rows = max(1, (list_bot - list_top) // row_h)

        screen.set_clip(pygame.Rect(px, list_top, panel_w, list_bot - list_top))
        for i in range(visible_rows + 1):
            idx = i + self._picker_scroll
            if idx >= len(parent_names):
                break
            name   = parent_names[idx]
            row_y  = list_top + i * row_h
            active = name in self._active_parents
            bg = (50, 80, 50) if active else (40, 40, 55)
            pygame.draw.rect(screen, bg,
                             (px + 10, row_y + 2, panel_w - 20, row_h - 4), border_radius=5)
            check = "[x]" if active else "[ ]"
            screen.blit(self._font_med.render(f"  {check}  {name}", True, TEXT_COLOR),
                        (px + 14, row_y + 8))
        screen.set_clip(None)

        btn_y = py + panel_h - 52
        for label, bx, bw in [("Select All", px + 10, 130),
                               ("Clear All",  px + 150, 110),
                               ("Confirm",    px + panel_w - 120, 110)]:
            color = BTN_ACTIVE if label == "Confirm" else BTN_BG
            pygame.draw.rect(screen, color, (bx, btn_y, bw, 28), border_radius=6)
            pygame.draw.rect(screen, (80, 80, 100), (bx, btn_y, bw, 28), 1, border_radius=6)
            t = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(t, (bx + bw // 2 - t.get_width() // 2, btn_y + 7))

    # ── Browse overlay ────────────────────────────────────────────────────────

    def _draw_browse_overlay(self, screen, sw, sh):
        if self._browse_discard:
            self._draw_browse_discard(screen, sw, sh)
            return
        deck = self.focused_deck
        if not deck:
            return

        panel_x      = self.width + 20
        right_margin = self.right_panel_width if (self.show_right_panel or self.show_options) else 0
        panel_w      = sw - panel_x - 20 - right_margin
        panel_y      = 20
        panel_h      = sh - 40

        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill((15, 15, 28, 240))
        screen.blit(overlay, (panel_x, panel_y))
        pygame.draw.rect(screen, ACCENT, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=8)

        drawn      = deck._drawn_paths
        trashed    = deck._trashed_paths
        if self.browse_shuffle_order and deck._draw_pile:
            available = list(reversed(deck._draw_pile))
        else:
            available  = [p for p in deck._all_fronts if p not in drawn and p not in trashed]
        in_play    = [p for p in deck._all_fronts if p in drawn   and p not in trashed]
        trash_list = [p for p in deck._all_fronts if p in trashed]
        n_avail    = len(available)
        n_inplay   = len(in_play)
        n_trash    = len(trash_list)

        screen.blit(self._font_large.render(
            f"Browse: {deck.display_name}  "
            f"({n_avail} available  /  {n_inplay} in play  /  {n_trash} trashed)",
            True, ACCENT), (panel_x + 12, panel_y + 12))

        close_rect = pygame.Rect(panel_x + panel_w - 36, panel_y + 8, 28, 28)
        pygame.draw.rect(screen, BTN_WARN, close_rect, border_radius=5)
        cx = self._font_med.render("X", True, TEXT_COLOR)
        screen.blit(cx, cx.get_rect(center=close_rect.center))

        thumb_sz     = self._browse_thumb_sz
        cols         = max(1, (panel_w - 30) // (thumb_sz + 10))
        cell_w       = (panel_w - 20) // cols
        cell_h       = thumb_sz + 16
        grid_top     = panel_y + 50
        grid_h       = panel_h - 70

        n_avail_rows = (n_avail  + cols - 1) // cols if n_avail  else 0
        n_play_rows  = (n_inplay + cols - 1) // cols if n_inplay else 0
        n_trash_rows = (n_trash  + cols - 1) // cols if n_trash  else 0
        sep1_rows    = 1 if in_play    else 0
        sep2_rows    = 1 if trash_list else 0
        total_rows   = n_avail_rows + sep1_rows + n_play_rows + sep2_rows + n_trash_rows
        visible_rows = max(1, grid_h // cell_h)

        dim_alpha = self.drawn_card_dim
        play_dim  = pygame.Surface((thumb_sz, thumb_sz), pygame.SRCALPHA) if (in_play    and dim_alpha > 0) else None
        trash_dim = pygame.Surface((thumb_sz, thumb_sz), pygame.SRCALPHA) if (trash_list and dim_alpha > 0) else None
        if play_dim:  play_dim.fill((0,   0,  0, dim_alpha))
        if trash_dim: trash_dim.fill((80, 20, 20, min(255, dim_alpha + 60)))

        def _draw_cards(card_list, vrow, row_off, dim_surf, sep_offset):
            section_row = vrow - sep_offset
            for col in range(cols):
                idx = section_row * cols + col
                if idx >= len(card_list):
                    break
                path    = card_list[idx]
                flipped = path in self._browse_flipped
                display = (deck.card_back_for(path) or path) if flipped else path
                thumb   = self._get_browse_thumb(display, thumb_sz)
                tw, th  = thumb.get_size()
                tx = panel_x + 10 + col * cell_w + (cell_w - tw) // 2
                ty = grid_top + row_off * cell_h + (cell_h - th) // 2
                screen.blit(thumb, (tx, ty))
                if dim_surf:
                    screen.blit(dim_surf, (tx, ty))
                if flipped:
                    pygame.draw.rect(screen, (255, 180, 50), (tx, ty, tw, th), 2, border_radius=3)

        screen.set_clip(pygame.Rect(panel_x, grid_top, panel_w, grid_h))
        for row_off in range(visible_rows + 1):
            vrow = row_off + self._browse_scroll

            if vrow < n_avail_rows:
                _draw_cards(available, vrow, row_off, None, 0)

            elif sep1_rows and vrow == n_avail_rows:
                mid_y = grid_top + row_off * cell_h + cell_h // 2
                pygame.draw.line(screen, (80, 80, 110),
                                 (panel_x + 10, mid_y), (panel_x + panel_w - 10, mid_y), 1)
                lbl = self._font_small.render(f"— In Play  ({n_inplay}) —", True, DIM_COLOR)
                screen.blit(lbl, (panel_x + panel_w // 2 - lbl.get_width() // 2, mid_y - 8))

            elif vrow < n_avail_rows + sep1_rows + n_play_rows:
                _draw_cards(in_play, vrow, row_off, play_dim, n_avail_rows + sep1_rows)

            elif sep2_rows and vrow == n_avail_rows + sep1_rows + n_play_rows:
                mid_y = grid_top + row_off * cell_h + cell_h // 2
                pygame.draw.line(screen, (110, 55, 55),
                                 (panel_x + 10, mid_y), (panel_x + panel_w - 10, mid_y), 1)
                lbl = self._font_small.render(f"— Trashed  ({n_trash}) —", True, (180, 80, 80))
                screen.blit(lbl, (panel_x + panel_w // 2 - lbl.get_width() // 2, mid_y - 8))

            else:
                trash_off = n_avail_rows + sep1_rows + n_play_rows + sep2_rows
                _draw_cards(trash_list, vrow, row_off, trash_dim, trash_off)

        screen.set_clip(None)

        if total_rows > visible_rows:
            pygame.draw.rect(screen, (70, 70, 100),
                             (panel_x + panel_w - 6, grid_top, 4, grid_h))
            frac_top = self._browse_scroll / total_rows
            frac_bot = min(1.0, (self._browse_scroll + visible_rows) / total_rows)
            pygame.draw.rect(screen, ACCENT,
                             (panel_x + panel_w - 6,
                              grid_top + int(frac_top * grid_h),
                              4, max(10, int((frac_bot - frac_top) * grid_h))))

        hint = self._font_small.render(
            "Double-click to add  ·  Right-click to flip  ·  Ctrl+Scroll to zoom  ·  Esc to close",
            True, DIM_COLOR)
        screen.blit(hint, (panel_x + panel_w // 2 - hint.get_width() // 2,
                           panel_y + panel_h - 18))

    def _draw_browse_discard(self, screen, sw, sh):
        panel_x      = self.width + 20
        right_margin = self.right_panel_width if (self.show_right_panel or self.show_options) else 0
        panel_w      = sw - panel_x - 20 - right_margin
        panel_y = 20
        panel_h = sh - 40
        n_cards = len(self.discard_pile)

        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill((15, 15, 28, 240))
        screen.blit(overlay, (panel_x, panel_y))
        pygame.draw.rect(screen, (180, 55, 55), (panel_x, panel_y, panel_w, panel_h), 2,
                         border_radius=8)

        screen.blit(self._font_large.render(
            f"Discard Pile  ({n_cards} cards)", True, (210, 80, 80)),
            (panel_x + 12, panel_y + 12))

        close_rect = pygame.Rect(panel_x + panel_w - 36, panel_y + 8, 28, 28)
        pygame.draw.rect(screen, BTN_WARN, close_rect, border_radius=5)
        cx = self._font_med.render("X", True, TEXT_COLOR)
        screen.blit(cx, cx.get_rect(center=close_rect.center))

        thumb_sz     = self._browse_thumb_sz
        cols         = max(1, (panel_w - 30) // (thumb_sz + 10))
        cell_w       = (panel_w - 20) // cols
        cell_h       = thumb_sz + 16
        grid_top     = panel_y + 50
        grid_h       = panel_h - 70
        rows         = max(1, (n_cards + cols - 1) // cols)
        visible_rows = max(1, grid_h // cell_h)
        self._browse_scroll = min(self._browse_scroll, max(0, rows - visible_rows))

        screen.set_clip(pygame.Rect(panel_x, grid_top, panel_w, grid_h))
        for row_off in range(visible_rows + 1):
            row = row_off + self._browse_scroll
            for col in range(cols):
                idx = row * cols + col
                if idx >= n_cards:
                    break
                card  = self.discard_pile[idx]
                thumb = self._get_card_thumb(card, thumb_sz)
                tw, th = thumb.get_size()
                tx = panel_x + 10 + col * cell_w + (cell_w - tw) // 2
                ty = grid_top + row_off * cell_h + (cell_h - th) // 2
                screen.blit(thumb, (tx, ty))
                if idx == n_cards - 1:  # highlight top card
                    pygame.draw.rect(screen, (255, 80, 80), (tx, ty, tw, th), 2, border_radius=3)
        screen.set_clip(None)

        if rows > visible_rows:
            pygame.draw.rect(screen, (70, 70, 100),
                             (panel_x + panel_w - 6, grid_top, 4, grid_h))
            frac_top = self._browse_scroll / rows
            frac_bot = min(1.0, (self._browse_scroll + visible_rows) / rows)
            pygame.draw.rect(screen, (200, 60, 60),
                             (panel_x + panel_w - 6,
                              grid_top + int(frac_top * grid_h),
                              4, max(10, int((frac_bot - frac_top) * grid_h))))

        hint = self._font_small.render(
            "Double-click to return to table  ·  Ctrl+Scroll to zoom  ·  Esc to close",
            True, DIM_COLOR)
        screen.blit(hint, (panel_x + panel_w // 2 - hint.get_width() // 2,
                           panel_y + panel_h - 18))

    # ── Background picker overlay ─────────────────────────────────────────────

    def _bg_picker_rects(self, sw, sh):
        """Return dict of named rects for the background picker panel."""
        panel_w = min(520, sw - self.width - 40)
        panel_h = min(480, sh - 60)
        px = self.width + (sw - self.width - panel_w) // 2
        py = (sh - panel_h) // 2

        thumb_w, thumb_h = 100, 80
        img_cols = max(1, (panel_w - 20) // (thumb_w + 10))
        cell_w   = (panel_w - 20) // img_cols
        cell_h   = thumb_h + 10

        img_grid_top = py + 64          # header (44) + label (20)
        img_grid_h   = cell_h * 2       # 2 visible rows

        rects = {
            'panel':       pygame.Rect(px, py, panel_w, panel_h),
            'close':       pygame.Rect(px + panel_w - 36, py + 8, 28, 28),
            'img_grid':    pygame.Rect(px + 10, img_grid_top, panel_w - 20, img_grid_h),
            '_img_cols':   img_cols,
            '_cell_w':     cell_w,
            '_cell_h':     cell_h,
            '_img_grid_top': img_grid_top,
        }

        # Tile / Center toggle buttons below the grid
        fit_y = img_grid_top + img_grid_h + 6
        half  = (panel_w - 20) // 2 - 4
        rects['fit_tile']   = pygame.Rect(px + 10,           fit_y, half, 26)
        rects['fit_center'] = pygame.Rect(px + 10 + half + 8, fit_y, half, 26)

        # Separator + color section
        color_top = fit_y + 26 + 18 + 20  # fit row + separator(12) + label(20) - some spacing
        swatch_sz  = 28
        swatch_gap = 6
        n_sw       = len(_BG_PRESET_SWATCHES)
        total_sw_w = n_sw * swatch_sz + (n_sw - 1) * swatch_gap
        sw_x_start = px + (panel_w - total_sw_w) // 2
        for i in range(n_sw):
            sx = sw_x_start + i * (swatch_sz + swatch_gap)
            rects[f'swatch_{i}'] = pygame.Rect(sx, color_top, swatch_sz, swatch_sz)

        hex_row_y = color_top + swatch_sz + 8
        rects['hex_input'] = pygame.Rect(px + 10,       hex_row_y, 130, 28)
        rects['apply_btn'] = pygame.Rect(px + 10 + 138, hex_row_y,  70, 28)

        none_y = hex_row_y + 28 + 8
        rects['none_btn'] = pygame.Rect(px + 10, none_y, panel_w - 20, 28)

        # Store computed color_top and fit_y for drawing
        rects['_color_top'] = color_top
        rects['_fit_y']     = fit_y

        return rects

    def _handle_bg_picker_event(self, event, sw, sh, mx, my):
        rects = self._bg_picker_rects(sw, sh)

        # Escape closes
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.show_bg_picker = False
                self._bg_hex_active = False
                return None
            if self._bg_hex_active:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._apply_hex_color()
                elif event.key == pygame.K_BACKSPACE:
                    self._bg_hex_input = self._bg_hex_input[:-1]
                    self._bg_hex_error = False
                elif event.unicode:
                    ch = event.unicode
                    if ch in "0123456789abcdefABCDEF":
                        if len(self._bg_hex_input) < 6:
                            self._bg_hex_input += ch
                            self._bg_hex_error = False
                    elif ch == "#" and len(self._bg_hex_input) == 0:
                        pass  # ignore # prefix — we strip it on apply
            return None

        if event.type == pygame.MOUSEWHEEL:
            img_cols  = rects['_img_cols']
            n_images  = len(self._bg_table_images)
            n_rows    = max(0, (n_images + img_cols - 1) // img_cols - 2)
            self._bg_img_scroll = max(0, min(n_rows, self._bg_img_scroll - event.y))
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        if not rects['panel'].collidepoint(mx, my):
            self.show_bg_picker = False
            self._bg_hex_active = False
            return None

        if rects['close'].collidepoint(mx, my):
            self.show_bg_picker = False
            self._bg_hex_active = False
            return None

        if rects['hex_input'].collidepoint(mx, my):
            self._bg_hex_active = True
            return None

        self._bg_hex_active = False

        if rects['apply_btn'].collidepoint(mx, my):
            self._apply_hex_color()
            return None

        if rects['none_btn'].collidepoint(mx, my):
            self.bg_mode       = "color"
            self.bg_color      = (34, 34, 48)
            self.bg_image_path = None
            self._bg_surface   = None
            settings.save(self)
            return None

        if rects['fit_tile'].collidepoint(mx, my):
            self.bg_image_fit = "tile"
            self._bg_surface  = None
            self._bg_cache_key = None
            settings.save(self)
            return None

        if rects['fit_center'].collidepoint(mx, my):
            self.bg_image_fit  = "center"
            self._bg_surface   = None
            self._bg_cache_key = None
            settings.save(self)
            return None

        for i in range(len(_BG_PRESET_SWATCHES)):
            key = f'swatch_{i}'
            if key in rects and rects[key].collidepoint(mx, my):
                self.bg_mode       = "color"
                self.bg_color      = _BG_PRESET_SWATCHES[i]
                self.bg_image_path = None
                self._bg_surface   = None
                settings.save(self)
                return None

        img_grid_rect = rects['img_grid']
        if img_grid_rect.collidepoint(mx, my):
            img_cols  = rects['_img_cols']
            cell_w    = rects['_cell_w']
            cell_h    = rects['_cell_h']
            grid_top  = rects['_img_grid_top']
            rel_x     = mx - (rects['panel'].x + 10)
            rel_y     = my - grid_top
            col       = rel_x // cell_w
            row       = rel_y // cell_h + self._bg_img_scroll
            idx       = row * img_cols + col
            if 0 <= col < img_cols and 0 <= idx < len(self._bg_table_images):
                self.bg_image_path = self._bg_table_images[idx]
                self.bg_mode       = "image"
                self._bg_surface   = None
                self._bg_cache_key = None
                settings.save(self)

        return None

    def _draw_bg_picker(self, screen, sw, sh):
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        rects  = self._bg_picker_rects(sw, sh)
        px     = rects['panel'].x
        py     = rects['panel'].y
        pw     = rects['panel'].width
        ph     = rects['panel'].height

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((20, 20, 35, 245))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, ACCENT, (px, py, pw, ph), 2, border_radius=8)

        # Header
        screen.blit(self._font_large.render("Table Background", True, ACCENT), (px + 12, py + 10))
        pygame.draw.line(screen, (70, 70, 90), (px + 10, py + 44), (px + pw - 10, py + 44), 1)

        close_rect = rects['close']
        pygame.draw.rect(screen, BTN_WARN, close_rect, border_radius=5)
        cx = self._font_med.render("X", True, TEXT_COLOR)
        screen.blit(cx, cx.get_rect(center=close_rect.center))

        # ---- Image section ----
        img_grid_top = rects['_img_grid_top']
        screen.blit(self._font_small.render("TABLE IMAGES", True, DIM_COLOR),
                    (px + 10, img_grid_top - 18))

        img_grid_rect = rects['img_grid']
        img_cols = rects['_img_cols']
        cell_w   = rects['_cell_w']
        cell_h   = rects['_cell_h']
        thumb_w  = cell_w - 10
        thumb_h  = cell_h - 10

        if not self._bg_table_images:
            screen.blit(self._font_small.render("No images found in tables/", True, DIM_COLOR),
                        (px + 14, img_grid_top + 20))
        else:
            screen.set_clip(img_grid_rect)
            visible_rows = 2
            for row_off in range(visible_rows):
                row = row_off + self._bg_img_scroll
                for col in range(img_cols):
                    idx = row * img_cols + col
                    if idx >= len(self._bg_table_images):
                        break
                    path = self._bg_table_images[idx]
                    key  = (path, thumb_w, thumb_h)
                    if key not in self._bg_thumb_cache:
                        try:
                            self._bg_thumb_cache[key] = _pil_fit_surface(path, thumb_w, thumb_h)
                        except Exception:
                            surf = pygame.Surface((thumb_w, thumb_h))
                            surf.fill((60, 60, 60))
                            self._bg_thumb_cache[key] = surf
                    thumb    = self._bg_thumb_cache[key]
                    tw, th   = thumb.get_size()
                    tx = px + 10 + col * cell_w + (cell_w - tw) // 2
                    ty = img_grid_top + row_off * cell_h + (cell_h - th) // 2
                    screen.blit(thumb, (tx, ty))
                    if self.bg_mode == "image" and path == self.bg_image_path:
                        pygame.draw.rect(screen, ACCENT, (tx, ty, tw, th), 2, border_radius=3)
            screen.set_clip(None)

        # ---- Tile / Center toggle ----
        fit_y = rects['_fit_y']
        for key, label, mode in (('fit_tile', 'Tile', 'tile'), ('fit_center', 'Center', 'center')):
            r     = rects[key]
            color = BTN_ACTIVE if self.bg_image_fit == mode else BTN_BG
            pygame.draw.rect(screen, color,          r, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100),  r, 1, border_radius=4)
            ls = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(ls, ls.get_rect(center=r.center))

        # ---- Separator + color section ----
        sep_y = fit_y + 26 + 6
        pygame.draw.line(screen, (70, 70, 90), (px + 10, sep_y), (px + pw - 10, sep_y), 1)
        color_top = rects['_color_top']
        screen.blit(self._font_small.render("BACKGROUND COLOR", True, DIM_COLOR),
                    (px + 10, sep_y + 6))

        # Swatches
        for i, swatch_color in enumerate(_BG_PRESET_SWATCHES):
            key = f'swatch_{i}'
            if key not in rects:
                continue
            srect = rects[key]
            pygame.draw.rect(screen, swatch_color, srect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100),  srect, 1, border_radius=4)
            if self.bg_mode == "color" and self.bg_color == swatch_color:
                pygame.draw.rect(screen, ACCENT, srect, 2, border_radius=4)

        # Hex input
        hex_rect   = rects['hex_input']
        apply_rect = rects['apply_btn']
        border_col = (200, 80, 80) if self._bg_hex_error else (ACCENT if self._bg_hex_active else (80, 80, 100))
        pygame.draw.rect(screen, (40, 40, 55), hex_rect, border_radius=4)
        pygame.draw.rect(screen, border_col,   hex_rect, 1, border_radius=4)
        if self._bg_hex_input:
            disp_text  = "#" + self._bg_hex_input
            text_color = TEXT_COLOR
        else:
            disp_text  = "#RRGGBB"
            text_color = DIM_COLOR
        screen.blit(self._font_small.render(disp_text, True, text_color),
                    (hex_rect.x + 6, hex_rect.y + 7))
        if self._bg_hex_active:
            cursor_x = hex_rect.x + 6 + self._font_small.size(disp_text)[0] + 1
            pygame.draw.line(screen, TEXT_COLOR,
                             (cursor_x, hex_rect.y + 5), (cursor_x, hex_rect.y + 22), 1)

        pygame.draw.rect(screen, BTN_BG,        apply_rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 100), apply_rect, 1, border_radius=4)
        screen.blit(self._font_small.render("Apply", True, TEXT_COLOR),
                    (apply_rect.x + 8, apply_rect.y + 7))

        # None button
        none_rect = rects['none_btn']
        pygame.draw.rect(screen, BTN_BG,        none_rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 100), none_rect, 1, border_radius=5)
        screen.blit(self._font_small.render("None (reset to default)", True, TEXT_COLOR),
                    (none_rect.x + 8, none_rect.y + 7))

        # Footer
        hint = self._font_small.render("Esc or click outside to close", True, DIM_COLOR)
        screen.blit(hint, (px + pw // 2 - hint.get_width() // 2, py + ph - 18))

    # ── Options overlay ───────────────────────────────────────────────────────

    def _draw_options(self, screen, sw, sh):
        rects = self._options_rects(sw, sh, self._options_scroll_y)
        px = rects['panel'].x
        pw = rects['panel'].width
        content_h = rects['_content_h']

        # Panel background + left border line (matches right panel style)
        pygame.draw.rect(screen, SIDEBAR_BG, (px, 0, pw, sh))
        pygame.draw.line(screen, (70, 70, 90), (px, 0), (px, sh), 2)

        # Title — right-justified
        title = self._font_large.render("Options", True, ACCENT)
        screen.blit(title, (sw - 12 - title.get_width(), 12))

        # Separator below header
        pygame.draw.line(screen, (70, 70, 90), (px + 10, 40), (sw - 10, 40), 1)

        # Clip scrollable content to panel area below the header
        screen.set_clip(pygame.Rect(px, 41, pw, sh - 41))

        # Toggle items
        toggle_items = [
            ('pile_top_toggle',        "PileTop Thumbnail",    self.show_pile_top),
            ('face_down_toggle',       "Draw Face Down",       self.draw_face_down),
            ('random_rotation_toggle', "Random Rotation",      self.draw_random_rotation),
            ('tuck_toggle',            "Tuck (place under)",   self.tuck_mode),
            ('snap_to_grid_toggle',    "Snap to Grid",         self.snap_to_grid),
            ('save_with_bg_toggle',       "Save w/ Background",   self.save_with_bg),
            ('save_to_clipboard_toggle',  "Ctrl+S → Clipboard",   self.save_to_clipboard),
            ('delete_confirm_toggle',      "Confirm Delete",       self.delete_confirm),
            ('delete_discards_toggle',     "Delete → Discard",     self.delete_discards),
            ('keep_discard_orient_toggle', "Keep Discard Orient.", self.keep_discard_orientation),
            ('browse_shuffle_order_toggle', "Browse: Shuf. Order", self.browse_shuffle_order),
            ('show_grid_toggle',            "Dot Grid",            self.show_grid),
            ('load_confirm_toggle',         "Warn Before Load",     self.load_confirm),
            ('reset_on_loadout_toggle',     "Reset on Load",        self.reset_on_loadout),
        ]
        fi = self._font_icon or self._font_small
        for key, label, state in toggle_items:
            rect  = rects[key]
            # "Warn Before Load" is greyed out when Reset on Load is off
            disabled = (key == 'load_confirm_toggle' and not self.reset_on_loadout)
            color = CHK_ON if (state and not disabled) else BTN_BG
            pygame.draw.rect(screen, color, rect, border_radius=5)
            pygame.draw.rect(screen, (80, 80, 100), rect, 1, border_radius=5)
            txt_color = DIM_COLOR if disabled else TEXT_COLOR
            chk_char  = "\u2714" if state else "\u2716"   # ✔ / ✖
            chk_col   = ACCENT   if (state and not disabled) else DIM_COLOR
            chk_surf  = fi.render(chk_char, True, chk_col)
            screen.blit(chk_surf, chk_surf.get_rect(centery=rect.centery, x=rect.x + 8))
            lbl_surf = self._font_small.render(label, True, txt_color)
            screen.blit(lbl_surf, lbl_surf.get_rect(centery=rect.centery,
                                                     x=rect.x + 8 + chk_surf.get_width() + 6))

        # Snap grid size +/- buttons (overlaid on the snap_to_grid_toggle row)
        for btn_key, btn_lbl in (('snap_grid_minus', '-'), ('snap_grid_plus', '+')):
            br = rects[btn_key]
            pygame.draw.rect(screen, BTN_BG, br, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), br, 1, border_radius=4)
            screen.blit(self._font_small.render(btn_lbl, True, TEXT_COLOR),
                        self._font_small.render(btn_lbl, True, TEXT_COLOR).get_rect(center=br.center))
        sz_surf = self._font_small.render(f"{self.snap_grid_size}px", True, DIM_COLOR)
        snap_row = rects['snap_to_grid_toggle']
        screen.blit(sz_surf, (rects['snap_grid_minus'].x - sz_surf.get_width() - 4,
                               snap_row.y + 7))

        # Browse Dim row (label + value + -/+ buttons, no checkbox)
        dim_rect = rects['draw_dim_row']
        pygame.draw.rect(screen, BTN_BG, dim_rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 100), dim_rect, 1, border_radius=5)
        screen.blit(self._font_small.render("Browse Dim:", True, TEXT_COLOR),
                    (dim_rect.x + 8, dim_rect.y + 7))
        for btn_key, btn_lbl in (('dim_minus', '-'), ('dim_plus', '+')):
            br = rects[btn_key]
            pygame.draw.rect(screen, BTN_BG, br, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), br, 1, border_radius=4)
            t = self._font_small.render(btn_lbl, True, TEXT_COLOR)
            screen.blit(t, t.get_rect(center=br.center))
        dim_val = self._font_small.render(str(self.drawn_card_dim), True, DIM_COLOR)
        screen.blit(dim_val, (rects['dim_minus'].x - dim_val.get_width() - 4, dim_rect.y + 7))

        # Arrow Weight row (label + value + -/+ buttons)
        aw_rect = rects['arrow_weight_row']
        pygame.draw.rect(screen, BTN_BG, aw_rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 100), aw_rect, 1, border_radius=5)
        screen.blit(self._font_small.render("Arrow Weight:", True, TEXT_COLOR),
                    (aw_rect.x + 8, aw_rect.y + 7))
        for btn_key, btn_lbl in (('arrow_weight_minus', '-'), ('arrow_weight_plus', '+')):
            br = rects[btn_key]
            pygame.draw.rect(screen, BTN_BG, br, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), br, 1, border_radius=4)
            t = self._font_small.render(btn_lbl, True, TEXT_COLOR)
            screen.blit(t, t.get_rect(center=br.center))
        aw_val = self._font_small.render(str(self.default_arrow_weight), True, DIM_COLOR)
        screen.blit(aw_val, (rects['arrow_weight_minus'].x - aw_val.get_width() - 4, aw_rect.y + 7))

        # Default Card Size — 3-line grouped box
        box_rect = rects['card_size_box']
        pygame.draw.rect(screen, BTN_BG, box_rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 100), box_rect, 1, border_radius=5)
        # Header line: label + shared Reset button
        screen.blit(self._font_small.render("Default Card Size", True, TEXT_COLOR),
                    (box_rect.x + 8, box_rect.y + 8))
        rst_rect = rects['card_size_reset']
        rst_col  = ACCENT if (self.card_base_w != 500 or self.card_base_h != 500) else DIM_COLOR
        pygame.draw.rect(screen, BTN_BG, rst_rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 100), rst_rect, 1, border_radius=4)
        screen.blit(self._font_small.render("Reset", True, rst_col),
                    (rst_rect.x + 6, rst_rect.y + 4))
        # Divider under header
        div_y = box_rect.y + 4 + 24
        pygame.draw.line(screen, (60, 60, 80), (box_rect.x + 4, div_y), (box_rect.right - 4, div_y), 1)
        # Width and Height rows
        for row_key, label, attr, minus_key, plus_key, field_key, act_attr, inp_attr in (
            ('card_w_row', "Width:", 'card_base_w',
             'card_w_minus', 'card_w_plus', 'card_w_field', '_card_w_active', '_card_w_input'),
            ('card_h_row', "Height:", 'card_base_h',
             'card_h_minus', 'card_h_plus', 'card_h_field', '_card_h_active', '_card_h_input'),
        ):
            row_rect  = rects[row_key]
            is_active = getattr(self, act_attr)
            inp_str   = getattr(self, inp_attr)
            val       = getattr(self, attr)
            # Label
            screen.blit(self._font_small.render(label, True, TEXT_COLOR),
                        (row_rect.x + 8, row_rect.y + 6))
            # Input field
            fld_rect   = rects[field_key]
            fld_border = ACCENT if is_active else (80, 80, 100)
            pygame.draw.rect(screen, (40, 40, 55), fld_rect, border_radius=4)
            pygame.draw.rect(screen, fld_border,   fld_rect, 1, border_radius=4)
            disp_text = inp_str if is_active else str(val)
            txt_color = TEXT_COLOR if is_active else DIM_COLOR
            screen.blit(self._font_small.render(disp_text, True, txt_color),
                        (fld_rect.x + 5, fld_rect.y + 4))
            if is_active:
                cx = fld_rect.x + 5 + self._font_small.size(disp_text)[0] + 1
                pygame.draw.line(screen, TEXT_COLOR,
                                 (cx, fld_rect.y + 3), (cx, fld_rect.bottom - 3), 1)
            # -/+ buttons
            for btn_key, btn_lbl in ((minus_key, '-'), (plus_key, '+')):
                br = rects[btn_key]
                pygame.draw.rect(screen, BTN_BG, br, border_radius=4)
                pygame.draw.rect(screen, (80, 80, 100), br, 1, border_radius=4)
                t = self._font_small.render(btn_lbl, True, TEXT_COLOR)
                screen.blit(t, t.get_rect(center=br.center))

        # Separator above action buttons
        sep_y = rects['import_pdf'].top - 6
        pygame.draw.line(screen, (70, 70, 90), (px + 10, sep_y), (sw - 10, sep_y), 1)

        # Action buttons
        action_items = [
            ('import_pdf', "\U0001f4c4", "Import PDF Deck"),  # 📄
            ('controls',   "\u2753",     "Controls  [?]"),    # ❓
            ('background', "\U0001f3a8", "Background..."),    # 🎨
        ]
        for key, icon, label in action_items:
            rect = rects[key]
            pygame.draw.rect(screen, BTN_BG, rect, border_radius=5)
            pygame.draw.rect(screen, (80, 80, 100), rect, 1, border_radius=5)
            icon_surf = fi.render(icon, True, ACCENT)
            screen.blit(icon_surf, icon_surf.get_rect(centery=rect.centery, x=rect.x + 8))
            lbl_surf = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(lbl_surf, lbl_surf.get_rect(centery=rect.centery,
                                                     x=rect.x + 8 + icon_surf.get_width() + 6))

        # Startup loadout button
        sl_rect = rects['startup_loadout']
        pygame.draw.rect(screen, BTN_BG, sl_rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 100), sl_rect, 1, border_radius=5)
        sl_icon = fi.render("\U0001f4c2", True, ACCENT)   # 📂
        screen.blit(sl_icon, sl_icon.get_rect(centery=sl_rect.centery, x=sl_rect.x + 8))
        if self.default_loadout_path:
            sl_name = os.path.basename(self.default_loadout_path)
            sl_label = f"Startup: {sl_name}"
        else:
            sl_label = "Startup Loadout..."
        sl_lbl = self._font_small.render(sl_label, True, TEXT_COLOR)
        screen.blit(sl_lbl, sl_lbl.get_rect(centery=sl_rect.centery,
                                             x=sl_rect.x + 8 + sl_icon.get_width() + 6))
        if self.default_loadout_path:
            cl_rect = rects['startup_loadout_clear']
            pygame.draw.rect(screen, (100, 40, 40), cl_rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 100), cl_rect, 1, border_radius=4)
            t = (self._font_icon or self._font_small).render("\u2716", True, TEXT_COLOR)
            screen.blit(t, t.get_rect(center=cl_rect.center))

        # Reset clip
        screen.set_clip(None)

        # Scrollbar (only when content overflows)
        if content_h > sh:
            sb_x    = sw - 6
            sb_top  = 44
            sb_h    = sh - sb_top
            thumb_h = max(20, int(sb_h * sh / content_h))
            thumb_y = sb_top + int((sb_h - thumb_h) * self._options_scroll_y /
                                   max(1, content_h - sh))
            pygame.draw.rect(screen, (60, 60, 80), (sb_x, sb_top, 4, sb_h), border_radius=2)
            pygame.draw.rect(screen, (120, 120, 150), (sb_x, thumb_y, 4, thumb_h), border_radius=2)

    # ── Confirm-delete dialog ─────────────────────────────────────────────────

    def _confirm_delete_rects(self, sw, sh):
        panel_w, panel_h = 340, 144
        px = (sw - panel_w) // 2
        py = (sh - panel_h) // 2
        return {
            'panel':  pygame.Rect(px, py, panel_w, panel_h),
            'cancel': pygame.Rect(px + panel_w // 2 - 140, py + panel_h - 44, 120, 30),
            'delete': pygame.Rect(px + panel_w // 2 + 20,  py + panel_h - 44, 120, 30),
        }

    def draw_confirm_delete(self, screen, sw, sh):
        """Draw a modal confirmation dialog for permanent card removal."""
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        rects = self._confirm_delete_rects(sw, sh)
        px, py = rects['panel'].x, rects['panel'].y
        pw, ph = rects['panel'].width, rects['panel'].height

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((35, 18, 18, 250))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, (200, 80, 80), (px, py, pw, ph), 2, border_radius=8)

        title = self._font_large.render("Confirm Delete", True, (220, 110, 110))
        screen.blit(title, (px + 12, py + 10))
        pygame.draw.line(screen, (110, 55, 55), (px + 10, py + 38), (px + pw - 10, py + 38), 1)

        if self._confirm_delete_bulk_n > 0:
            msg_text = f"Remove all {self._confirm_delete_bulk_n} cards? This cannot be undone."
        else:
            msg_text = "Remove card from session? This cannot be undone."
        msg = self._font_small.render(msg_text, True, TEXT_COLOR)
        screen.blit(msg, (px + pw // 2 - msg.get_width() // 2, py + 52))

        mx, my = pygame.mouse.get_pos()
        for key, label, base_c, hover_c in [
            ('cancel', "Cancel",     BTN_BG,         BTN_HOVER),
            ('delete', "Delete",     (140, 50, 50),  (185, 70, 70)),
        ]:
            r = rects[key]
            color = hover_c if r.collidepoint(mx, my) else base_c
            pygame.draw.rect(screen, color, r, border_radius=5)
            pygame.draw.rect(screen, (80, 80, 100), r, 1, border_radius=5)
            t = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(t, t.get_rect(center=r.center))

    def handle_confirm_delete_event(self, event, sw, sh):
        """Process events for the confirm-delete dialog.
        Returns 'confirm', 'cancel', or None (keep dialog open)."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                return 'confirm'
            elif event.key == pygame.K_ESCAPE:
                return 'cancel'
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            rects = self._confirm_delete_rects(sw, sh)
            if rects['delete'].collidepoint(event.pos):
                return 'confirm'
            return 'cancel'   # click outside or on Cancel both cancel
        return None

    # ── Confirm-load-loadout dialog ───────────────────────────────────────────

    def _confirm_load_rects(self, sw, sh):
        panel_w, panel_h = 360, 130
        px = (sw - panel_w) // 2
        py = (sh - panel_h) // 2
        btn_y = py + panel_h - 42
        return {
            'panel':  pygame.Rect(px, py, panel_w, panel_h),
            'cancel': pygame.Rect(px + panel_w // 2 - 150, btn_y, 120, 28),
            'load':   pygame.Rect(px + panel_w // 2 + 30,  btn_y, 120, 28),
        }

    def draw_confirm_load(self, screen, sw, sh):
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        rects = self._confirm_load_rects(sw, sh)
        px, py = rects['panel'].x, rects['panel'].y
        pw, ph = rects['panel'].width, rects['panel'].height

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((20, 30, 50, 250))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, ACCENT, (px, py, pw, ph), 2, border_radius=8)

        title = self._font_large.render("Load Loadout?", True, ACCENT)
        screen.blit(title, (px + 12, py + 10))
        pygame.draw.line(screen, (50, 80, 120), (px + 10, py + 38), (px + pw - 10, py + 38), 1)

        msg = self._font_small.render("Cards will be returned to piles. Continue?", True, TEXT_COLOR)
        screen.blit(msg, (px + pw // 2 - msg.get_width() // 2, py + 50))

        mx, my = pygame.mouse.get_pos()
        for key, label, base_c, hover_c in [
            ('cancel', "Cancel", BTN_BG,     BTN_HOVER),
            ('load',   "Load",   BTN_ACTIVE, (130, 180, 255)),
        ]:
            r = rects[key]
            color = hover_c if r.collidepoint(mx, my) else base_c
            pygame.draw.rect(screen, color, r, border_radius=5)
            pygame.draw.rect(screen, (80, 80, 100), r, 1, border_radius=5)
            t = self._font_small.render(label, True, TEXT_COLOR)
            screen.blit(t, t.get_rect(center=r.center))

    def handle_confirm_load_event(self, event, sw, sh):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:  return 'confirm'
            if event.key == pygame.K_ESCAPE:  return 'cancel'
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            rects = self._confirm_load_rects(sw, sh)
            if rects['load'].collidepoint(event.pos):
                return 'confirm'
            return 'cancel'
        return None

    # ── Help overlay ──────────────────────────────────────────────────────────

    def _help_lines(self):
        return [
            # ── Card Actions (hovered card or full selection) ─────────────────
            ("D",                    "Draw random card (weighted by pile size)"),
            ("A",                    "Draw one card from each selected pile"),
            ("F",                    "Flip card face-up / face-down"),
            ("T",                    "Rotate card 180°"),
            ("R / E",                "Rotate card CW / CCW 90°"),
            ("Y / U",                "Rotate card 45° CW / reset rotation"),
            ("V",                    "Random rotation (0 / 90 / 180 / 270°)"),
            ("C",                    "Duplicate card(s) — copy placed offset, auto-selected"),
            ("Z",                    "Return card to its source pile"),
            ("X",                    "Send card to discard pile"),
            ("Delete",               "Remove card (per Options: confirm or discard)"),
            ("] / [",                "Move card forward / backward in z-order"),
            ("Home / End",           "Bring to top / send to bottom of z-order"),
            ("",                     ""),
            # ── Multi-Select ─────────────────────────────────────────────────
            ("Ctrl+A",               "Select all cards and arrows on table"),
            ("Esc",                  "Clear selection / cancel arrow placement"),
            ("Ctrl+click card",      "Toggle card in/out of selection"),
            ("Drag (empty canvas)",  "Box-select cards and arrows in a region"),
            ("Ctrl+drag (canvas)",   "Additive box-select"),
            ("Drag selected card",   "Move all selected cards and arrows together"),
            ("",                     ""),
            # ── Arrows ───────────────────────────────────────────────────────
            (",",                    "Toggle arrow placement mode (or use Session Panel)"),
            ("Click-drag (canvas)",  "Draw a new arrow while in placement mode"),
            ("Right-click",          "Cancel arrow placement"),
            ("Drag arrow body",      "Move arrow (moves all selected arrows too)"),
            ("Drag arrow endpoint",  "Resize / reposition arrow endpoint"),
            ("X / Delete",           "Remove hovered or selected arrow(s)"),
            ("",                     ""),
            # ── Bulk Table Actions ────────────────────────────────────────────
            ("Ctrl+Z",               "Return all table cards to their source piles"),
            ("Ctrl+X",               "Send all table cards to discard pile"),
            ("Ctrl+Delete",          "Delete all cards and arrows (per Options settings)"),
            ("",                     ""),
            # ── Drop Modifiers ────────────────────────────────────────────────
            ("Ctrl + drop",          "Toggle tuck mode on drop (card goes under)"),
            ("Alt + drop",           "Toggle snap-to-grid on drop"),
            ("",                     ""),
            # ── Pile Sidebar ─────────────────────────────────────────────────
            ("Right-click pile",     "Draw one card from that pile only"),
            ("Ctrl+click pile",      "Toggle pile in draw selection"),
            ("Ctrl+Alt+click pile",  "Select/deselect all piles with same name"),
            ("Ctrl+Alt+right pile",  "Draw from combined pool of matching piles"),
            ("Drag pile row",        "Reorder piles within a collection"),
            ("Drag header",          "Reorder collection groups"),
            ("Ctrl+click header",    "Collapse / expand all collections"),
            ("",                     ""),
            # ── Canvas Navigation ─────────────────────────────────────────────
            ("Scroll wheel",         "Zoom in / out (on canvas)"),
            ("Middle / Right drag",  "Pan the canvas"),
            ("",                     ""),
            # ── File & Session ────────────────────────────────────────────────
            ("Ctrl+S",               "Export PNG (or clipboard if enabled in Options)"),
            ("Ctrl+Shift+S",         "Save layout to JSON (any location)"),
            ("Ctrl+O",               "Load layout from JSON"),
            ("Session Panel (\u25b6)","Save/Load spreads and deck lists"),
            ("",                     ""),
            # ── App Controls ─────────────────────────────────────────────────
            ("?",                    "Toggle this Controls help"),
            ("Choose Decks",         "Pick which deck collections are active"),
            ("Browse Pile",          "Browse cards  \u00b7  Double-click to add"),
            ("Options",              "Settings, toggles, Import PDF, Background"),
            ("  Default W / H",      "Global fallback card size \u00b7 \u2212/+ adjust in 25 px steps \u00b7 R resets to 500"),
        ]

    def _draw_help(self, screen):
        sw, sh   = screen.get_size()
        panel_w  = 440
        px = self.width + (sw - self.width - panel_w) // 2

        lines    = self._help_lines()
        line_h   = 17
        spacer_h = 4
        header_h = 44
        footer_h = 26

        total_content_h = sum(spacer_h if not k else line_h for k, _ in lines)
        max_panel_h     = sh - 60
        visible_h       = min(total_content_h, max_panel_h - header_h - footer_h)
        panel_h         = header_h + visible_h + footer_h
        max_scroll      = max(0, total_content_h - visible_h)
        self._help_scroll = max(0, min(max_scroll, self._help_scroll))

        py = (sh - panel_h) // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((20, 20, 35, 235))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, ACCENT, (px, py, panel_w, panel_h), 2, border_radius=8)

        screen.blit(self._font_large.render("Keyboard & Mouse Controls", True, ACCENT),
                    (px + 12, py + 12))

        content_top = py + header_h
        content_bot = content_top + visible_h

        screen.set_clip(pygame.Rect(px, content_top, panel_w, visible_h))
        y = content_top - self._help_scroll
        for key, desc in lines:
            if not key:
                y += spacer_h
                continue
            if y + line_h > content_top and y < content_bot:
                screen.blit(self._font_med.render(key, True, ACCENT),        (px + 14, y))
                screen.blit(self._font_small.render(desc, True, TEXT_COLOR), (px + 190, y + 2))
            y += line_h
        screen.set_clip(None)

        # Scrollbar
        if max_scroll > 0:
            sb_x = px + panel_w - 7
            pygame.draw.rect(screen, (70, 70, 100), (sb_x, content_top, 4, visible_h))
            frac_top = self._help_scroll / total_content_h
            frac_bot = min(1.0, (self._help_scroll + visible_h) / total_content_h)
            pygame.draw.rect(screen, ACCENT,
                             (sb_x,
                              content_top + int(frac_top * visible_h),
                              4, max(10, int((frac_bot - frac_top) * visible_h))))

        if max_scroll > 0:
            hint_txt = "Scroll for more  ·  Press any key or click to close"
        else:
            hint_txt = "Press any key or click anywhere to close"
        close = self._font_small.render(hint_txt, True, DIM_COLOR)
        screen.blit(close, (px + panel_w // 2 - close.get_width() // 2, content_bot + 6))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _unique_parents(self):
        seen = []
        for d in self.decks:
            if d.parent_name not in seen:
                seen.append(d.parent_name)
        return sorted(seen)
