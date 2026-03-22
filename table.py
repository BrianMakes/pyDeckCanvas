import math
import pygame
from card import Card
from arrow import Arrow, draw_arrow, point_to_segment_dist


# Base size cards are stored/rendered at
CARD_BASE_SIZE = 500

# Cache for rounded-corner masks keyed by (w, h, radius)
_corner_mask_cache = {}


def _get_corner_mask(w, h, radius):
    """Return a cached SRCALPHA mask surface with rounded corners."""
    key = (w, h, radius)
    if key not in _corner_mask_cache:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 0))
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h),
                         border_radius=radius)
        _corner_mask_cache[key] = mask
    return _corner_mask_cache[key]


class Table:
    """
    Manages the layout canvas: cards and arrows in a unified z-order list.
    World coordinates are independent of screen zoom/pan.
    """

    def __init__(self):
        self.objects = []        # unified z-order: index 0 = bottom, -1 = top
        self.zoom = 0.3
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_card = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self.selected_cards = set()
        self._group_drag_offsets = {}
        self._group_drag_arrow_offsets = {}
        self._group_drag = False

        self.selected_arrows = set()
        self._drag_arrow       = None
        self._drag_arrow_mode  = None    # "body" | "start" | "end"
        self._drag_arrow_ox    = 0.0
        self._drag_arrow_oy    = 0.0
        self._drag_arrow_dx    = 0.0
        self._drag_arrow_dy    = 0.0

    # --- Filtered views (read-only) ---

    @property
    def cards(self):
        return [o for o in self.objects if isinstance(o, Card)]

    @property
    def arrows(self):
        return [o for o in self.objects if isinstance(o, Arrow)]

    # --- Coordinate helpers ---

    def screen_to_world(self, sx, sy):
        wx = (sx - self.pan_x) / self.zoom
        wy = (sy - self.pan_y) / self.zoom
        return wx, wy

    def world_to_screen(self, wx, wy):
        sx = wx * self.zoom + self.pan_x
        sy = wy * self.zoom + self.pan_y
        return sx, sy

    @property
    def card_display_size(self):
        return CARD_BASE_SIZE

    # --- Card management ---

    def add_card(self, card, center_on_screen=None, screen_size=None, tuck=False):
        """Add card to z-stack, optionally centering on screen.
        tuck=True places the card at the bottom of the z-order."""
        if center_on_screen and screen_size:
            sw, sh = screen_size
            wx, wy = self.screen_to_world(sw / 2, sh / 2)
            card.x = wx - card.card_w / 2
            card.y = wy - card.card_h / 2
        if tuck:
            self.objects.insert(0, card)
        else:
            self.objects.append(card)

    def remove_card(self, card):
        if card in self.objects:
            self.objects.remove(card)
        self.selected_cards.discard(card)

    def clear_cards(self):
        """Remove all cards from the objects list."""
        self.objects = [o for o in self.objects if not isinstance(o, Card)]
        self.selected_cards.clear()

    def bring_to_top(self, card):
        if card in self.objects:
            self.objects.remove(card)
            self.objects.append(card)

    def send_to_bottom(self, card):
        if card in self.objects:
            self.objects.remove(card)
            self.objects.insert(0, card)

    def move_up(self, card):
        idx = self.objects.index(card)
        if idx < len(self.objects) - 1:
            self.objects[idx], self.objects[idx + 1] = self.objects[idx + 1], self.objects[idx]

    def move_down(self, card):
        idx = self.objects.index(card)
        if idx > 0:
            self.objects[idx], self.objects[idx - 1] = self.objects[idx - 1], self.objects[idx]

    def card_at_screen_pos(self, sx, sy):
        """Return topmost card under screen position, or None."""
        wx, wy = self.screen_to_world(sx, sy)
        for obj in reversed(self.objects):
            if not isinstance(obj, Card):
                continue
            surf = obj.get_surface()
            sw, sh = surf.get_size()
            if pygame.Rect(obj.x, obj.y, sw, sh).collidepoint(wx, wy):
                return obj
        return None

    # --- Drag ---

    def start_drag(self, card, sx, sy):
        self._drag_card = card
        wx, wy = self.screen_to_world(sx, sy)
        self._drag_offset_x = wx - card.x
        self._drag_offset_y = wy - card.y

        if card in self.selected_cards and len(self.selected_cards) > 1:
            # Group drag: bring all selected cards to top preserving relative z-order
            in_order = [o for o in self.objects if o in self.selected_cards]
            for c in in_order:
                self.objects.remove(c)
            self.objects.extend(in_order)
            self._group_drag_offsets = {
                c: (c.x - card.x, c.y - card.y) for c in self.selected_cards
            }
            self._group_drag = True
            self._group_drag_arrow_offsets = {
                a: (a.x1 - card.x, a.y1 - card.y,
                    a.x2 - card.x, a.y2 - card.y)
                for a in self.selected_arrows
            }
        else:
            self._group_drag_offsets = {}
            self._group_drag_arrow_offsets = {}
            self._group_drag = False
            self.bring_to_top(card)

    def update_drag(self, sx, sy):
        if self._drag_card:
            wx, wy = self.screen_to_world(sx, sy)
            self._drag_card.x = wx - self._drag_offset_x
            self._drag_card.y = wy - self._drag_offset_y
            for c, (ox, oy) in self._group_drag_offsets.items():
                if c is not self._drag_card:
                    c.x = self._drag_card.x + ox
                    c.y = self._drag_card.y + oy
            for a, (ox1, oy1, ox2, oy2) in self._group_drag_arrow_offsets.items():
                a.x1 = self._drag_card.x + ox1
                a.y1 = self._drag_card.y + oy1
                a.x2 = self._drag_card.x + ox2
                a.y2 = self._drag_card.y + oy2

    def end_drag(self, sx, sy, snap_to_grid=False, snap_grid_size=125):
        if not self._drag_card:
            return None
        card = self._drag_card
        self._drag_card = None

        if snap_to_grid and snap_grid_size > 0:
            g = snap_grid_size
            old_x, old_y = card.x, card.y
            card.x = round(card.x / g) * g
            card.y = round(card.y / g) * g
            if self._group_drag_offsets:
                dx = card.x - old_x
                dy = card.y - old_y
                for c in self._group_drag_offsets:
                    if c is not card:
                        c.x += dx
                        c.y += dy

        self._group_drag_offsets = {}
        self._group_drag_arrow_offsets = {}
        return card

    # --- Arrow management ---

    def add_arrow(self, arrow, tuck=False):
        """Add arrow to z-stack. tuck=True places it at the bottom."""
        if tuck:
            self.objects.insert(0, arrow)
        else:
            self.objects.append(arrow)

    def remove_arrow(self, arrow):
        if arrow in self.objects:
            self.objects.remove(arrow)
        self.selected_arrows.discard(arrow)

    def clear_arrows(self):
        """Remove all arrows from the objects list."""
        self.objects = [o for o in self.objects if not isinstance(o, Arrow)]
        self.selected_arrows.clear()

    def arrow_bring_to_top(self, arrow):
        if arrow in self.objects:
            self.objects.remove(arrow)
            self.objects.append(arrow)

    def arrow_send_to_bottom(self, arrow):
        if arrow in self.objects:
            self.objects.remove(arrow)
            self.objects.insert(0, arrow)

    def arrow_move_up(self, arrow):
        idx = self.objects.index(arrow)
        if idx < len(self.objects) - 1:
            self.objects[idx], self.objects[idx + 1] = self.objects[idx + 1], self.objects[idx]

    def arrow_move_down(self, arrow):
        idx = self.objects.index(arrow)
        if idx > 0:
            self.objects[idx], self.objects[idx - 1] = self.objects[idx - 1], self.objects[idx]

    def arrow_at_screen_pos(self, sx, sy):
        """Return (arrow, part) where part is 'start'|'end'|'body', or (None, None)."""
        ENDPOINT_R = 10
        BODY_DIST  = 8
        for obj in reversed(self.objects):
            if not isinstance(obj, Arrow):
                continue
            x1s, y1s = self.world_to_screen(obj.x1, obj.y1)
            x2s, y2s = self.world_to_screen(obj.x2, obj.y2)
            if math.sqrt((sx - x2s) ** 2 + (sy - y2s) ** 2) <= ENDPOINT_R:
                return obj, "end"
            if math.sqrt((sx - x1s) ** 2 + (sy - y1s) ** 2) <= ENDPOINT_R:
                return obj, "start"
            if point_to_segment_dist(sx, sy, x1s, y1s, x2s, y2s) <= BODY_DIST:
                return obj, "body"
        return None, None

    def start_arrow_drag(self, arrow, mode, sx, sy):
        self._drag_arrow      = arrow
        self._drag_arrow_mode = mode
        wx, wy = self.screen_to_world(sx, sy)
        if mode == "body":
            mx = (arrow.x1 + arrow.x2) / 2
            my = (arrow.y1 + arrow.y2) / 2
            self._drag_arrow_ox = wx - mx
            self._drag_arrow_oy = wy - my
            self._drag_arrow_dx = arrow.x2 - arrow.x1
            self._drag_arrow_dy = arrow.y2 - arrow.y1
            self._group_drag_arrow_offsets = {}
            for a in self.selected_arrows:
                if a is not arrow:
                    amx = (a.x1 + a.x2) / 2
                    amy = (a.y1 + a.y2) / 2
                    self._group_drag_arrow_offsets[a] = (
                        amx - mx, amy - my,
                        a.x2 - a.x1, a.y2 - a.y1,
                    )
        else:
            self._drag_arrow_ox = 0.0
            self._drag_arrow_oy = 0.0
            self._drag_arrow_dx = 0.0
            self._drag_arrow_dy = 0.0
            self._group_drag_arrow_offsets = {}

    def update_arrow_drag(self, sx, sy):
        if not self._drag_arrow:
            return
        wx, wy = self.screen_to_world(sx, sy)
        arrow = self._drag_arrow
        if self._drag_arrow_mode == "body":
            new_mx = wx - self._drag_arrow_ox
            new_my = wy - self._drag_arrow_oy
            half_dx = self._drag_arrow_dx / 2
            half_dy = self._drag_arrow_dy / 2
            arrow.x1 = new_mx - half_dx
            arrow.y1 = new_my - half_dy
            arrow.x2 = new_mx + half_dx
            arrow.y2 = new_my + half_dy
            cur_mx = (arrow.x1 + arrow.x2) / 2
            cur_my = (arrow.y1 + arrow.y2) / 2
            for a, (omx, omy, adx, ady) in self._group_drag_arrow_offsets.items():
                new_amx = cur_mx + omx
                new_amy = cur_my + omy
                a.x1 = new_amx - adx / 2
                a.y1 = new_amy - ady / 2
                a.x2 = new_amx + adx / 2
                a.y2 = new_amy + ady / 2
        elif self._drag_arrow_mode == "start":
            arrow.x1, arrow.y1 = wx, wy
        elif self._drag_arrow_mode == "end":
            arrow.x2, arrow.y2 = wx, wy

    def end_arrow_drag(self):
        arrow = self._drag_arrow
        self._drag_arrow = None
        self._drag_arrow_mode = None
        self._group_drag_arrow_offsets = {}
        return arrow

    def arrows_in_screen_rect(self, sx1, sy1, sx2, sy2):
        """Return all arrows whose midpoint screen position falls within the given rect."""
        found = set()
        for obj in self.objects:
            if not isinstance(obj, Arrow):
                continue
            mx = (obj.x1 + obj.x2) / 2
            my = (obj.y1 + obj.y2) / 2
            cx, cy = self.world_to_screen(mx, my)
            if sx1 <= cx <= sx2 and sy1 <= cy <= sy2:
                found.add(obj)
        return found

    def cards_in_screen_rect(self, sx1, sy1, sx2, sy2):
        """Return all cards whose center screen position falls within the given screen rect."""
        found = set()
        for obj in self.objects:
            if not isinstance(obj, Card):
                continue
            surf = obj.get_surface()
            csw, csh = surf.get_size()
            cx, cy = self.world_to_screen(obj.x + csw / 2, obj.y + csh / 2)
            if sx1 <= cx <= sx2 and sy1 <= cy <= sy2:
                found.add(obj)
        return found

    def group_send_to_bottom(self, cards):
        """Send a set of cards to the bottom of the z-stack, preserving their relative order."""
        in_order = [o for o in self.objects if o in cards]
        for c in in_order:
            self.objects.remove(c)
        for i, c in enumerate(in_order):
            self.objects.insert(i, c)

    # --- Zoom / Pan ---

    def zoom_at(self, sx, sy, factor):
        wx, wy = self.screen_to_world(sx, sy)
        self.zoom = max(0.05, min(3.0, self.zoom * factor))
        self.pan_x = sx - wx * self.zoom
        self.pan_y = sy - wy * self.zoom

    def pan(self, dx, dy):
        self.pan_x += dx
        self.pan_y += dy

    # --- Draw ---

    def draw(self, screen):
        """Draw all objects in z-order (index 0 = bottom, last = top)."""
        for obj in self.objects:
            if isinstance(obj, Card):
                surf = obj.get_surface()
                sw, sh = surf.get_size()
                dw = int(sw * self.zoom)
                dh = int(sh * self.zoom)
                if dw < 2 or dh < 2:
                    continue
                scaled = pygame.transform.smoothscale(surf, (dw, dh))
                short_side = min(int(obj.card_w * self.zoom), int(obj.card_h * self.zoom))
                radius = max(4, short_side // 20)
                mask = _get_corner_mask(dw, dh, radius)
                scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                sx, sy = self.world_to_screen(obj.x, obj.y)
                screen.blit(scaled, (int(sx), int(sy)))
            else:  # Arrow
                x1s, y1s = self.world_to_screen(obj.x1, obj.y1)
                x2s, y2s = self.world_to_screen(obj.x2, obj.y2)
                draw_arrow(screen, obj, x1s, y1s, x2s, y2s, self.zoom)

    def draw_highlight(self, screen, card, color=(255, 220, 0), thickness=3):
        surf = card.get_surface()
        sw, sh = surf.get_size()
        wcx = card.x + sw / 2
        wcy = card.y + sh / 2
        scx, scy = self.world_to_screen(wcx, wcy)
        half_w = card.card_w * self.zoom / 2
        half_h = card.card_h * self.zoom / 2
        a = math.radians(card.rotation)
        cos_a, sin_a = math.cos(a), math.sin(a)
        corners = [(-half_w, -half_h), (half_w, -half_h),
                   (half_w,  half_h), (-half_w,  half_h)]
        pts = [
            (scx + px * cos_a - py * sin_a,
             scy + px * sin_a + py * cos_a)
            for px, py in corners
        ]
        pygame.draw.polygon(screen, color, pts, thickness)

    def draw_arrow_highlight(self, screen, arrow, color=(255, 220, 0)):
        """Draw a thick halo behind an arrow to indicate selection or hover."""
        x1s, y1s = self.world_to_screen(arrow.x1, arrow.y1)
        x2s, y2s = self.world_to_screen(arrow.x2, arrow.y2)
        dx = x2s - x1s
        dy = y2s - y1s
        if math.sqrt(dx * dx + dy * dy) < 4:
            return
        thickness = max(6, int(self.zoom * 10))
        pygame.draw.line(screen, color, (int(x1s), int(y1s)), (int(x2s), int(y2s)), thickness)
        r = max(7, int(self.zoom * 11))
        pygame.draw.circle(screen, color, (int(x1s), int(y1s)), r)
        pygame.draw.circle(screen, color, (int(x2s), int(y2s)), r)

    # --- Serialization ---

    def to_dict(self):
        objects = []
        for obj in self.objects:
            if isinstance(obj, Card):
                objects.append({"type": "card", "data": obj.to_dict()})
            else:
                objects.append({"type": "arrow", "data": obj.to_dict()})
        return {
            "zoom":    self.zoom,
            "pan_x":   self.pan_x,
            "pan_y":   self.pan_y,
            "objects": objects,
        }

    def from_dict(self, data):
        self.zoom  = data.get("zoom",  0.3)
        self.pan_x = data.get("pan_x", 0.0)
        self.pan_y = data.get("pan_y", 0.0)
        self.objects = []
        if "objects" in data:
            for item in data["objects"]:
                if item["type"] == "card":
                    self.objects.append(Card.from_dict(item["data"]))
                else:
                    self.objects.append(Arrow.from_dict(item["data"]))
        else:
            # Legacy format: separate cards and arrows lists (cards drawn first)
            for cd in data.get("cards", []):
                self.objects.append(Card.from_dict(cd))
            for ad in data.get("arrows", []):
                self.objects.append(Arrow.from_dict(ad))
        self.selected_arrows.clear()
