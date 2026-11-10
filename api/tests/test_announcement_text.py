import unittest

from src.utils import announcement_text as text

NOTES = """## Novedades de la 2.40

Una **gran** versión con _varias_ cosas:

- Nuevo: la página de *Novedades*
  - con sub-puntos
- Arreglo: `Temporada` ya no falla
1. Primero
2. Segundo

> Un aviso importante

Más en [la guía](https://example.com/guia?a=1&b=2).

---
Gracias <3 & hasta pronto"""


class TelegramHtmlTests(unittest.TestCase):
    def test_release_notes_are_drawn_with_bold_bullets_links_and_quotes(self):
        drawn = text.to_telegram_html(NOTES)
        self.assertIn("<b>Novedades de la 2.40</b>", drawn)
        self.assertIn("Una <b>gran</b> versión con <i>varias</i> cosas:", drawn)
        self.assertIn("• Nuevo: la página de <i>Novedades</i>", drawn)
        self.assertIn("\u2003◦ con sub-puntos", drawn)
        self.assertIn("• Arreglo: <code>Temporada</code> ya no falla", drawn)
        self.assertIn("1. Primero\n2. Segundo", drawn)
        self.assertIn("<blockquote>Un aviso importante</blockquote>", drawn)
        self.assertIn('<a href="https://example.com/guia?a=1&amp;b=2">la guía</a>', drawn)
        self.assertIn(text.RULE_LINE, drawn)
        self.assertIn("Gracias &lt;3 &amp; hasta pronto", drawn)

    def test_html_typed_by_the_admin_is_escaped_never_interpreted(self):
        drawn = text.to_telegram_html('<script>alert(1)</script> <b>x</b> [a](javascript:alert(1)) `<i>`')
        self.assertNotIn("<script>", drawn)
        self.assertNotIn("javascript", drawn)
        self.assertIn("&lt;script&gt;", drawn)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", drawn)
        self.assertIn("<code>&lt;i&gt;</code>", drawn)

    def test_a_link_to_anything_but_http_keeps_only_its_text(self):
        self.assertEqual(text.to_telegram_html("[a](ftp://x.org) [b](http://x.org)"), 'a <a href="http://x.org">b</a>')

    def test_underscores_inside_words_and_stray_marks_are_left_alone(self):
        self.assertEqual(text.to_telegram_html("snake_case_name y 2 * 3 * 4"), "snake_case_name y 2 * 3 * 4")

    def test_a_code_block_is_kept_as_written(self):
        self.assertEqual(text.to_telegram_html("```\n**no** <b>\n```"), "<pre>**no** &lt;b&gt;</pre>")
        self.assertEqual(text.to_telegram_html("```\nsin cerrar"), "<pre>sin cerrar</pre>")

    def test_a_heading_does_not_nest_bold_inside_bold(self):
        self.assertEqual(text.to_telegram_html("# Un **título**"), "<b>Un título</b>")

    def test_blank_lines_collapse_and_the_ends_are_trimmed(self):
        self.assertEqual(text.to_telegram_html("\n\na\n\n\n\nb\n\n"), "a\n\nb")

    def test_strikethrough_and_indentation_beyond_two_levels(self):
        drawn = text.to_telegram_html("~~viejo~~\n- a\n    - b\n        - c\n            - d")
        self.assertIn("<s>viejo</s>", drawn)
        self.assertIn("\u2003\u2003▪ c", drawn)
        self.assertIn("\u2003\u2003▪ d", drawn)


class PlainTests(unittest.TestCase):
    def test_marks_are_taken_off_and_bullets_kept(self):
        plain = text.to_plain("# Título\nUna **gran** `versión` con [guía](https://x.org)\n- uno\n> cita")
        self.assertEqual(plain, "Título\nUna gran versión con guía\n• uno\ncita")

    def test_push_body_is_one_line_or_nothing(self):
        self.assertEqual(text.push_body("# Título\n- uno\n- dos"), "Título · uno · dos")
        self.assertIsNone(text.push_body("  "))
        self.assertIsNone(text.push_body(None))

    def test_a_long_push_body_is_cut_at_a_word_with_an_ellipsis(self):
        body = text.push_body("- " + "palabra " * 60, 40)
        self.assertLessEqual(len(body), 40)
        self.assertTrue(body.endswith("palabra…"))
        self.assertEqual(text.push_body("corto", 40), "corto")


class MessageTests(unittest.TestCase):
    def test_the_title_is_bold_and_escaped_and_the_plain_copy_has_no_tags(self):
        drawn, plain = text.telegram_message("Hola <b> & _adiós_", "un **aviso**")
        self.assertEqual(drawn, "<b>Hola &lt;b&gt; &amp; _adiós_</b>\n\nun <b>aviso</b>")
        self.assertEqual(plain, "Hola <b> & _adiós_\n\nun aviso")

    def test_without_a_message_it_is_only_the_title(self):
        self.assertEqual(text.telegram_message("Hola", None), ("<b>Hola</b>", "Hola"))
        self.assertEqual(text.telegram_message("Hola", "  "), ("<b>Hola</b>", "Hola"))

    def test_the_length_that_counts_is_the_drawn_one(self):
        self.assertFalse(text.too_long("t", "**" + "a" * 3000 + "**"))
        self.assertTrue(text.too_long("t", "a" * 4000))


if __name__ == "__main__":
    unittest.main()
