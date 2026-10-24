"""Blank tags are rejected; surrounding whitespace is trimmed, case is kept."""
import pytest

from backend.app.models import Cabinet, DesignRevision
from backend.app.schemas import ExpectedItem, ExpectedItemsSubmission
from backend.app.services.expected_items import ExpectedItemsError, list_expected_items, replace_from_submission


@pytest.fixture
def revision_id(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="x"))
        s.add(DesignRevision(id="DREV-1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                             drawing_sha256="ab" * 32))
        s.commit()
    return "DREV-1"


def stored_tags(session_factory, rid):
    with session_factory() as s:
        return [i.tag for i in list_expected_items(s, rid)]


def submit(session_factory, rid, tags, **kw):
    with session_factory() as s:
        replace_from_submission(s, rid, ExpectedItemsSubmission(items=[ExpectedItem(tag=t) for t in tags], **kw))
        s.commit()


@pytest.mark.parametrize("blank", ["", " ", "\t\n"])
def test_blank_tag_is_a_400_and_keeps_the_old_list_and_parser_version(session_factory, revision_id, blank):
    submit(session_factory, revision_id, ["CB11"], parser_version="p 1")
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, revision_id, ExpectedItemsSubmission(
                parser_version="p 2", items=[ExpectedItem(tag="GOOD"), ExpectedItem(tag=blank)]))
    assert e.value.status_code == 400 and "blank" in e.value.detail
    assert stored_tags(session_factory, revision_id) == ["CB11"]
    with session_factory() as s:
        assert s.get(DesignRevision, revision_id).parser_version == "p 1"


def test_tags_are_trimmed_before_storing_and_case_is_preserved(session_factory, revision_id):
    submit(session_factory, revision_id, ["  Cb11 ", "\tps11\n", "X1"])
    assert stored_tags(session_factory, revision_id) == ["Cb11", "ps11", "X1"]


def test_duplicate_detection_is_still_case_insensitive_after_trimming(session_factory, revision_id):
    with session_factory() as s:
        with pytest.raises(ExpectedItemsError) as e:
            replace_from_submission(s, revision_id, ExpectedItemsSubmission(
                items=[ExpectedItem(tag="Cb11"), ExpectedItem(tag=" cB11 ")]))
    assert e.value.status_code == 400 and "Cb11" in e.value.detail
