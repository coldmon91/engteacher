import unittest

from teacherlang.gui_theme import (
    AQUA_PALETTE,
    DEFAULT_PALETTE,
    SMALLEST_FONT_SIZE,
    CardFonts,
    font_sizes,
    palette_for,
)


class FakeFont:
    """Stands in for tkinter.font.Font, which needs a running Tk."""

    def __init__(self, **options):
        self.options = options

    def copy(self):
        return FakeFont(**self.options)

    def configure(self, **options):
        self.options.update(options)


class PaletteTest(unittest.TestCase):
    def test_aqua_uses_dynamic_system_colors(self):
        self.assertIs(palette_for("aqua"), AQUA_PALETTE)
        self.assertTrue(AQUA_PALETTE.background.startswith("system"))
        self.assertTrue(AQUA_PALETTE.text.startswith("system"))

    def test_other_systems_use_fixed_colors(self):
        self.assertIs(palette_for("x11"), DEFAULT_PALETTE)
        self.assertIs(palette_for("win32"), DEFAULT_PALETTE)


class FontSizesTest(unittest.TestCase):
    def test_sizes_scale_from_body(self):
        sizes = font_sizes(14)
        self.assertEqual((sizes.body, sizes.headline, sizes.small), (14, 17, 12))

    def test_small_size_has_a_floor(self):
        self.assertEqual(font_sizes(9).small, SMALLEST_FONT_SIZE)

    def test_card_fonts_resize_together(self):
        fonts = CardFonts(FakeFont(family="System", size=10), 14)
        fonts.resize(20)
        self.assertEqual(fonts.body.options["size"], 20)
        self.assertEqual(fonts.bold.options, {"family": "System", "size": 20, "weight": "bold"})
        self.assertEqual(fonts.headline.options["size"], 23)
        self.assertEqual(fonts.small.options["size"], 18)
        self.assertEqual(fonts.section.options["weight"], "bold")


if __name__ == "__main__":
    unittest.main()
