import unittest
from unittest.mock import Mock

from teacherlang.gui import LessonWindow

from teacherlang.gui_theme import (
    AQUA_PALETTE,
    DEFAULT_PALETTE,
    SMALLEST_FONT_SIZE,
    CardFonts,
    font_sizes,
    palette_for,
)

from teacherlang.render import FIELD, ITEM, Block, Span


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


class FieldLabelTest(unittest.TestCase):
    def setUp(self):
        self.window = LessonWindow.__new__(LessonWindow)
        self.window._text = Mock()
        self.window._palette = DEFAULT_PALETTE
        self.window._fold_hovered = False
        self.window._fonts = CardFonts(FakeFont(), 14)
        self.window._fonts.body.metrics = Mock(return_value=20)
        self.window._fonts.body.measure = Mock(return_value=10)
        self.window._fonts.small.measure = Mock(return_value=25)
        self.window._text.winfo_width.return_value = 500

    def test_fields_use_colon_and_separate_label_tag(self):
        for label, tag in (("원문", None), ("개선", "bold")):
            with self.subTest(label=label):
                self.window._text.reset_mock()
                self.window._insert_block(Block(FIELD, [Span("A sentence.", tag)], label),
                                          None, 0)
                self.assertEqual(
                    [call.args for call in self.window._text.insert.call_args_list],
                    [("end", f"{label}:", (FIELD, "field_label")),
                     ("end", "\t", (FIELD,)),
                     ("end", "A sentence.", (FIELD, *((tag,) if tag else ())))])

    def test_field_font_and_column_follow_small_font_after_resize(self):
        for size in (9, 14, 32):
            with self.subTest(size=size):
                self.window.set_font_size(size)
                self.assertEqual(self.window._fonts.small.options["size"], max(8, size - 2))
                self.window._text.tag_configure.assert_any_call(
                    "field_label", font=self.window._fonts.small,
                    foreground=DEFAULT_PALETTE.secondary)
                self.window._fonts.small.measure.assert_any_call("원문:")
                self.window._fonts.small.measure.assert_any_call("개선:")
                self.window._text.tag_configure.assert_any_call(
                    FIELD, lmargin2=45, tabs=(45,), spacing1=4)
                self.window._text.tag_raise.assert_any_call("field_label")

    def test_item_bullets_keep_their_existing_tag(self):
        self.window._insert_block(Block(ITEM, [Span("Example.")]), None, 0)
        self.window._text.insert.assert_any_call("end", "·  ", (ITEM, "label"))
        self.window._configure_layout_tags()
        self.window._text.tag_configure.assert_any_call(
            "label", foreground=DEFAULT_PALETTE.secondary)


if __name__ == "__main__":
    unittest.main()
