"""ExpectedItemsSubmission, contract_version and duplicate-tag rules."""
import pytest

from backend.app.db import get_db
from backend.app.models import Cabinet, DesignRevision
from backend.app.schemas import CONTRACT_VERSION, DrawingParseResult, ExpectedItem, ExpectedItemsSubmission
from backend.app.services.expected_items import (
    ExpectedItemsError, duplicate_tags, list_expected_items, replace_from_submission,
)

PDF_SHA = "ab" * 32

PARSED = {
    "contract_version": "0.2", "drawing_file_sha256": PDF_SHA, "parser_version": "drawing-parser 0.1.0",
    "items": [
        {"tag": "CB11", "part_number": "P1", "description": "MCB", "quantity": 1,
         "rating": {"value": "10 A", "source": "schematic", "page": 5, "needs_review": False}, "source_page": 3},
        {"tag": "PS11", "rating": {"value": None, "source": "schematic", "page": 4, "needs_review": True},
         "source_page": 3},
    ],
}


@pytest.fixture
def revision_id(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="x"))
        s.add(DesignRevision(id="DREV-1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                             drawing_sha256=PDF_SHA))
        s.commit()
    return "DREV-1"


def tags(session_factory, rid):
    with session_factory() as s:
        return [i.tag for i in list_expected_items(s, rid)]


def parser(session_factory, rid):
    with session_factory() as s:
        return s.get(DesignRevision, rid).parser_version


def store(session_factory, rid, body):
    with session_factory() as s:
        replace_from_submission(s, rid, ExpectedItemsSubmission.model_validate(body))
        s.commit()


# ---------- schema ----------
def test_parsed_result_still_validates_as_both_models():
    parsed = DrawingParseResult.model_validate(PARSED)
    sub = ExpectedItemsSubmission.model_validate(PARSED)
    assert sub.parser_version == parsed.parser_version and sub.items == parsed.items
    assert ExpectedItemsSubmission.model_validate(parsed.model_dump()).items == parsed.items


def test_parsed_result_model_is_unchanged_parser_version_is_still_required():
    with pytest.raises(ValueError):
        DrawingParseResult.model_validate({"items": []})


def test_manual_submission_may_omit_parser_version_hash_and_contract_version():
    sub = ExpectedItemsSubmission.model_validate({"items": [{"tag": "CB11"}]})
    assert sub.parser_version is None and sub.drawing_file_sha256 is None
    assert sub.contract_version == CONTRACT_VERSION == "0.2"


# ---------- contract_version ----------
def test_parsed_submission_is_stored(session_factory, revision_id):
    store(session_factory, revision_id, PARSED)
    assert tags(session_factory, revision_id) == ["CB11", "PS11"]
    assert parser(session_factory, revision_id) == "drawing-parser 0.1.0"


def test_missing_contract_version_is_treated_as_supported(session_factory, revision_id):
    store(session_factory, revision_id, {"items": [{"tag": "M1"}]})
    assert tags(session_factory, revision_id) == ["M1"]


@pytest.mark.parametrize("version", ["0.1", "1.0", "", "0.1.0", "latest"])
def test_unsupported_contract_version_is_a_400_naming_the_supported_one(session_factory, revision_id, version):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, revision_id, ExpectedItemsSubmission(
                contract_version=version, items=[ExpectedItem(tag="A")]))
    assert e.value.status_code == 400
    assert "'0.2'" in e.value.detail and "Unsupported contract_version" in e.value.detail


# ---------- duplicate tags ----------
@pytest.mark.parametrize("names", [["CB11", "CB11"], ["CB11", "cb11"], ["CB11", " CB11 "], ["Cb11", "cB11\t"]])
def test_tags_differing_only_in_case_or_whitespace_are_rejected(session_factory, revision_id, names):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, revision_id, ExpectedItemsSubmission(
                items=[ExpectedItem(tag=n) for n in names]))
    assert e.value.status_code == 400
    assert "Duplicate tags" in e.value.detail and names[0].strip() in e.value.detail


def test_error_names_every_repeated_tag_once_in_first_seen_order():
    items = [ExpectedItem(tag=t) for t in ["B2", "a1", "A1", "b2", " B2", "C3", "a1"]]
    assert duplicate_tags(items) == ["B2", "a1"]


def test_distinct_tags_are_accepted(session_factory, revision_id):
    store(session_factory, revision_id, {"items": [{"tag": "CB11"}, {"tag": "CB12"}, {"tag": "CB1"}]})
    assert tags(session_factory, revision_id) == ["CB11", "CB12", "CB1"]


def test_duplicates_are_only_checked_inside_one_submission(session_factory, revision_id):
    store(session_factory, revision_id, {"items": [{"tag": "CB11"}]})
    store(session_factory, revision_id, {"items": [{"tag": "cb11"}]})  # replaces, so no conflict
    assert tags(session_factory, revision_id) == ["cb11"]


# ---------- rejected submissions change nothing ----------
@pytest.mark.parametrize("body, status", [
    ({"contract_version": "9.9", "parser_version": "new", "items": [{"tag": "X"}]}, 400),
    ({"parser_version": "new", "items": [{"tag": "X"}, {"tag": " x"}]}, 400),
    ({"parser_version": "new", "drawing_file_sha256": "00" * 32, "items": [{"tag": "X"}]}, 409),
    ({"parser_version": "  ", "items": [{"tag": "X"}]}, 400),
])
def test_rejected_submission_leaves_items_and_parser_version_unchanged(session_factory, revision_id, body, status):
    store(session_factory, revision_id, PARSED)
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, revision_id, ExpectedItemsSubmission.model_validate(body))
        assert e.value.status_code == status
    assert tags(session_factory, revision_id) == ["CB11", "PS11"]
    assert parser(session_factory, revision_id) == "drawing-parser 0.1.0"


def test_unknown_revision_is_404(session_factory):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, "DREV-NOPE", ExpectedItemsSubmission(items=[]))
    assert e.value.status_code == 404


# ---------- commit belongs to the endpoint ----------
def test_replacement_is_stored_only_when_the_request_session_commits(session_factory, revision_id):
    body = ExpectedItemsSubmission.model_validate(PARSED)
    gen = get_db(session_factory)  # the same dependency an endpoint receives
    s = next(gen)
    replace_from_submission(s, revision_id, body)
    gen.close()  # request ends without commit
    assert tags(session_factory, revision_id) == []

    gen = get_db(session_factory)
    s = next(gen)
    replace_from_submission(s, revision_id, body)
    s.commit()  # the endpoint's explicit commit
    gen.close()
    assert tags(session_factory, revision_id) == ["CB11", "PS11"]
