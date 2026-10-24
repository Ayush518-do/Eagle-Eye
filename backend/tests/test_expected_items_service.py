"""Contract A replacement rules: hash check, parser_version, replace-not-append, atomicity."""
import pytest
from alembic import command
from sqlalchemy import inspect

from backend.app.db import make_engine
from backend.app.models import Cabinet, DesignRevision
from backend.app.schemas import DrawingParseResult, ExpectedItem
from backend.app.services.expected_items import (
    ExpectedItemsError, list_expected_items, replace_expected_items,
)

from .conftest import alembic_config

PDF_SHA = "ab" * 32


@pytest.fixture
def revision_id(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="x"))
        s.add(DesignRevision(id="DREV-1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                             drawing_sha256=PDF_SHA))
        s.commit()
    return "DREV-1"


def parsed_items() -> list[ExpectedItem]:
    return DrawingParseResult.model_validate({
        "drawing_file_sha256": PDF_SHA, "parser_version": "drawing-parser 0.1.0",
        "items": [
            {"tag": "CB11", "part_number": "P1", "description": "MCB", "quantity": 1,
             "rating": {"value": "10 A", "source": "schematic", "page": 5, "needs_review": False},
             "source_page": 3},
            {"tag": "PS11", "rating": {"value": None, "source": "schematic", "page": 4, "needs_review": True},
             "source_page": 3},
            {"tag": "X1"},
        ]}).items


def stored(session_factory, rid):
    with session_factory() as s:
        return [(i.tag, i.rating_value, i.rating_source, i.rating_page, i.rating_needs_review, i.source_page)
                for i in list_expected_items(s, rid)]


def revision_parser(session_factory, rid):
    with session_factory() as s:
        return s.get(DesignRevision, rid).parser_version


# ---------- migration 0004 ----------
def test_parser_version_column_is_nullable_and_new_revisions_default_to_null(session_factory, revision_id):
    cols = {c["name"]: c for c in inspect(session_factory.kw["bind"]).get_columns("design_revisions")}
    assert cols["parser_version"]["nullable"] is True
    assert revision_parser(session_factory, revision_id) is None


def test_0004_downgrade_keeps_revisions_and_reupgrades(session_factory, migrated_db_url, revision_id):
    cfg = alembic_config(migrated_db_url)
    command.downgrade(cfg, "0003")
    engine = make_engine(migrated_db_url)
    assert "parser_version" not in {c["name"] for c in inspect(engine).get_columns("design_revisions")}
    engine.dispose()
    command.upgrade(cfg, "head")  # the foreign-key check in env.py runs on both steps
    engine = make_engine(migrated_db_url)
    assert "parser_version" in {c["name"] for c in inspect(engine).get_columns("design_revisions")}
    engine.dispose()


# ---------- drawing_file_sha256 ----------
def test_matching_hash_is_accepted_case_insensitively(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items(), drawing_file_sha256=PDF_SHA.upper())
        s.commit()
    assert len(stored(session_factory, revision_id)) == 3


def test_mismatching_hash_is_rejected_and_nothing_changes(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items(), parser_version="p 1")
        s.commit()
    before = stored(session_factory, revision_id)
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_expected_items(s, revision_id, [ExpectedItem(tag="NEW")],
                                   parser_version="p 2", drawing_file_sha256="00" * 32)
        assert e.value.status_code == 409 and "does not match" in e.value.detail
        s.rollback()
    assert stored(session_factory, revision_id) == before
    assert revision_parser(session_factory, revision_id) == "p 1"


def test_missing_stored_hash_is_reported_not_treated_as_verified(session_factory, revision_id):
    with session_factory() as s:
        s.get(DesignRevision, revision_id).drawing_sha256 = ""
        s.commit()
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_expected_items(s, revision_id, parsed_items(), drawing_file_sha256=PDF_SHA)
        assert e.value.status_code == 409 and "cannot be verified" in e.value.detail


def test_hash_is_optional(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items())
        s.commit()
    assert len(stored(session_factory, revision_id)) == 3


def test_unknown_revision_is_404(session_factory):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_expected_items(s, "DREV-NOPE", [])
        assert e.value.status_code == 404


# ---------- parser_version ----------
def test_parser_version_is_stored_when_supplied(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items(), parser_version="drawing-parser 0.1.0")
        s.commit()
    assert revision_parser(session_factory, revision_id) == "drawing-parser 0.1.0"


def test_manual_replacement_keeps_the_previous_parser_version(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items(), parser_version="drawing-parser 0.1.0")
        s.commit()
    with session_factory() as s:
        replace_expected_items(s, revision_id, [ExpectedItem(tag="MANUAL1")])  # no parser_version
        s.commit()
    assert revision_parser(session_factory, revision_id) == "drawing-parser 0.1.0"
    assert [r[0] for r in stored(session_factory, revision_id)] == ["MANUAL1"]


def test_new_parser_version_replaces_the_old_one(session_factory, revision_id):
    for version in ("drawing-parser 0.1.0", "drawing-parser 0.2.0"):
        with session_factory() as s:
            replace_expected_items(s, revision_id, parsed_items(), parser_version=version)
            s.commit()
    assert revision_parser(session_factory, revision_id) == "drawing-parser 0.2.0"


def test_manual_list_on_a_fresh_revision_leaves_parser_version_null(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, [ExpectedItem(tag="M1")])
        s.commit()
    assert revision_parser(session_factory, revision_id) is None


def test_blank_parser_version_is_rejected(session_factory, revision_id):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_expected_items(s, revision_id, parsed_items(), parser_version="  ")
        assert e.value.status_code == 400


# ---------- replace, not append ----------
def test_contract_a_fields_are_stored_per_item(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items())
        s.commit()
    assert stored(session_factory, revision_id) == [
        ("CB11", "10 A", "schematic", 5, False, 3),
        ("PS11", None, "schematic", 4, True, 3),
        ("X1", None, None, None, False, None),
    ]


def test_second_replacement_replaces_instead_of_appending(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items())
        s.commit()
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items()[:1])
        s.commit()
    assert [r[0] for r in stored(session_factory, revision_id)] == ["CB11"]


def test_replacing_with_an_empty_list_clears_the_items(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items())
        s.commit()
    with session_factory() as s:
        replace_expected_items(s, revision_id, [])
        s.commit()
    assert stored(session_factory, revision_id) == []


def test_replacement_only_touches_the_given_revision(session_factory, revision_id):
    with session_factory() as s:
        s.add(DesignRevision(id="DREV-2", cabinet_id="CAB-001", label="REV-B", drawing_file_id="g",
                             drawing_sha256="cd" * 32))
        s.commit()
        replace_expected_items(s, "DREV-2", [ExpectedItem(tag="OTHER")])
        replace_expected_items(s, revision_id, parsed_items())
        s.commit()
    with session_factory() as s:
        replace_expected_items(s, revision_id, [])
        s.commit()
    assert [r[0] for r in stored(session_factory, "DREV-2")] == ["OTHER"]


# ---------- atomicity ----------
def test_failed_replacement_leaves_the_old_list_and_parser_version(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items(), parser_version="p 1")
        s.commit()
    before = stored(session_factory, revision_id)
    bad = ExpectedItem.model_construct(tag=None)  # NOT NULL violation, after the first new row is added
    with session_factory() as s:
        with pytest.raises(Exception):
            replace_expected_items(s, revision_id, [ExpectedItem(tag="GOOD"), bad], parser_version="p 2")
    assert stored(session_factory, revision_id) == before
    assert revision_parser(session_factory, revision_id) == "p 1"


def test_replacement_is_not_visible_until_the_caller_commits(session_factory, revision_id):
    with session_factory() as s:
        replace_expected_items(s, revision_id, parsed_items())
        assert stored(session_factory, revision_id) == []  # other connection sees nothing yet
        s.rollback()
    assert stored(session_factory, revision_id) == []
