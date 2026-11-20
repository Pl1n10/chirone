from chirone.catalog import Catalog


def test_catalog_is_consistent():
    cat = Catalog()
    assert cat.validate() == []


def test_every_fault_category_has_a_fault():
    cat = Catalog()
    covered = {f.category for f in cat.faults.values()}
    assert covered == {c.id for c in cat.categories.values() if c.source == "lab"}


def test_every_category_fix_is_exercised_by_some_fault():
    """A fix with no lab fault has no verified training data."""
    cat = Catalog()
    exercised = {f.expected.fix_id for f in cat.faults.values()}
    from_requests = {f for c in cat.categories.values() if c.source == "requests" for f in c.fixes}
    # info.what_i_can_do is labelled from datagen.offtopic (not a fault: nothing is broken)
    missing = set(cat.playbooks) - exercised - from_requests - {"escalate.human", "info.what_i_can_do"}
    assert missing == set(), f"no lab fault for {missing}"
