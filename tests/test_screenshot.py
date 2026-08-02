import unittest

from gex_terminal.screenshot import colorize_terminal_svg


class ScreenshotTests(unittest.TestCase):
    def test_colorizes_textual_grayscale_svg_export(self):
        svg = (
            '<svg><style>.a{fill: #101010}.b{fill: #5c5c5c}'
            '.c{fill: #a5a5a5}.d{fill: #c1c1c1}</style></svg>'
        )

        result = colorize_terminal_svg(svg)

        self.assertIn("#080a0d", result)
        self.assertIn("#4ade80", result)
        self.assertIn("#38bdf8", result)
        self.assertIn("#fbbf24", result)
        self.assertNotIn("#101010", result)


if __name__ == "__main__":
    unittest.main()
