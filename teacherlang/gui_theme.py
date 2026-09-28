"""Colors and fonts for the GUI viewer; free of Tk imports so it loads without Tk."""

from dataclasses import dataclass

# Mid-tone colors that stay readable on both light and dark system backgrounds.
TAG_COLORS = {
    "dim": "gray55",
    "red": "#d9534f",
    "green": "#3c9d4f",
    "cyan": "#1f9bb5",
    "yellow": "#d08c00",
}
# Tags rendered through a font change instead of a color.
FONT_TAGS = {"bold"}
SAVED_COLOR = "#e0a800"
SMALLEST_FONT_SIZE = 8


@dataclass(frozen=True)
class Palette:
    background: str
    text: str
    secondary: str
    disabled: str
    separator: str
    accent: str


# macOS dynamic colors follow the light/dark appearance. Tk drops their alpha, so the
# translucent label colors (secondary, tertiary) would turn solid; mid-tones stand in for them.
AQUA_PALETTE = Palette(background="systemTextBackgroundColor", text="systemTextColor",
                       secondary="gray55", disabled="gray70", separator="systemGridColor",
                       accent="systemControlAccentColor")
DEFAULT_PALETTE = Palette(background="white", text="black", secondary="gray45",
                          disabled="gray70", separator="gray85", accent="#1f6fd1")


def palette_for(windowing_system: str) -> Palette:
    return AQUA_PALETTE if windowing_system == "aqua" else DEFAULT_PALETTE


@dataclass(frozen=True)
class FontSizes:
    body: int
    headline: int
    small: int


def font_sizes(body: int) -> FontSizes:
    """Card font sizes scaled from the body size chosen in the settings."""
    return FontSizes(body=body, headline=body + 3, small=max(SMALLEST_FONT_SIZE, body - 2))


class CardFonts:
    """Fonts copied from a base Tk font; `resize` rescales them together."""

    def __init__(self, base_font, body_size: int):
        self.body = base_font.copy()
        self.bold = base_font.copy()
        self.bold.configure(weight="bold")
        self.headline = base_font.copy()
        self.headline.configure(weight="bold")
        self.small = base_font.copy()
        self.section = base_font.copy()
        self.section.configure(weight="bold")
        self.resize(body_size)

    def resize(self, body_size: int) -> None:
        sizes = font_sizes(body_size)
        self.body.configure(size=sizes.body)
        self.bold.configure(size=sizes.body)
        self.headline.configure(size=sizes.headline)
        self.small.configure(size=sizes.small)
        self.section.configure(size=sizes.small)
