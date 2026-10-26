"""إعدادات المظهر وتفضيلات المستخدم (ملف settings.json بجانب البيانات)."""
import json
import os

from .data import data_dir

DEFAULTS = {
    "theme": "teal",
    "accent": None,          # لون تمييز مخصّص (hex) أو None لاستخدام لون الثيم
    "font": "IBM Plex Sans Arabic",
    "font_scale": 1.0,
    "radius": 1.0,
    "last_export_dir": None,
}


class Settings(dict):
    def __init__(self, root=None):
        super().__init__(DEFAULTS)
        self.path = os.path.join(root or data_dir(), "settings.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def reset_appearance(self):
        for k in ("theme", "accent", "font", "font_scale", "radius"):
            self[k] = DEFAULTS[k]
