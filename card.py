import pygame
from PIL import Image


class Card:
    def __init__(self, image_path, deck_name, card_name):
        self.image_path = image_path    # currently displayed image (back or front)
        self.front_path = image_path    # always the front face path
        self.back_path  = None          # back image path (set by Deck when drawn face-down)
        self.is_face_down = False       # True = currently showing back
        self.deck_name = deck_name
        self.card_name = card_name
        self.rotation = 0               # 0, 90, 180, 270
        self.x = 100
        self.y = 100
        self._surface_cache = {}
        self._load_image()
        self.card_w, self.card_h = self._pil_image.size  # display dims; overridden by Deck

    def _load_image(self):
        pil_img = Image.open(self.image_path).convert("RGBA")
        self._pil_image = pil_img
        self._surface_cache = {}

    def get_surface(self):
        if self.rotation not in self._surface_cache:
            img = self._pil_image.resize((self.card_w, self.card_h), Image.LANCZOS)
            rotated = img.rotate(-self.rotation, expand=True)
            data = rotated.tobytes()
            size = rotated.size
            surface = pygame.image.fromstring(data, size, "RGBA").convert_alpha()
            self._surface_cache[self.rotation] = surface
        return self._surface_cache[self.rotation]

    def reveal(self):
        """Flip face-down card to show its front."""
        if self.is_face_down:
            self.image_path = self.front_path
            self.is_face_down = False
            self._load_image()

    def flip(self):
        """Toggle between face-down and face-up."""
        if self.is_face_down:
            self.image_path = self.front_path
            self.is_face_down = False
            self._load_image()
        elif self.back_path:
            self.image_path = self.back_path
            self.is_face_down = True
            self._load_image()

    def _apply_rotation(self, new_rotation):
        """Set rotation and adjust x/y so the visual center stays fixed."""
        old_w, old_h = self.get_surface().get_size()
        self.rotation = new_rotation % 360
        self._surface_cache.pop(self.rotation, None)   # invalidate new angle
        new_w, new_h = self.get_surface().get_size()
        if old_w != new_w or old_h != new_h:
            self.x += (old_w - new_w) / 2
            self.y += (old_h - new_h) / 2

    def rotate_cw(self):
        self._apply_rotation(self.rotation + 90)

    def rotate_ccw(self):
        self._apply_rotation(self.rotation - 90)

    def rotate_180(self):
        self._apply_rotation(self.rotation + 180)

    def rotate_45cw(self):
        self._apply_rotation(self.rotation + 45)

    def reset_rotation(self):
        self._apply_rotation(0)

    def get_rect(self):
        return pygame.Rect(self.x, self.y, self.card_w, self.card_h)

    def to_dict(self):
        return {
            "image_path": self.image_path,
            "front_path": self.front_path,
            "back_path":  self.back_path,
            "is_face_down": self.is_face_down,
            "deck_name": self.deck_name,
            "card_name": self.card_name,
            "rotation": self.rotation,
            "x": self.x,
            "y": self.y,
        }

    @classmethod
    def from_dict(cls, data):
        card = cls(data["image_path"], data["deck_name"], data["card_name"])
        card.front_path = data.get("front_path", data["image_path"])
        card.back_path  = data.get("back_path", None)
        card.is_face_down = data.get("is_face_down", False)
        card.rotation = data["rotation"]
        card.x = data["x"]
        card.y = data["y"]
        return card
