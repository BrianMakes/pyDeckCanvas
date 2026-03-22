import json
import math
import os
import pygame
from PIL import Image, ImageDraw, ImageChops
from arrow import draw_arrow_pil
from card import Card


def _rotated_card_size(card):
    """Return (w, h) of a card's dimensions after rotation with expand=True."""
    if card.rotation % 90 == 0:
        if card.rotation % 180 == 0:
            return card.card_w, card.card_h
        else:
            return card.card_h, card.card_w   # 90/270: dimensions swap
    rad = math.radians(card.rotation)
    w = math.ceil(card.card_w * abs(math.cos(rad)) + card.card_h * abs(math.sin(rad)))
    h = math.ceil(card.card_w * abs(math.sin(rad)) + card.card_h * abs(math.cos(rad)))
    return w, h


def _rounded_card(card_img, radius):
    """Return card_img (RGBA) with rounded corners applied to its alpha channel."""
    mask = Image.new("L", card_img.size, 0)
    draw = ImageDraw.Draw(mask)
    w, h = card_img.size
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    existing_alpha = card_img.split()[3]
    combined = ImageChops.multiply(existing_alpha, mask)
    card_img.putalpha(combined)
    return card_img


def save_layout_json(table, filepath):
    """Save the full table state to a JSON file."""
    data = table.to_dict()
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Layout saved: {filepath}")


def load_layout_json(table, filepath):
    """Load table state from a JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    table.from_dict(data)
    print(f"Layout loaded: {filepath}")


def _build_canvas(table, bg_color=(34, 34, 48),
                  bg_image_path=None, bg_image_fit="tile"):
    """Render table objects into a PIL Image and return it, or None if nothing to render."""
    if not table.objects:
        return None

    margin = 40
    xs, ys, max_x_vals, max_y_vals = [], [], [], []
    for obj in table.objects:
        if isinstance(obj, Card):
            xs.append(obj.x)
            ys.append(obj.y)
            max_x_vals.append(obj.x + _rotated_card_size(obj)[0])
            max_y_vals.append(obj.y + _rotated_card_size(obj)[1])
        else:
            xs  += [obj.x1, obj.x2]
            ys  += [obj.y1, obj.y2]
            max_x_vals += [obj.x1, obj.x2]
            max_y_vals += [obj.y1, obj.y2]
    min_x = min(xs) - margin
    min_y = min(ys) - margin
    out_w = int(max(max_x_vals) + margin - min_x)
    out_h = int(max(max_y_vals) + margin - min_y)

    canvas = Image.new("RGB", (out_w, out_h), bg_color)
    if bg_image_path:
        try:
            bg = Image.open(bg_image_path).convert("RGB")
            if bg_image_fit == "tile":
                tw, th = bg.size
                for ty in range(0, out_h, th):
                    for tx in range(0, out_w, tw):
                        canvas.paste(bg, (tx, ty))
            else:
                scale = min(out_w / bg.width, out_h / bg.height)
                nw, nh = int(bg.width * scale), int(bg.height * scale)
                canvas.paste(bg.resize((nw, nh), Image.LANCZOS),
                             ((out_w - nw) // 2, (out_h - nh) // 2))
        except Exception as e:
            print(f"Background image skipped: {e}")

    canvas = canvas.convert("RGBA")
    arrow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    arrow_draw  = ImageDraw.Draw(arrow_layer)
    has_arrows  = False
    for obj in table.objects:
        if isinstance(obj, Card):
            if has_arrows:
                canvas = Image.alpha_composite(canvas, arrow_layer)
                arrow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                arrow_draw  = ImageDraw.Draw(arrow_layer)
                has_arrows  = False
            corner_radius = min(obj.card_w, obj.card_h) // 20
            card_img = Image.open(obj.image_path).convert("RGBA")
            card_img = card_img.resize((obj.card_w, obj.card_h), Image.LANCZOS)
            if obj.rotation:
                card_img = card_img.rotate(-obj.rotation, expand=True)
            card_img = _rounded_card(card_img, corner_radius)
            canvas.paste(card_img, (int(obj.x - min_x), int(obj.y - min_y)), card_img)
        else:
            draw_arrow_pil(arrow_draw, obj,
                           int(obj.x1 - min_x), int(obj.y1 - min_y),
                           int(obj.x2 - min_x), int(obj.y2 - min_y))
            has_arrows = True
    if has_arrows:
        canvas = Image.alpha_composite(canvas, arrow_layer)
    return canvas


def export_png(table, filepath, bg_color=(34, 34, 48),
               bg_image_path=None, bg_image_fit="tile"):
    """Export the current layout as a PNG file."""
    canvas = _build_canvas(table, bg_color, bg_image_path, bg_image_fit)
    if canvas is None:
        print("No cards or arrows to export.")
        return
    canvas.save(filepath, "PNG")
    print(f"Exported PNG: {filepath}")


def export_clipboard(table, bg_color=(34, 34, 48),
                     bg_image_path=None, bg_image_fit="tile"):
    """Copy the current layout as a PNG image to the system clipboard."""
    import sys
    canvas = _build_canvas(table, bg_color, bg_image_path, bg_image_fit)
    if canvas is None:
        print("No cards or arrows to export.")
        return
    if sys.platform == "win32":
        import ctypes, io as _io
        buf = _io.BytesIO()
        canvas.convert("RGB").save(buf, "BMP")
        data = buf.getvalue()[14:]  # strip 14-byte BMP file header; keep DIB header + pixels

        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        # Set return types explicitly — default c_int truncates 64-bit pointers on x64
        k32.GlobalAlloc.restype  = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype   = ctypes.c_void_p
        k32.GlobalLock.argtypes  = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

        GMEM_MOVEABLE = 0x0002
        hMem = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not hMem:
            print("Clipboard error: GlobalAlloc failed.")
            return
        pMem = k32.GlobalLock(hMem)
        if not pMem:
            print("Clipboard error: GlobalLock failed.")
            return
        ctypes.memmove(pMem, data, len(data))
        k32.GlobalUnlock(hMem)
        u32.OpenClipboard(0)
        u32.EmptyClipboard()
        u32.SetClipboardData(8, hMem)  # CF_DIB = 8
        u32.CloseClipboard()
        print("Copied to clipboard.")
    else:
        print("Clipboard export is only supported on Windows.")


def _win_dialog(title, initialdir, ext, save):
    """
    Native Windows file dialog via COMDLG32 — no tkinter, fully SDL-compatible.
    Uses the pygame window as the dialog owner so it stays on top.
    """
    import ctypes
    import sys

    if sys.platform != "win32":
        return None  # signal caller to use tkinter fallback

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize",       ctypes.c_uint32),
            ("hwndOwner",         ctypes.c_void_p),
            ("hInstance",         ctypes.c_void_p),
            ("lpstrFilter",       ctypes.c_void_p),
            ("lpstrCustomFilter", ctypes.c_void_p),
            ("nMaxCustomFilter",  ctypes.c_uint32),
            ("nFilterIndex",      ctypes.c_uint32),
            ("lpstrFile",         ctypes.c_void_p),
            ("nMaxFile",          ctypes.c_uint32),
            ("lpstrFileTitle",    ctypes.c_void_p),
            ("nMaxFileTitle",     ctypes.c_uint32),
            ("lpstrInitialDir",   ctypes.c_void_p),
            ("lpstrTitle",        ctypes.c_void_p),
            ("Flags",             ctypes.c_uint32),
            ("nFileOffset",       ctypes.c_uint16),
            ("nFileExtension",    ctypes.c_uint16),
            ("lpstrDefExt",       ctypes.c_void_p),
            ("lCustData",         ctypes.c_void_p),
            ("lpfnHook",          ctypes.c_void_p),
            ("lpTemplateName",    ctypes.c_void_p),
        ]

    # All string buffers kept alive for the duration of the call
    filter_str  = f"{ext.upper()} files\0*.{ext}\0All files\0*.*\0\0"
    filter_buf  = ctypes.create_unicode_buffer(filter_str, len(filter_str))
    title_buf   = ctypes.create_unicode_buffer(title)
    initdir_buf = ctypes.create_unicode_buffer(initialdir or "")
    defext_buf  = ctypes.create_unicode_buffer(ext)
    file_buf    = ctypes.create_unicode_buffer(32768)

    hwnd = 0
    try:
        hwnd = pygame.display.get_wm_info().get("window", 0)
    except Exception:
        pass

    OFN_OVERWRITEPROMPT = 0x00000002
    OFN_PATHMUSTEXIST   = 0x00000800
    OFN_FILEMUSTEXIST   = 0x00001000
    OFN_NOCHANGEDIR     = 0x00000008
    OFN_EXPLORER        = 0x00080000

    ofn = OPENFILENAMEW()
    ofn.lStructSize    = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner      = hwnd
    ofn.lpstrFilter    = ctypes.addressof(filter_buf)
    ofn.nFilterIndex   = 1
    ofn.lpstrFile      = ctypes.addressof(file_buf)
    ofn.nMaxFile       = 32768
    ofn.lpstrInitialDir = ctypes.addressof(initdir_buf)
    ofn.lpstrTitle     = ctypes.addressof(title_buf)
    ofn.lpstrDefExt    = ctypes.addressof(defext_buf)

    comdlg32 = ctypes.windll.comdlg32
    if save:
        ofn.Flags = OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR | OFN_EXPLORER
        ok = comdlg32.GetSaveFileNameW(ctypes.byref(ofn))
    else:
        ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER
        ok = comdlg32.GetOpenFileNameW(ctypes.byref(ofn))

    return file_buf.value if ok else None


def _tk_dialog(filetypes="json", initialdir=None, save=False, title=None):
    """Tkinter file dialog fallback for non-Windows."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if save:
            path = filedialog.asksaveasfilename(
                title=title or "Save",
                initialdir=initialdir,
                defaultextension=f".{filetypes}",
                filetypes=[(f"{filetypes.upper()} files", f"*.{filetypes}"),
                           ("All files", "*.*")]
            )
        else:
            path = filedialog.askopenfilename(
                title=title or "Open",
                initialdir=initialdir,
                filetypes=[(f"{filetypes.upper()} files", f"*.{filetypes}"),
                           ("All files", "*.*")]
            )
        root.destroy()
        return path if path else None
    except Exception as e:
        print(f"File dialog error: {e}")
        return None


def _file_dialog(title, initialdir, ext, save):
    """Platform-aware file dialog: native COMDLG32 on Windows, tkinter elsewhere."""
    import sys
    if sys.platform == "win32":
        return _win_dialog(title, initialdir, ext, save)
    return _tk_dialog(ext, initialdir, save=save, title=title)


def open_file_dialog(filetypes="json", initialdir=None):
    """Returns filepath string or None."""
    save = (filetypes != "json")
    title = "Save Layout" if save else "Load Layout"
    return _file_dialog(title, initialdir, filetypes, save)


def save_dialog_json(table):
    path = open_file_dialog("json")
    if path:
        save_layout_json(table, path)


def load_dialog_json(table):
    path = open_file_dialog("json")
    if path and os.path.exists(path):
        load_layout_json(table, path)


def _spreads_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "spreads")


def _loadouts_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "loadouts")


def save_spread_dialog(table, sidebar, decks):
    """Save full spread state to the spreads/ folder.

    Includes table layout, active decks, discard pile, and per-deck draw state.
    """
    d = _spreads_dir()
    os.makedirs(d, exist_ok=True)
    try:
        path = _file_dialog("Save Spread", d, "json", save=True)
        if path:
            data = {
                "spread_version": 2,
                "table": table.to_dict(),
                "active_parents": sorted(sidebar._active_parents),
                "discard_pile": [c.to_dict() for c in sidebar.discard_pile],
                "deck_state": [
                    {
                        "display_name":  dk.display_name,
                        "drawn_paths":   list(dk._drawn_paths),
                        "trashed_paths": list(dk._trashed_paths),
                        "draw_pile":     list(dk._draw_pile),
                    }
                    for dk in decks
                ],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Spread saved: {path}")
    except Exception as e:
        print(f"File dialog error: {e}")


def load_spread_dialog(table, sidebar, decks):
    """Load full spread state from the spreads/ folder."""
    d = _spreads_dir()
    os.makedirs(d, exist_ok=True)
    try:
        path = _file_dialog("Load Spread", d, "json", save=False)
        if not (path and os.path.exists(path)):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("spread_version", 1)
        if version >= 2:
            table.from_dict(data["table"])
            sidebar._active_parents    = set(data.get("active_parents", []))
            sidebar._selected_indices.clear()
            sidebar._focused_idx       = -1
            sidebar._scroll_offset     = 0
            from card import Card
            sidebar.discard_pile = [Card.from_dict(c) for c in data.get("discard_pile", [])]
            name_to_deck = {dk.display_name: dk for dk in decks}
            # Patch card dimensions from deck config (not saved in spread)
            for card in table.cards + sidebar.discard_pile:
                pile = name_to_deck.get(card.deck_name)
                if pile:
                    card.card_w = pile.card_w
                    card.card_h = pile.card_h
                    card._surface_cache.clear()
            for ds in data.get("deck_state", []):
                deck = name_to_deck.get(ds["display_name"])
                if deck:
                    all_set = set(deck._all_fronts)
                    deck._drawn_paths   = set(ds.get("drawn_paths",   [])) & all_set
                    deck._trashed_paths = set(ds.get("trashed_paths", [])) & all_set
                    saved_pile = ds.get("draw_pile", [])
                    deck._draw_pile = [p for p in saved_pile
                                       if p in all_set
                                       and p not in deck._drawn_paths
                                       and p not in deck._trashed_paths]
        else:
            table.from_dict(data)
        print(f"Spread loaded: {path}")
    except Exception as e:
        print(f"File dialog error: {e}")


def save_loadout_dialog(active_parents, collapsed_parents=None):
    """Save active_parents (and optionally collapsed_parents) as a loadout JSON."""
    d = _loadouts_dir()
    os.makedirs(d, exist_ok=True)
    try:
        path = _file_dialog("Save Loadout", d, "json", save=True)
        if path:
            data = {"active_parents": sorted(active_parents)}
            if collapsed_parents is not None:
                data["collapsed_parents"] = sorted(collapsed_parents)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Loadout saved: {path}")
    except Exception as e:
        print(f"File dialog error: {e}")


def pick_loadout_file_dialog():
    """Open a file picker in loadouts/ and return the selected path (or None)."""
    d = _loadouts_dir()
    os.makedirs(d, exist_ok=True)
    try:
        path = _file_dialog("Select Startup Loadout", d, "json", save=False)
        return path if path else None
    except Exception as e:
        print(f"File dialog error: {e}")
    return None


def load_loadout_dialog():
    """Open a loadout JSON.
    Returns (active_parents, collapsed_parents) tuple, or (None, None) on cancel/error.
    collapsed_parents defaults to [] for loadouts saved before this feature existed.
    """
    d = _loadouts_dir()
    os.makedirs(d, exist_ok=True)
    try:
        path = _file_dialog("Load Loadout", d, "json", save=False)
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("active_parents", []), data.get("collapsed_parents", [])
    except Exception as e:
        print(f"File dialog error: {e}")
    return None, None


def _sidebar_bg_args(sidebar):
    bg_color      = sidebar.bg_color if sidebar else (34, 34, 48)
    bg_image_path = None
    bg_image_fit  = "tile"
    if sidebar and sidebar.save_with_bg and sidebar.bg_mode == "image":
        bg_image_path = sidebar.bg_image_path
        bg_image_fit  = sidebar.bg_image_fit
    return bg_color, bg_image_path, bg_image_fit


def save_dialog_png(table, sidebar=None):
    spreads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spreads")
    os.makedirs(spreads_dir, exist_ok=True)
    path = open_file_dialog("png", initialdir=spreads_dir)
    if path:
        bg_color, bg_image_path, bg_image_fit = _sidebar_bg_args(sidebar)
        export_png(table, path, bg_color=bg_color,
                   bg_image_path=bg_image_path, bg_image_fit=bg_image_fit)


def save_clipboard_png(table, sidebar=None):
    """Copy the layout PNG directly to the clipboard (no file dialog)."""
    bg_color, bg_image_path, bg_image_fit = _sidebar_bg_args(sidebar)
    export_clipboard(table, bg_color=bg_color,
                     bg_image_path=bg_image_path, bg_image_fit=bg_image_fit)
