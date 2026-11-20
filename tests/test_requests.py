"""Labels of search requests must only use the person's own words."""
import random

from chirone.catalog import Catalog
from datagen.requests import valid_search

Q = Catalog().playbooks["web.search"].params["query"]


def v(req, q, seed=0):
    return valid_search({"request": req, "query": q}, Q, random.Random(seed))


def test_keywords_from_the_request_are_kept():
    assert v("vorrei sapere com'è l'orario dei treni da Napoli a Salerno stasera",
             "orario treni Napoli Salerno stasera") is not None


def test_invented_word_is_dropped():
    assert v("fammi vedere se c'è il sole domani a Positano", "meteo Positano domani") is None


def test_bare_query_mostly_dropped():
    kept = sum(v("ricetta pastiera", "ricetta pastiera", seed=s) is not None for s in range(200))
    assert 10 < kept < 80  # ~20%


def test_unsafe_query_dropped():
    assert v('cerca -rf "tutto"', "-rf") is None


def test_action_params_resolve_on_the_pc():
    from pathlib import Path

    import yaml

    from datagen.build_dataset import action_params

    concepts = yaml.safe_load(Path("datagen/apps.yaml").read_text(encoding="utf-8"))
    probes = {"apps_installed": "galculator: Galculator (Calcolatrice)\nthunar: Thunar",
              "browser_default": "firefox-esr.desktop"}
    assert action_params({"fix_id": "app.open", "concept": "calculator"}, probes, concepts) == {"app": "galculator"}
    assert action_params({"fix_id": "app.open", "concept": "letter"}, probes, concepts) is None
    assert action_params({"fix_id": "web.search", "query": "meteo"}, probes, concepts) == {
        "query": "meteo", "browser": "firefox-esr"}
    assert action_params({"fix_id": "web.search", "query": "x"}, {"browser_default": "chromium.desktop"},
                         concepts) is None


def test_minutes_only_from_what_the_request_says():
    from datagen.requests import minutes_mentioned as m

    assert 30 in m("ricordami tra mezz'ora la pastiglia")
    assert 15 in m("fra un quarto d’ora il forno")
    assert 120 in m("tra 2 ore chiama Mario")
    assert 90 in m("in an hour and a half call mum")
    assert 45 in m("remind me in 45 minutes")
    assert 10 in m("tra dieci minuti la lavatrice")
    assert 60 in m("tra un'ora il dottore")
    assert m("ricordami la pastiglia") == set()


def test_reminder_label_checked():
    from datagen.requests import valid_reminder

    tp = Catalog().playbooks["reminder.set"].params["text"]
    ok = {"request": "tra mezz'ora ricordami di prendere la pastiglia", "minutes": 30,
          "text": "prendere la pastiglia"}
    assert valid_reminder(ok, tp) == ok
    assert valid_reminder({**ok, "minutes": 60}, tp) is None          # teacher's arithmetic is not trusted
    assert valid_reminder({**ok, "text": "prendere la medicina"}, tp) is None  # invented word


def test_volume_number_must_be_written():
    from datagen.requests import valid_volume

    assert valid_volume({"request": "metti il volume al 50", "percent": 50}) == {
        "request": "metti il volume al 50", "percent": 50}
    assert valid_volume({"request": "metti il volume a metà", "percent": 50}) is None


def test_action_params_for_fixed_and_extracted_actions():
    from datagen.build_dataset import action_params

    probes = {"browser_default": "firefox.desktop"}
    assert action_params({"fix_id": "web.open_site", "params": {"site": "inps"}}, probes, {}) == {
        "site": "inps", "browser": "firefox"}
    assert action_params({"fix_id": "reminder.set", "params": {"minutes": 30, "text": "pastiglia"}},
                         probes, {}) == {"minutes": 30, "text": "pastiglia"}
