import math
import pygame


# 7 preset color swatches shown in the Session Panel
ARROW_SWATCHES = [
    (  0,   0,   0),   # black
    (255, 255, 255),   # white
    (220,  50,  50),   # red
    ( 60, 120, 220),   # blue
    ( 50, 180,  80),   # green
    (220, 160,  30),   # gold
    (160,  60, 200),   # purple
]


class Arrow:
    """A canvas annotation arrow — not tied to any deck pile."""

    def __init__(self, x1, y1, x2, y2, color=(0, 0, 0), style="plain",
                 both_ends=False, weight=3):
        self.x1 = float(x1)
        self.y1 = float(y1)
        self.x2 = float(x2)
        self.y2 = float(y2)
        self.color     = tuple(color)
        self.style     = style       # "plain" | "rope" | "chain"
        self.both_ends = both_ends   # True = arrowhead at both endpoints
        self.weight    = int(weight) # 1–10, controls shaft+head size

    def to_dict(self):
        return {
            "x1": self.x1, "y1": self.y1,
            "x2": self.x2, "y2": self.y2,
            "color":     list(self.color),
            "style":     self.style,
            "both_ends": self.both_ends,
            "weight":    self.weight,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["x1"], data["y1"],
            data["x2"], data["y2"],
            color=tuple(data.get("color", [0, 0, 0])),
            style=data.get("style", "plain"),
            both_ends=data.get("both_ends", False),
            weight=data.get("weight", 3),
        )


# ── Pygame screen-space drawing ────────────────────────────────────────────

def draw_arrow(screen, arrow, x1s, y1s, x2s, y2s, zoom, color_override=None):
    """Draw an arrow in screen space.  color_override is used for highlight halos."""
    color = color_override if color_override is not None else arrow.color

    dx = x2s - x1s
    dy = y2s - y1s
    length = math.sqrt(dx * dx + dy * dy)
    if length < 4:
        return

    ux, uy = dx / length, dy / length   # unit vector along arrow direction
    px, py = -uy, ux                     # perpendicular unit vector

    # weight (1-10) scales both shaft and head proportionally
    head_w    = max(4,  int(zoom * arrow.weight * 3.15))
    head_len  = max(9,  int(head_w * 1.62))
    thickness = max(1,  int(head_w * 0.45))

    # Shaft endpoints — pulled back from tips to leave room for arrowheads
    shaft_x2 = x2s - ux * head_len
    shaft_y2 = y2s - uy * head_len
    shaft_x1 = x1s + (ux * head_len if arrow.both_ends else 0)
    shaft_y1 = y1s + (uy * head_len if arrow.both_ends else 0)

    # Draw shaft
    if arrow.style == "rope":
        _draw_rope(screen, shaft_x1, shaft_y1, shaft_x2, shaft_y2,
                   ux, uy, px, py, color, zoom, thickness)
    elif arrow.style == "chain":
        _draw_chain(screen, shaft_x1, shaft_y1, shaft_x2, shaft_y2,
                    ux, uy, px, py, color, zoom, thickness)
    else:  # plain
        pygame.draw.line(screen, color,
                         (int(shaft_x1), int(shaft_y1)),
                         (int(shaft_x2), int(shaft_y2)), thickness)

    # Forward arrowhead at (x2s, y2s)
    tip   = (int(x2s), int(y2s))
    left  = (int(shaft_x2 + px * head_w), int(shaft_y2 + py * head_w))
    right = (int(shaft_x2 - px * head_w), int(shaft_y2 - py * head_w))
    pygame.draw.polygon(screen, color, [tip, left, right])

    # Optional reverse arrowhead at (x1s, y1s)
    if arrow.both_ends:
        tip2   = (int(x1s), int(y1s))
        left2  = (int(shaft_x1 - px * head_w), int(shaft_y1 - py * head_w))
        right2 = (int(shaft_x1 + px * head_w), int(shaft_y1 + py * head_w))
        pygame.draw.polygon(screen, color, [tip2, left2, right2])


def _draw_rope(screen, x1, y1, x2, y2, ux, uy, px, py, color, zoom, thickness=2):
    shaft_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if shaft_len < 2:
        return
    n_pts     = max(20, int(shaft_len / 4))
    amplitude = max(3, int(zoom * 6))
    waves     = max(2, int(shaft_len / max(20, int(zoom * 40))))
    pts = []
    for i in range(n_pts + 1):
        t   = i / n_pts
        cx  = x1 + ux * shaft_len * t
        cy  = y1 + uy * shaft_len * t
        off = amplitude * math.sin(t * math.pi * 2 * waves)
        pts.append((int(cx + px * off), int(cy + py * off)))
    if len(pts) >= 2:
        pygame.draw.lines(screen, color, False, pts, thickness)


def _draw_chain(screen, x1, y1, x2, y2, ux, uy, px, py, color, zoom, thickness=2):
    shaft_len  = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if shaft_len < 2:
        return
    link_major = max(9, int(zoom * 14))
    link_minor = max(4, int(zoom * 7))
    spacing    = link_major * 1.8
    n_links    = max(1, int(shaft_len / spacing))
    arrow_ang  = math.atan2(uy, ux)
    for i in range(n_links):
        t  = (i + 0.5) / n_links
        cx = x1 + ux * shaft_len * t
        cy = y1 + uy * shaft_len * t
        if i % 2 == 0:
            rx, ry, ang = link_major, link_minor, arrow_ang
        else:
            rx, ry, ang = link_minor, link_major, arrow_ang + math.pi / 2
        _draw_ellipse_poly(screen, color, cx, cy, rx, ry, ang, thickness)


def _draw_ellipse_poly(screen, color, cx, cy, rx, ry, angle, width=2, n=16):
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    pts = []
    for i in range(n):
        t  = 2 * math.pi * i / n
        ex = rx * math.cos(t)
        ey = ry * math.sin(t)
        pts.append((int(cx + ex * cos_a - ey * sin_a),
                    int(cy + ex * sin_a + ey * cos_a)))
    if len(pts) >= 3:
        pygame.draw.polygon(screen, color, pts, width)


# ── Hit testing ────────────────────────────────────────────────────────────

def point_to_segment_dist(px, py, x1, y1, x2, y2):
    """Minimum distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t  = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    nx = x1 + t * dx
    ny = y1 + t * dy
    return math.sqrt((px - nx) ** 2 + (py - ny) ** 2)


# ── PIL export ─────────────────────────────────────────────────────────────

def draw_arrow_pil(draw, arrow, x1, y1, x2, y2):
    """Draw an arrow onto a PIL ImageDraw object (for PNG export at full resolution)."""
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length < 4:
        return

    color = tuple(arrow.color)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    # Head size: weight-based, capped at 10% of arrow length so two heads on a
    # both-ended arrow never eat the shaft and create a diamond shape.
    head_w   = max(4,  min(int(arrow.weight * 3.15), int(length * 0.10)))
    head_len = max(9,  int(head_w * 1.62))

    shaft_x2 = x2 - ux * head_len
    shaft_y2 = y2 - uy * head_len
    shaft_x1 = x1 + (ux * head_len if arrow.both_ends else 0)
    shaft_y1 = y1 + (uy * head_len if arrow.both_ends else 0)

    shaft_w = max(1, int(head_w * 0.45))
    if arrow.style == "rope":
        _draw_rope_pil(draw, shaft_x1, shaft_y1, shaft_x2, shaft_y2,
                       ux, uy, px, py, color, shaft_w)
    elif arrow.style == "chain":
        _draw_chain_pil(draw, shaft_x1, shaft_y1, shaft_x2, shaft_y2,
                        ux, uy, px, py, color, shaft_w)
    else:
        draw.line([(int(shaft_x1), int(shaft_y1)), (int(shaft_x2), int(shaft_y2))],
                  fill=color, width=shaft_w)

    # Forward arrowhead
    tip   = (int(x2), int(y2))
    left  = (int(shaft_x2 + px * head_w), int(shaft_y2 + py * head_w))
    right = (int(shaft_x2 - px * head_w), int(shaft_y2 - py * head_w))
    draw.polygon([tip, left, right], fill=color)

    if arrow.both_ends:
        tip2   = (int(x1), int(y1))
        left2  = (int(shaft_x1 - px * head_w), int(shaft_y1 - py * head_w))
        right2 = (int(shaft_x1 + px * head_w), int(shaft_y1 + py * head_w))
        draw.polygon([tip2, left2, right2], fill=color)


def _draw_rope_pil(draw, x1, y1, x2, y2, ux, uy, px, py, color, width=4):
    shaft_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if shaft_len < 2:
        return
    n_pts = max(20, int(shaft_len / 4))
    amp   = max(3, 6)
    waves = max(2, int(shaft_len / 40))
    pts = []
    for i in range(n_pts + 1):
        t   = i / n_pts
        cx  = x1 + ux * shaft_len * t
        cy  = y1 + uy * shaft_len * t
        off = amp * math.sin(t * math.pi * 2 * waves)
        pts.append((int(cx + px * off), int(cy + py * off)))
    if len(pts) >= 2:
        draw.line(pts, fill=color, width=width)


def _draw_chain_pil(draw, x1, y1, x2, y2, ux, uy, px, py, color, width=2):
    shaft_len  = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if shaft_len < 2:
        return
    link_major = 14
    link_minor = 7
    spacing    = link_major * 1.8
    n_links    = max(1, int(shaft_len / spacing))
    arrow_ang  = math.atan2(uy, ux)
    for i in range(n_links):
        t  = (i + 0.5) / n_links
        cx = x1 + ux * shaft_len * t
        cy = y1 + uy * shaft_len * t
        if i % 2 == 0:
            rx, ry, ang = link_major, link_minor, arrow_ang
        else:
            rx, ry, ang = link_minor, link_major, arrow_ang + math.pi / 2
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)
        pts = []
        for j in range(16):
            t2 = 2 * math.pi * j / 16
            ex = rx * math.cos(t2)
            ey = ry * math.sin(t2)
            pts.append((int(cx + ex * cos_a - ey * sin_a),
                        int(cy + ex * sin_a + ey * cos_a)))
        if len(pts) >= 3:
            draw.polygon(pts, outline=color, width=width)
