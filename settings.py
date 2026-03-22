"""
Persistent settings for the Options panel and background.

Stored in settings.json in the same directory as this file.
If the file doesn't exist it is created with the current (default) values.
Any unknown keys in the file are ignored; any keys missing from the file
fall back to the sidebar's hardcoded defaults.
"""

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# All sidebar attributes that are persisted
_KEYS = (
    "show_pile_top",
    "draw_face_down",
    "draw_random_rotation",
    "tuck_mode",
    "snap_to_grid",
    "snap_grid_size",
    "card_base_w",
    "card_base_h",
    "save_with_bg",
    "bg_mode",
    "bg_color",
    "bg_image_path",
    "bg_image_fit",
    "delete_confirm",
    "delete_discards",
    "keep_discard_orientation",
    "drawn_card_dim",
    "browse_shuffle_order",
    "show_grid",
    "load_confirm",
    "reset_on_loadout",
    "default_loadout_path",
    "arrow_color",
    "arrow_style",
    "arrow_both_ends",
    "default_arrow_weight",
    "save_to_clipboard",
)

# Keys whose values must be tuples (JSON round-trips them as lists)
_TUPLE_KEYS = {"bg_color", "arrow_color"}


def load(sidebar):
    """Read settings.json into sidebar.  Creates the file if it doesn't exist."""
    if os.path.exists(_PATH):
        try:
            with open(_PATH) as f:
                data = json.load(f)
            for key in _KEYS:
                if key in data:
                    val = data[key]
                    if key in _TUPLE_KEYS and isinstance(val, list):
                        val = tuple(val)
                    setattr(sidebar, key, val)
        except Exception as e:
            print(f"[settings] Could not load {_PATH}: {e}")
    # Session weight starts at the default.
    sidebar.arrow_weight = sidebar.default_arrow_weight
    # Always write back so the file is created (or updated with any new keys).
    save(sidebar)


def save(sidebar):
    """Write current option state to settings.json."""
    data = {key: getattr(sidebar, key) for key in _KEYS}
    try:
        with open(_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[settings] Could not save {_PATH}: {e}")
