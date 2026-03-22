"""
Card Table - Story Prompting Card Deck App
==========================================
Run:  python main.py

Put your card images in:  decks/<deck_name>/*.png
  Or import a PDF via the sidebar button / python pdf_to_cards.py MyDeck.pdf

Controls: press ? in-app to see the full help overlay.
"""

import pygame
import sys
import os
import random

from card import Card
from arrow import Arrow, draw_arrow
from deck import load_decks, _stem, _pile_key, save_collection_config
from table import Table
from ui import Sidebar, SIDEBAR_MIN_W, SIDEBAR_MAX_W, RESIZE_ZONE, RIGHT_PANEL_MIN_W, RIGHT_PANEL_MAX_W
from io_utils import (save_dialog_json, load_dialog_json, save_dialog_png,
                      save_clipboard_png,
                      save_spread_dialog, load_spread_dialog,
                      save_loadout_dialog, load_loadout_dialog,
                      pick_loadout_file_dialog)
import settings

WINDOW_TITLE   = "Card Table"
INITIAL_WIDTH  = 1200
INITIAL_HEIGHT = 800
BG_COLOR       = (34, 34, 48)
FPS            = 60


def main():
    pygame.init()
    screen = pygame.display.set_mode(
        (INITIAL_WIDTH, INITIAL_HEIGHT),
        pygame.RESIZABLE
    )
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    decks_path = os.path.join(os.path.dirname(__file__), "decks")

    table   = Table()
    sidebar = Sidebar(INITIAL_HEIGHT)
    sidebar.init_fonts()
    settings.load(sidebar)

    decks = load_decks(decks_path,
                       default_card_w=sidebar.card_base_w,
                       default_card_h=sidebar.card_base_h)
    if not decks:
        print(f"⚠  No decks found in '{decks_path}'")
        print("   Create a subfolder under 'decks/' with PNG images,")
        print("   or use the '⊕ Import PDF Deck' button in the sidebar.")
    sidebar.set_decks(decks)

    if sidebar.default_loadout_path and os.path.exists(sidebar.default_loadout_path):
        try:
            import json as _json
            with open(sidebar.default_loadout_path, "r", encoding="utf-8") as _f:
                _ldata = _json.load(_f)
            sidebar._active_parents    = set(_ldata.get("active_parents", []))
            sidebar._collapsed_parents = set(_ldata.get("collapsed_parents", []))
        except Exception as _e:
            print(f"[startup] Could not apply default loadout: {_e}")

    _panning               = False
    _pan_last              = (0, 0)
    _hover_card            = None
    _hover_arrow           = None
    _hover_arrow_part      = None
    _sidebar_resizing      = False
    _right_panel_resizing  = False
    _confirm_delete_card        = None
    _confirm_load_active_parents   = None   # pending loadout to apply after confirm
    _confirm_load_collapsed_parents = None  # collapsed state to apply with the above
    _box_selecting         = False
    _box_start_s           = (0, 0)   # screen coords where box started
    _pending_click_card    = None     # card armed on mousedown; cleared on mouseup
    _pending_click_ctrl    = False
    _pending_click_pos     = (0, 0)
    _last_click_card       = None     # for double-click detection
    _last_click_time       = 0
    _pending_click_arrow   = None     # arrow armed on mousedown
    _pending_click_arrow_part = None
    _arrow_placing         = False    # True while arrow placement mode is active
    _arrow_preview         = None     # Arrow being drawn (during drag)
    CLICK_THRESHOLD        = 5        # px — below this = click, above = drag
    DBLCLICK_MS            = 300      # ms window for double-click
    _box_end_s             = (0, 0)   # screen coords current end

    # ------------------------------------------------------------------ helpers

    def reload_decks():
        nonlocal decks
        decks = load_decks(decks_path,
                           default_card_w=sidebar.card_base_w,
                           default_card_h=sidebar.card_base_h)
        sidebar.set_decks(decks)
        sidebar._preview_cache.clear()

    def draw_random():
        """Draw one card from the combined pool of all selected piles.

        Each card in each pile has equal probability of being drawn —
        piles are weighted by their current card count so larger piles
        contribute proportionally more draws.
        """
        sw, sh = screen.get_size()
        pool_decks  = list(sidebar.selected_decks)
        has_discard = sidebar.discard_selected and bool(sidebar.discard_pile)
        if not pool_decks and not has_discard:
            return

        # Weight each source by how many cards it currently holds.
        # Exhausted piles fall back to their full size so they are still
        # represented (draw_random() will reshuffle them automatically).
        sources = [p for p in pool_decks if len(p) > 0]
        weights = [p.cards_remaining or len(p._all_fronts) for p in sources]
        if has_discard:
            sources.append(None)          # None = discard sentinel
            weights.append(len(sidebar.discard_pile))

        chosen = random.choices(sources, weights=weights, k=1)[0]
        if chosen is None:
            card = sidebar.discard_pile.pop(random.randrange(len(sidebar.discard_pile)))
            card.is_face_down = False
        else:
            card = chosen.draw_random(face_down=sidebar.draw_face_down)
            if sidebar.draw_random_rotation:
                card.rotation = random.choice([0, 90, 180, 270])
        table.add_card(card, center_on_screen=True, screen_size=(sw, sh),
                       tuck=sidebar.tuck_mode)

    def draw_all():
        """Draw one card from each selected pile."""
        sw, sh = screen.get_size()
        for pile in sidebar.selected_decks:
            if not pile._all_fronts:
                continue
            card = pile.draw_random(face_down=sidebar.draw_face_down)
            if sidebar.draw_random_rotation:
                card.rotation = random.choice([0, 90, 180, 270])
            table.add_card(card, center_on_screen=True, screen_size=(sw, sh),
                           tuck=sidebar.tuck_mode)

    def draw_single_pile(pile_idx):
        """Draw one card from a specific pile (right-click)."""
        piles = sidebar.active_piles
        if 0 <= pile_idx < len(piles):
            pile = piles[pile_idx]
            sw, sh = screen.get_size()
            card = pile.draw_random(face_down=sidebar.draw_face_down)
            if sidebar.draw_random_rotation:
                card.rotation = random.choice([0, 90, 180, 270])
            table.add_card(card, center_on_screen=True, screen_size=(sw, sh),
                           tuck=sidebar.tuck_mode)

    def trash_card(card):
        """Mark card as permanently deleted (trashed) in its source deck."""
        pile = next((d for d in decks if d.display_name == card.deck_name), None)
        if pile is not None:
            pile.mark_trashed(getattr(card, "front_path", card.image_path))

    def discard_card(card):
        """Normalize card state then add to discard pile.
        By default resets to face-up and 0° rotation.
        With keep_discard_orientation, face and 90°-step rotation are preserved,
        but non-orthogonal rotations (e.g. 45°) are always reset to 0°."""
        if not sidebar.keep_discard_orientation:
            card.reveal()
            card.reset_rotation()
        elif card.rotation % 90 != 0:
            card.reset_rotation()
        sidebar.discard_pile.append(card)

    def import_pdf():
        """PDF import is not yet implemented. Use SDEextract.py from the command line."""
        print("[import_pdf] PDF import is not yet available in the app.")
        print("             Use SDEextract.py from the command line to extract cards from a PDF.")

    # ------------------------------------------------------------------ loop

    running = True
    while running:
        sw, sh = screen.get_size()
        mx, my = pygame.mouse.get_pos()

        rp_x = sw - sidebar.right_panel_width if (sidebar.show_right_panel or sidebar.show_options) else sw
        if sidebar.width < mx < rp_x:
            _hover_card = table.card_at_screen_pos(mx, my)
            if not _hover_card and not _arrow_placing:
                _hover_arrow, _hover_arrow_part = table.arrow_at_screen_pos(mx, my)
            else:
                _hover_arrow, _hover_arrow_part = None, None
        else:
            _hover_card = None
            _hover_arrow, _hover_arrow_part = None, None

        # Update resize cursor
        in_resize_zone = (
            abs(mx - sidebar.width) <= RESIZE_ZONE
            and not sidebar.show_deck_picker
            and not sidebar.show_browse
            and not sidebar.show_bg_picker
        )
        in_right_resize_zone = (
            sidebar.show_right_panel
            and not sidebar.show_options
            and abs(mx - rp_x) <= RESIZE_ZONE
            and not sidebar.show_deck_picker
            and not sidebar.show_browse
            and not sidebar.show_bg_picker
        )
        if _sidebar_resizing or in_resize_zone or _right_panel_resizing or in_right_resize_zone:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Confirm-delete dialog intercepts all input while visible
            elif _confirm_delete_card is not None:
                result = sidebar.handle_confirm_delete_event(event, sw, sh)
                if result == 'confirm':
                    if isinstance(_confirm_delete_card, list):
                        for card in _confirm_delete_card:
                            trash_card(card)
                        table.clear_cards()
                    else:
                        trash_card(_confirm_delete_card)
                        table.remove_card(_confirm_delete_card)
                    _confirm_delete_card = None
                    sidebar._confirm_delete_bulk_n = 0
                    sidebar.show_confirm_delete = False
                elif result == 'cancel':
                    _confirm_delete_card = None
                    sidebar._confirm_delete_bulk_n = 0
                    sidebar.show_confirm_delete = False
                continue

            elif _confirm_load_active_parents is not None:
                result = sidebar.handle_confirm_load_event(event, sw, sh)
                if result == 'confirm':
                    # Return all table cards to their source piles
                    for card in list(table.cards):
                        pile = next((d for d in decks if d.display_name == card.deck_name), None)
                        if pile is not None:
                            pile.return_card(card)
                    table.clear_cards()
                    table.selected_cards.clear()
                    # Return all discard cards to their source piles
                    for card in list(sidebar.discard_pile):
                        pile = next((d for d in decks if d.display_name == card.deck_name), None)
                        if pile is not None:
                            pile.return_card(card)
                    sidebar.discard_pile.clear()
                    sidebar._active_parents    = set(_confirm_load_active_parents)
                    sidebar._collapsed_parents = set(_confirm_load_collapsed_parents or [])
                    sidebar._selected_indices.clear()
                    sidebar._focused_idx   = -1
                    sidebar._scroll_offset = 0
                    _confirm_load_active_parents   = None
                    _confirm_load_collapsed_parents = None
                    sidebar.show_confirm_load    = False
                elif result == 'cancel':
                    _confirm_load_active_parents   = None
                    _confirm_load_collapsed_parents = None
                    sidebar.show_confirm_load    = False
                continue

            elif event.type == pygame.VIDEORESIZE:
                sidebar.resize(sh)

            elif event.type == pygame.KEYDOWN:
                # Help overlay intercepts keys (scroll or Escape/any-other closes)
                if sidebar.show_help:
                    sidebar.handle_event(event, decks, table, (sw, sh))
                    continue

                # Browse overlay intercepts all keys (Escape closes)
                if sidebar.show_browse:
                    if event.key == pygame.K_ESCAPE:
                        sidebar.show_browse = False
                    continue

                # BG picker intercepts all keys when hex field active or for Escape
                if sidebar.show_bg_picker:
                    sidebar.handle_event(event, decks, table, (sw, sh))
                    continue

                mods  = pygame.key.get_mods()
                ctrl  = mods & pygame.KMOD_CTRL
                shift = mods & pygame.KMOD_SHIFT

                # Helper: hover wins over selection; fall back to selection if no hover.
                def _targets():
                    return ([_hover_card] if _hover_card else
                            list(table.selected_cards))

                if event.key == pygame.K_ESCAPE:
                    if _arrow_placing:
                        _arrow_placing          = False
                        sidebar._arrow_placing  = False
                        _arrow_preview          = None
                    table.selected_cards.clear()
                    table.selected_arrows.clear()

                elif event.key == pygame.K_COMMA:
                    _arrow_placing         = not _arrow_placing
                    sidebar._arrow_placing = _arrow_placing
                    if not _arrow_placing:
                        _arrow_preview = None

                elif event.key == pygame.K_d and not ctrl:
                    draw_random()
                elif event.key == pygame.K_a and not ctrl:
                    draw_all()
                elif ctrl and event.key == pygame.K_a:
                    table.selected_cards  = set(table.cards)
                    table.selected_arrows = set(table.arrows)

                # ── Per-card transforms — apply to full selection or hover ──────
                elif event.key == pygame.K_f:
                    for c in _targets(): c.flip()
                elif event.key == pygame.K_t:
                    for c in _targets(): c.rotate_180()
                elif ctrl and event.key == pygame.K_r:
                    table.clear_cards()
                    table.selected_cards.clear()
                    sidebar.discard_pile.clear()
                    for deck in decks:
                        deck._trashed_paths.clear()
                        deck.shuffle()
                elif event.key == pygame.K_r and not ctrl:
                    for c in _targets(): c.rotate_cw()
                elif event.key == pygame.K_e:
                    for c in _targets(): c.rotate_ccw()
                elif event.key == pygame.K_y:
                    for c in _targets(): c.rotate_45cw()
                elif event.key == pygame.K_u:
                    for c in _targets(): c.reset_rotation()
                elif event.key == pygame.K_v:
                    for c in _targets(): c.rotation = random.choice([0, 90, 180, 270])

                # ── Duplicate card(s) (C) ─────────────────────────────────────
                elif event.key == pygame.K_c and not ctrl:
                    new_cards = []
                    for c in _targets():
                        dup = Card(c.front_path, c.deck_name, c.card_name)
                        dup.card_w      = c.card_w
                        dup.card_h      = c.card_h
                        dup.rotation    = c.rotation
                        dup.is_face_down = c.is_face_down
                        if c.is_face_down and c.back_path:
                            dup.back_path   = c.back_path
                            dup.image_path  = c.back_path
                            dup._load_image()
                        dup.x = c.x + 20
                        dup.y = c.y + 20
                        table.add_card(dup)
                        new_cards.append(dup)
                    if new_cards:
                        table.selected_cards = set(new_cards)

                # ── Return to deck (Z) ────────────────────────────────────────
                elif event.key == pygame.K_z and not ctrl:
                    for c in _targets():
                        pile = next((d for d in decks
                                     if d.display_name == c.deck_name), None)
                        if pile is not None:
                            pile.return_card(c)
                            table.remove_card(c)
                    _hover_card = None

                # ── Discard (X) ───────────────────────────────────────────────
                elif event.key == pygame.K_x and not ctrl:
                    for c in _targets():
                        table.remove_card(c)
                        discard_card(c)
                    table.selected_cards.clear()
                    _hover_card = None
                    # Arrows: just delete (no discard tracking)
                    for a in list(table.selected_arrows):
                        table.remove_arrow(a)
                    if _hover_arrow:
                        table.remove_arrow(_hover_arrow)
                        _hover_arrow = None

                # ── Delete (whole-table bulk) ─────────────────────────────────
                elif ctrl and event.key == pygame.K_DELETE:
                    if sidebar.delete_discards:
                        for card in list(table.cards):
                            discard_card(card)
                        table.clear_cards()
                        table.selected_cards.clear()
                    elif sidebar.delete_confirm:
                        _confirm_delete_card = list(table.cards)
                        sidebar._confirm_delete_bulk_n = len(_confirm_delete_card)
                        sidebar.show_confirm_delete = True
                    else:
                        for card in list(table.cards):
                            trash_card(card)
                        table.clear_cards()
                        table.selected_cards.clear()
                    # Always clear arrows on bulk delete
                    table.clear_arrows()
                    table.selected_arrows.clear()

                # ── Delete (selection or hover) ───────────────────────────────
                elif event.key == pygame.K_DELETE:
                    # Always delete hovered/selected arrows immediately
                    arrow_targets = (list(table.selected_arrows) or
                                     ([_hover_arrow] if _hover_arrow else []))
                    for a in arrow_targets:
                        table.remove_arrow(a)
                    if _hover_arrow and _hover_arrow in arrow_targets:
                        _hover_arrow = None
                    targets = _targets()
                    if targets:
                        if sidebar.delete_discards:
                            for c in targets:
                                table.remove_card(c)
                                discard_card(c)
                            table.selected_cards.clear()
                            _hover_card = None
                        elif sidebar.delete_confirm:
                            if len(targets) == 1:
                                _confirm_delete_card = targets[0]
                                sidebar._confirm_delete_bulk_n = 0
                            else:
                                _confirm_delete_card = targets
                                sidebar._confirm_delete_bulk_n = len(targets)
                            sidebar.show_confirm_delete = True
                            _hover_card = None
                        else:
                            for c in targets:
                                trash_card(c)
                                table.remove_card(c)
                            table.selected_cards.clear()
                            _hover_card = None

                # ── Z-order (hovered card or arrow) ──────────────────────────
                elif event.key == pygame.K_RIGHTBRACKET:
                    if _hover_arrow:
                        table.arrow_move_up(_hover_arrow)
                    elif _hover_card:
                        table.move_up(_hover_card)
                elif event.key == pygame.K_LEFTBRACKET:
                    if _hover_arrow:
                        table.arrow_move_down(_hover_arrow)
                    elif _hover_card:
                        table.move_down(_hover_card)
                elif event.key == pygame.K_HOME:
                    if _hover_arrow:
                        table.arrow_bring_to_top(_hover_arrow)
                    elif _hover_card:
                        table.bring_to_top(_hover_card)
                elif event.key == pygame.K_END:
                    if _hover_arrow:
                        table.arrow_send_to_bottom(_hover_arrow)
                    elif _hover_card:
                        table.send_to_bottom(_hover_card)

                elif event.unicode == "?":
                    sidebar.show_options = False
                    sidebar.show_help = not sidebar.show_help
                elif ctrl and not shift and event.key == pygame.K_s:
                    if sidebar.save_to_clipboard:
                        save_clipboard_png(table, sidebar)
                    else:
                        save_dialog_png(table, sidebar)
                elif ctrl and shift and event.key == pygame.K_s:
                    save_dialog_json(table)
                elif ctrl and event.key == pygame.K_o:
                    load_dialog_json(table)
                elif ctrl and event.key == pygame.K_z:
                    for card in list(table.cards):
                        pile = next((d for d in decks if d.display_name == card.deck_name), None)
                        if pile is not None:
                            pile.return_card(card)
                    table.clear_cards()
                    table.selected_cards.clear()
                elif ctrl and event.key == pygame.K_x:
                    for card in list(table.cards):
                        discard_card(card)
                    table.clear_cards()
                    table.selected_cards.clear()
                    table.clear_arrows()
                    table.selected_arrows.clear()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Help overlay: scroll buttons pass through; any real click closes
                if sidebar.show_help:
                    if event.button not in (4, 5):
                        sidebar.show_help = False
                    continue

                # Start sidebar resize drag (takes priority over sidebar buttons)
                if (event.button == 1
                        and abs(mx - sidebar.width) <= RESIZE_ZONE
                        and not sidebar.show_deck_picker
                        and not sidebar.show_browse
                        and not sidebar.show_options
                        and not sidebar.show_bg_picker):
                    _sidebar_resizing = True

                # Start right panel resize drag (blocked while options open)
                elif (event.button == 1
                        and sidebar.show_right_panel
                        and not sidebar.show_options
                        and abs(mx - rp_x) <= RESIZE_ZONE
                        and not sidebar.show_deck_picker
                        and not sidebar.show_browse
                        and not sidebar.show_bg_picker):
                    _right_panel_resizing = True

                # Options panel on right side (takes priority over right panel)
                elif sidebar.show_options and mx >= rp_x:
                    result = sidebar.handle_options_event(event, sw, sh, mx, my)
                    if result == "import_pdf":
                        import_pdf()
                    elif result == "card_base_size_changed":
                        settings.save(sidebar)
                        reload_decks()
                    elif result == "pick_startup_loadout":
                        path = pick_loadout_file_dialog()
                        if path:
                            sidebar.default_loadout_path = path
                            settings.save(sidebar)
                    elif result == "clear_startup_loadout":
                        sidebar.default_loadout_path = None
                        settings.save(sidebar)

                elif (mx <= sidebar.width or sidebar.show_deck_picker
                        or sidebar.show_browse or sidebar.show_bg_picker):
                    result = sidebar.handle_event(event, decks, table, (sw, sh))
                    if result == "open_deck_picker":
                        reload_decks()
                        sidebar.show_deck_picker = True
                    elif result == "draw_random":
                        draw_random()
                    elif result == "draw_all":
                        draw_all()
                    elif result == "reset":
                        table.clear_cards()
                        table.selected_cards.clear()
                        table.clear_arrows()
                        table.selected_arrows.clear()
                        sidebar.discard_pile.clear()
                        for deck in decks:
                            deck._trashed_paths.clear()
                            deck.shuffle()
                    elif result == "import_pdf":
                        import_pdf()
                    elif isinstance(result, tuple) and result[0] == "browse_pick":
                        _, front_path, deck = result
                        deck.mark_drawn(front_path)
                        card = Card(front_path, deck.display_name, _stem(front_path))
                        card.front_path   = front_path
                        card.back_path    = deck.card_back_for(front_path)
                        card.is_face_down = False
                        card.card_w = deck.card_w
                        card.card_h = deck.card_h
                        card._surface_cache.clear()
                        table.add_card(card, center_on_screen=True, screen_size=(sw, sh),
                                       tuck=sidebar.tuck_mode)
                    elif isinstance(result, tuple) and result[0] == "draw_single_pile":
                        draw_single_pile(result[1])
                    elif isinstance(result, tuple) and result[0] == "draw_matching_piles":
                        _, match_name = result
                        pool = [p for p in sidebar.active_piles if p.name == match_name]
                        if pool:
                            weights = [p.cards_remaining or len(p._all_fronts) for p in pool]
                            chosen  = random.choices(pool, weights=weights, k=1)[0]
                            card    = chosen.draw_random(face_down=sidebar.draw_face_down)
                            if sidebar.draw_random_rotation:
                                card.rotation = random.choice([0, 90, 180, 270])
                            table.add_card(card, center_on_screen=True,
                                           screen_size=(sw, sh), tuck=sidebar.tuck_mode)
                    elif isinstance(result, tuple) and result[0] == "discard_browse_pick":
                        _, idx = result
                        if 0 <= idx < len(sidebar.discard_pile):
                            card = sidebar.discard_pile.pop(idx)
                            card.is_face_down = False
                            table.add_card(card, center_on_screen=True, screen_size=(sw, sh),
                                           tuck=sidebar.tuck_mode)

                elif sidebar.show_right_panel and mx >= rp_x:
                    result = sidebar.handle_right_panel_event(event, mx, my, sw, sh)
                    if result == "toggle_arrow_placing":
                        _arrow_placing         = not _arrow_placing
                        sidebar._arrow_placing = _arrow_placing
                        if not _arrow_placing:
                            _arrow_preview = None
                    elif result == "save_spread":
                        save_spread_dialog(table, sidebar, decks)
                    elif result == "load_spread":
                        load_spread_dialog(table, sidebar, decks)
                    elif result == "save_loadout":
                        save_loadout_dialog(sidebar._active_parents,
                                            sidebar._collapsed_parents)
                    elif result == "load_loadout":
                        new_parents, new_collapsed = load_loadout_dialog()
                        if new_parents is not None:
                            if sidebar.reset_on_loadout:
                                # Destructive: warn if requested, then full reset + replace
                                if sidebar.load_confirm:
                                    _confirm_load_active_parents   = new_parents
                                    _confirm_load_collapsed_parents = new_collapsed
                                    sidebar.show_confirm_load       = True
                                else:
                                    for card in list(table.cards):
                                        pile = next((d for d in decks if d.display_name == card.deck_name), None)
                                        if pile is not None:
                                            pile.return_card(card)
                                    table.clear_cards()
                                    table.selected_cards.clear()
                                    for card in list(sidebar.discard_pile):
                                        pile = next((d for d in decks if d.display_name == card.deck_name), None)
                                        if pile is not None:
                                            pile.return_card(card)
                                    sidebar.discard_pile.clear()
                                    sidebar._active_parents    = set(new_parents)
                                    sidebar._collapsed_parents = set(new_collapsed or [])
                                    sidebar._selected_indices.clear()
                                    sidebar._focused_idx   = -1
                                    sidebar._scroll_offset = 0
                            else:
                                # Additive: only add new decks, never remove existing ones
                                sidebar._active_parents    |= set(new_parents)
                                sidebar._collapsed_parents |= set(new_collapsed or [])
                    elif result == "save_deck_sort":
                        collections = {}
                        for pile in sidebar.active_piles:
                            cp = pile.collection_path
                            if cp not in collections:
                                collections[cp] = []
                            collections[cp].append(_pile_key(pile))
                        for cp, pile_keys in collections.items():
                            save_collection_config(cp, {"piles": pile_keys})
                    elif result == "discard_drag_start" and sidebar.discard_pile:
                        card = sidebar.discard_pile.pop()
                        wx, wy = table.screen_to_world(mx, my)
                        card.x = wx - card.card_w / 2
                        card.y = wy - card.card_h / 2
                        table.add_card(card)
                        table.start_drag(card, mx, my)
                    elif result == "discard_take_top" and sidebar.discard_pile:
                        card = sidebar.discard_pile.pop()
                        card.is_face_down = False
                        table.add_card(card, center_on_screen=True, screen_size=(sw, sh))

                else:
                    if event.button == 1:
                        mods = pygame.key.get_mods()
                        ctrl = bool(mods & pygame.KMOD_CTRL)

                        if _arrow_placing:
                            # Start drawing a new arrow
                            wx, wy = table.screen_to_world(mx, my)
                            _arrow_preview = Arrow(
                                wx, wy, wx, wy,
                                color=sidebar.arrow_color,
                                style=sidebar.arrow_style,
                                both_ends=sidebar.arrow_both_ends,
                                weight=sidebar.arrow_weight,
                            )
                        else:
                            arrow, arrow_part = _hover_arrow, _hover_arrow_part
                            if arrow:
                                # Arm arrow drag/click (same deferred pattern as cards)
                                _pending_click_arrow      = arrow
                                _pending_click_arrow_part = arrow_part
                                _pending_click_ctrl       = ctrl
                                _pending_click_pos        = (mx, my)
                                table.start_arrow_drag(arrow, arrow_part, mx, my)
                            else:
                                card = table.card_at_screen_pos(mx, my)
                                if card:
                                    now = pygame.time.get_ticks()
                                    if (card is _last_click_card
                                            and now - _last_click_time < DBLCLICK_MS):
                                        # Double-click — flip card
                                        card.flip()
                                        _last_click_card = None
                                    else:
                                        # Single mousedown — arm drag, defer selection to mouseup
                                        _last_click_card = card
                                        _last_click_time = now
                                        _pending_click_card = card
                                        _pending_click_ctrl = ctrl
                                        _pending_click_pos  = (mx, my)
                                        table.start_drag(card, mx, my)
                                else:
                                    # Empty canvas — start box select
                                    _last_click_card = None
                                    _box_selecting = True
                                    _box_start_s   = (mx, my)
                                    _box_end_s     = (mx, my)
                    elif event.button in (2, 3):
                        if _arrow_placing:
                            # Right-click cancels placement
                            _arrow_placing         = False
                            sidebar._arrow_placing = False
                            _arrow_preview         = None
                        else:
                            _panning  = True
                            _pan_last = (mx, my)
                    elif event.button == 4:
                        table.zoom_at(mx, my, 1.1)
                    elif event.button == 5:
                        table.zoom_at(mx, my, 1 / 1.1)

            elif event.type == pygame.MOUSEWHEEL:
                if (mx <= sidebar.width or sidebar.show_deck_picker or sidebar.show_browse
                        or sidebar.show_help or sidebar.show_bg_picker
                        or mx >= rp_x):
                    sidebar.handle_event(event, decks, table, (sw, sh))
                else:
                    table.zoom_at(mx, my, 1.1 if event.y > 0 else 1 / 1.1)

            elif event.type == pygame.MOUSEBUTTONUP:
                # Always give sidebar a chance to complete a pile drag
                sidebar.handle_event(event, decks, table, (sw, sh))

                if event.button == 1:
                    _sidebar_resizing = False
                    _right_panel_resizing = False

                    # Finalise arrow placement
                    if _arrow_placing and _arrow_preview is not None:
                        dx = _arrow_preview.x2 - _arrow_preview.x1
                        dy = _arrow_preview.y2 - _arrow_preview.y1
                        if dx * dx + dy * dy > 100:  # minimum length (10 world units)
                            _mods = pygame.key.get_mods()
                            _ctrl = bool(_mods & pygame.KMOD_CTRL)
                            _tuck = sidebar.tuck_mode != _ctrl  # Ctrl toggles tuck
                            table.add_arrow(_arrow_preview, tuck=_tuck)
                        _arrow_preview         = None
                        _arrow_placing         = False
                        sidebar._arrow_placing = False

                    # Finalise arrow drag
                    elif table._drag_arrow:
                        table.end_arrow_drag()
                        if _pending_click_arrow is not None:
                            dist = max(abs(mx - _pending_click_pos[0]),
                                       abs(my - _pending_click_pos[1]))
                            if dist < CLICK_THRESHOLD:
                                if _pending_click_ctrl:
                                    if _pending_click_arrow in table.selected_arrows:
                                        table.selected_arrows.discard(_pending_click_arrow)
                                    else:
                                        table.selected_arrows.add(_pending_click_arrow)
                                else:
                                    table.selected_cards.clear()
                                    table.selected_arrows = {_pending_click_arrow}
                            _pending_click_arrow      = None
                            _pending_click_arrow_part = None

                    # Finalise box select (must happen before card drag check)
                    elif _box_selecting:
                        _box_selecting = False
                        box_dist = max(abs(mx - _box_start_s[0]), abs(my - _box_start_s[1]))
                        mods = pygame.key.get_mods()
                        if box_dist > 8:
                            # Real drag → select cards and arrows in rect
                            sx1 = min(_box_start_s[0], mx)
                            sy1 = min(_box_start_s[1], my)
                            sx2 = max(_box_start_s[0], mx)
                            sy2 = max(_box_start_s[1], my)
                            found        = table.cards_in_screen_rect(sx1, sy1, sx2, sy2)
                            found_arrows = table.arrows_in_screen_rect(sx1, sy1, sx2, sy2)
                            if mods & pygame.KMOD_CTRL:
                                table.selected_cards  |= found
                                table.selected_arrows |= found_arrows
                            else:
                                table.selected_cards  = found
                                table.selected_arrows = found_arrows
                        else:
                            # Small click on empty canvas → clear selection
                            if not (mods & pygame.KMOD_CTRL):
                                table.selected_cards.clear()
                                table.selected_arrows.clear()

                    elif table._drag_card:
                        mods     = pygame.key.get_mods()
                        ctrl     = bool(mods & pygame.KMOD_CTRL)
                        alt      = bool(mods & pygame.KMOD_ALT)
                        snap     = sidebar.snap_to_grid ^ alt
                        was_group = table._group_drag
                        dragged  = table.end_drag(mx, my,
                                                  snap_to_grid=snap,
                                                  snap_grid_size=sidebar.snap_grid_size)

                        # Decide: was this a click or a drag?
                        if _pending_click_card is not None:
                            dist = max(abs(mx - _pending_click_pos[0]),
                                       abs(my - _pending_click_pos[1]))
                            if dist < CLICK_THRESHOLD:
                                # Click — apply selection
                                if _pending_click_ctrl:
                                    if _pending_click_card in table.selected_cards:
                                        table.selected_cards.discard(_pending_click_card)
                                    else:
                                        table.selected_cards.add(_pending_click_card)
                                else:
                                    table.selected_cards  = {_pending_click_card}
                                    table.selected_arrows.clear()
                            # If dist >= threshold it was a real drag — don't touch selection
                            _pending_click_card = None

                        if dragged and sidebar.show_right_panel and not sidebar.show_options and mx >= rp_x:
                            # Dropped onto right panel — discard dragged card(s)
                            if was_group:
                                for c in list(table.selected_cards):
                                    table.remove_card(c)
                                    discard_card(c)
                                table.selected_cards.clear()
                            else:
                                table.remove_card(dragged)
                                discard_card(dragged)
                        elif dragged and (sidebar.tuck_mode ^ ctrl):
                            if was_group:
                                table.group_send_to_bottom(table.selected_cards)
                            else:
                                table.send_to_bottom(dragged)

                elif event.button in (2, 3):
                    _panning = False

            elif event.type == pygame.MOUSEMOTION:
                if _sidebar_resizing:
                    sidebar.width = max(SIDEBAR_MIN_W, min(SIDEBAR_MAX_W, mx))
                elif _right_panel_resizing:
                    sidebar.right_panel_width = max(RIGHT_PANEL_MIN_W, min(RIGHT_PANEL_MAX_W, sw - mx))
                else:
                    if _arrow_placing and _arrow_preview is not None:
                        wx, wy = table.screen_to_world(mx, my)
                        _arrow_preview.x2, _arrow_preview.y2 = wx, wy
                    if _box_selecting:
                        _box_end_s = (mx, my)
                    if table._drag_arrow:
                        table.update_arrow_drag(mx, my)
                    elif table._drag_card:
                        table.update_drag(mx, my)
                    if _panning:
                        dx = mx - _pan_last[0]
                        dy = my - _pan_last[1]
                        table.pan(dx, dy)
                        _pan_last = (mx, my)
                    sidebar.handle_motion(mx, my, sh)
                    if mx <= sidebar.width:
                        for btn in sidebar._buttons.values():
                            btn.update(mx, my)

        # ---------------------------------------------------------------- draw

        right_w     = sidebar.right_panel_width if (sidebar.show_right_panel or sidebar.show_options) else 0
        canvas_rect = pygame.Rect(sidebar.width, 0, sw - sidebar.width - right_w, sh)
        screen.fill(sidebar.bg_color)
        if sidebar.bg_mode == "image" and sidebar.bg_image_path:
            cache_key = (sidebar.bg_image_path, canvas_rect.width, canvas_rect.height,
                         sidebar.bg_image_fit)
            if sidebar._bg_cache_key != cache_key:
                try:
                    from PIL import Image as _PILImage
                    src = _PILImage.open(sidebar.bg_image_path).convert("RGB")
                    cw, ch = canvas_rect.width, canvas_rect.height
                    if sidebar.bg_image_fit == "tile":
                        tw, th = src.size
                        tiled = _PILImage.new("RGB", (cw, ch))
                        for ty in range(0, ch, th):
                            for tx in range(0, cw, tw):
                                tiled.paste(src, (tx, ty))
                        surf = pygame.image.fromstring(tiled.tobytes(), tiled.size, "RGB")
                    else:  # "center"
                        scale = min(cw / src.width, ch / src.height)
                        nw = int(src.width * scale)
                        nh = int(src.height * scale)
                        resized = src.resize((nw, nh), _PILImage.LANCZOS)
                        canvas_img = _PILImage.new("RGB", (cw, ch), sidebar.bg_color)
                        canvas_img.paste(resized, ((cw - nw) // 2, (ch - nh) // 2))
                        surf = pygame.image.fromstring(canvas_img.tobytes(),
                                                       canvas_img.size, "RGB")
                    sidebar._bg_surface   = surf.convert()
                    sidebar._bg_cache_key = cache_key
                except Exception:
                    sidebar.bg_image_path = None
                    sidebar.bg_mode       = "color"
            if sidebar._bg_surface:
                screen.blit(sidebar._bg_surface, (canvas_rect.x, canvas_rect.y))

        if sidebar.show_grid:
            _draw_grid(screen, table, canvas_rect)

        screen.set_clip(canvas_rect)
        table.draw(screen)

        # Arrow highlights (halo drawn behind arrows)
        for arrow in table.selected_arrows:
            if arrow is not table._drag_arrow:
                table.draw_arrow_highlight(screen, arrow, color=(80, 140, 220))
        if _hover_arrow and not table._drag_arrow:
            hov_col = (140, 190, 255) if _hover_arrow in table.selected_arrows else (255, 220, 0)
            table.draw_arrow_highlight(screen, _hover_arrow, color=hov_col)
        if table._drag_arrow:
            table.draw_arrow_highlight(screen, table._drag_arrow, color=(120, 220, 255))

        # Preview arrow during placement
        if _arrow_placing and _arrow_preview is not None:
            x1s, y1s = table.world_to_screen(_arrow_preview.x1, _arrow_preview.y1)
            x2s, y2s = table.world_to_screen(_arrow_preview.x2, _arrow_preview.y2)
            draw_arrow(screen, _arrow_preview, x1s, y1s, x2s, y2s, table.zoom)

        # Face-down badge overlay
        _draw_facedown_badges(screen, table, sidebar.width)

        # Card highlights — priority: drag (cyan) > hover (yellow) > selected (blue)
        for card in table.selected_cards:
            if card is not table._drag_card and card is not _hover_card:
                table.draw_highlight(screen, card, color=(80, 140, 220))
        if _hover_card and not table._drag_card:
            hover_color = (140, 190, 255) if _hover_card in table.selected_cards else (255, 220, 0)
            table.draw_highlight(screen, _hover_card, color=hover_color)
        if table._drag_card:
            table.draw_highlight(screen, table._drag_card, color=(120, 220, 255))

        screen.set_clip(None)

        # Box select overlay (drawn above canvas, under UI)
        if _box_selecting:
            bx1 = min(_box_start_s[0], mx)
            by1 = min(_box_start_s[1], my)
            bw  = abs(mx - _box_start_s[0])
            bh  = abs(my - _box_start_s[1])
            if bw > 4 and bh > 4:
                _box_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
                _box_surf.fill((80, 140, 220, 40))
                screen.blit(_box_surf, (bx1, by1))
                pygame.draw.rect(screen, (80, 140, 220), (bx1, by1, bw, bh), 1)

        sidebar.draw(screen)
        _draw_status(screen, table, sidebar, sw, sh)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


def _draw_facedown_badges(screen, table, sidebar_width):
    pass


def _draw_grid(screen, table, clip_rect):
    grid_spacing = 50
    dot_color    = (50, 50, 68)
    import math
    left, top     = table.screen_to_world(clip_rect.left, clip_rect.top)
    right, bottom = table.screen_to_world(clip_rect.right, clip_rect.bottom)
    start_x = math.floor(left  / grid_spacing) * grid_spacing
    start_y = math.floor(top   / grid_spacing) * grid_spacing
    gx = start_x
    while gx < right:
        gy = start_y
        while gy < bottom:
            sx, sy = table.world_to_screen(gx, gy)
            if clip_rect.collidepoint(sx, sy):
                screen.set_at((int(sx), int(sy)), dot_color)
            gy += grid_spacing
        gx += grid_spacing


def _draw_status(screen, table, sidebar, sw, sh):
    try:
        font     = pygame.font.SysFont("segoeui", 12)
        zoom_pct = int(table.zoom * 100)
        n_cards  = len(table.cards)
        piles    = sidebar.active_piles
        sel      = len(sidebar.selected_decks)
        n_active = len(piles)
        pile_info = f"Active piles: {n_active}  ({sel} selected)"
        status = f"  Zoom: {zoom_pct}%   On table: {n_cards}   {pile_info}   | ? for help"
        surf   = font.render(status, True, (100, 100, 130))
        screen.blit(surf, (sidebar.width + 8, sh - 18))
    except Exception:
        pass


if __name__ == "__main__":
    main()
