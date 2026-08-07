#!/usr/bin/env python3
"""Focused tests for conservative Marker/Surya text fusion."""

from __future__ import annotations

import unittest

from extract_marker_surya_hybrid import (
    flatten_output_blocks,
    fuse_marker_surya_text,
    html_table_to_markdown,
    join_ocr_lines,
    normalized_word,
    strip_html,
)


class MarkerSuryaHybridTests(unittest.TestCase):
    def test_surya_repairs_broken_long_o_font_map(self) -> None:
        marker = "H6koku Daimy6jin, H6j6, and Kant6"
        surya = "Hōkoku Daimyōjin, Hōjō, and Kantō"
        self.assertEqual(
            fuse_marker_surya_text(marker, surya),
            "Hōkoku Daimyōjin, Hōjō, and Kantō",
        )

    def test_surya_proves_marker_word_join(self) -> None:
        marker = "premod ern pageantry"
        surya = "premodern pageantry"
        self.assertEqual(fuse_marker_surya_text(marker, surya), surya)

    def test_marker_remains_authoritative_on_real_disagreement(self) -> None:
        marker = "Hideyoshi ordered the ceremony."
        surya = "Hidevoshi ordered the ceremonv."
        self.assertEqual(fuse_marker_surya_text(marker, surya), marker)

    def test_surya_repairs_lowercase_l_for_uppercase_i(self) -> None:
        self.assertEqual(fuse_marker_surya_text("lmagawa rule", "Imagawa rule"), "Imagawa rule")

    def test_surya_splits_accidentally_joined_marker_words(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text("bound by treatiesto Kyoto", "bound by treaties to Kyoto"),
            "bound by treaties to Kyoto",
        )

    def test_surya_punctuation_frame_preserves_em_dash_and_hyphen(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text(
                "a parttime soldier with a surname-a distinction",
                "a part-time soldier with a surname—a distinction",
            ),
            "a part-time soldier with a surname—a distinction",
        )

    def test_marker_comma_wins_over_surya_period_error(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text(
                "from Owari province, several days away",
                "from Owari province. several days away",
            ),
            "from Owari province, several days away",
        )

    def test_surya_superscript_brackets_plain_marker_number(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text(
                'the country was supplied."4 Architect',
                'the country was supplied.<sup>4</sup> Architect',
            ),
            'the country was supplied."[4] Architect',
        )

    def test_marker_ascii_double_dash_normalizes_to_em_dash(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text("receptions--all", "receptions—all"),
            "receptions—all",
        )

    def test_surya_replaces_block_with_damaged_marker_glyph(self) -> None:
        self.assertEqual(
            fuse_marker_surya_text("recover the� imperial holdings", "recover the imperial holdings"),
            "recover the imperial holdings",
        )

    def test_line_wrap_hyphen_is_joined_for_normal_word(self) -> None:
        self.assertEqual(join_ocr_lines(["pre-", "modern history"]), "premodern history")

    def test_html_cleanup_repairs_possessive_spacing(self) -> None:
        self.assertEqual(strip_html("several days &#39; journey"), "several days' journey")

    def test_normalization_compares_embedded_six_as_long_o(self) -> None:
        self.assertEqual(normalized_word("Daimy6jin"), normalized_word("Daimyōjin"))

    def test_nested_list_items_are_not_dropped(self) -> None:
        blocks = [
            {
                "block_type": "Text",
                "html": "<p>Introduction</p>",
            },
            {
                "block_type": "ListGroup",
                "children": [
                    {"block_type": "ListItem", "html": "<li>Item 1</li>"},
                    {"block_type": "ListItem", "html": "<li>Item 2</li>"},
                ],
            },
        ]
        self.assertEqual(
            [block["block_type"] for block in flatten_output_blocks(blocks)],
            ["Text", "ListItem", "ListItem"],
        )

    def test_grouped_picture_and_caption_keep_source_order(self) -> None:
        blocks = [
            {
                "block_type": "PictureGroup",
                "children": [
                    {"block_type": "Picture", "images": {"image": "encoded"}},
                    {"block_type": "Caption", "html": "<p>Map 1</p>"},
                ],
            }
        ]
        flattened = flatten_output_blocks(blocks)
        self.assertEqual([block["block_type"] for block in flattened], ["Picture"])
        self.assertEqual(flattened[0]["_group_caption_html"], "<p>Map 1</p>")

    def test_table_parent_remains_atomic(self) -> None:
        table = {
            "block_type": "Table",
            "html": "<table><tr><td>A</td></tr></table>",
            "children": [{"block_type": "TableCell", "html": "<td>A</td>"}],
        }
        self.assertEqual(flatten_output_blocks([table]), [table])

    def test_html_table_preserves_rows_and_merges_wrapped_cells(self) -> None:
        source = """
        <table><tbody>
          <tr><th>·</th><th>U</th><th></th><th></th><th></th></tr>
          <tr><th>Location</th><th>Type</th><th>Size</th><th>Value</th><th>Cultivator</th></tr>
          <tr><td>Same</td><td>superior dry</td><td></td><td></td><td></td></tr>
          <tr><td></td><td>field</td><td>96</td><td>0.3.8.4</td><td>Same</td></tr>
        </tbody></table>
        """
        self.assertEqual(
            html_table_to_markdown(source),
            "\n".join(
                [
                    "| Location | Type | Size | Value | Cultivator |",
                    "| --- | --- | --- | --- | --- |",
                    "| Same | superior dry field | 96 | 0.3.8.4 | Same |",
                ]
            ),
        )

    def test_one_row_table_remains_caption_text(self) -> None:
        self.assertEqual(
            html_table_to_markdown(
                "<table><tr><th>Table</th><th>1.</th><th>Caption</th></tr></table>"
            ),
            "Table 1. Caption",
        )


if __name__ == "__main__":
    unittest.main()
