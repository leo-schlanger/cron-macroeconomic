"""Blog hygiene rules (pure part)."""

import blog_maintenance as bm
from tests.test_curator import GOOD


def test_short_legacy_post_is_not_a_language_defect():
    short = dict(GOOD, content_pt="O Fed manteve os juros e o mercado reagiu com cautela. " * 10,
                 content_en="The Fed held rates. " * 10)
    assert bm.language_problems(short) == []


def test_language_defects_are_detected():
    english_title = dict(GOOD, title_pt="Eurozone inflation hits high", title_en="Eurozone inflation hits high")
    assert any("título PT igual" in p for p in bm.language_problems(english_title))
    spanish = dict(GOOD, title_pt="Influxo de Inversores Institucionais")
    assert bm.language_problems(spanish)
    english_body = dict(GOOD, content_pt="The market and the investors of the world reacted. " * 40)
    assert bm.language_problems(english_body)


def test_good_post_is_kept():
    assert bm.language_problems(GOOD) == []
