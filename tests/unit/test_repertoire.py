"""Every committed repertoire line is validated here, never by memory (brief §13.2)."""

from pathlib import Path

import pytest

from app.book.loader import load_book
from catalog.loader import index_by_position, load_catalog, source_commit
from catalog.validate import validate

REPERTOIRE_DIR = Path(__file__).parents[2] / "repertoire"


@pytest.fixture(scope="module")
def book():
    return load_book(REPERTOIRE_DIR)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_catalog_is_complete(catalog):
    assert len(catalog) == 3865
    assert sum(entry.name.startswith("Caro-Kann") for entry in catalog) == 110


def test_every_variation_matches_the_catalog(book, catalog):
    assert validate(book, index_by_position(catalog)) == []


def test_validator_detects_wrong_names(book, catalog):
    index = index_by_position(catalog)
    variant = book.variants["caro-kann.advance.short"]
    tampered = type(book)(
        book.repertoires,
        {variant.variant_id: type(variant)(**{**variant.__dict__, "opening": "Made Up Name"})},
    )
    assert "Made Up Name" in validate(tampered, index)[0]


def test_every_variation_has_eco_opening_and_pinned_source(book):
    for variant in book.variants.values():
        assert variant.eco and variant.opening, variant.variant_id
        assert source_commit() in variant.source, variant.variant_id


def test_variant_ids_are_namespaced_by_repertoire(book):
    for variant in book.variants.values():
        assert variant.variant_id.startswith(f"{variant.repertoire_id}."), variant.variant_id


def test_repertoires_and_colors(book):
    assert {key: rep.color for key, rep in book.repertoires.items()} == {
        "caro-kann": "black",
        "sicilian-taimanov": "black",
        "vienna": "white",
        "sicilian-rossolimo": "white",
        "sicilian-moscow": "white",
        "sicilian-alapin": "white",
    }
    assert len(book.variants) == 48
