import jsonschema
import pytest

from chirone.catalog import Catalog
from chirone.schemas import step1_schema, step2_schema, step2_target

SAMPLES = {
    "iface": "enp1s0",
    "connection": "Wired connection 1",
    "file": "vecchio-programma.list",
    "printer": "HP_LaserJet",
    "profile": "a1b2c3.default-esr",
    "sink": "alsa_output.pci-0000_00_1b.0.analog-stereo",
    "pid": 4242,
}


@pytest.fixture(scope="module")
def cat():
    return Catalog()


def test_expected_literal_targets_validate(cat):
    for f in cat.faults.values():
        params = {}
        pb = cat.playbooks[f.expected.fix_id]
        for name, spec in pb.params.items():
            v = f.expected.params.get(name, spec.default)
            if isinstance(v, (str, int)):
                params[name] = int(v) if spec.type == "int" else v
            else:  # capture: fill with a plausible value
                params[name] = SAMPLES[name]
        jsonschema.validate(step2_target(f.expected.fix_id, params), step2_schema(cat, f.category))


def test_schema_rejects_fix_from_other_category(cat):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(step2_target("audio.unmute", {}), step2_schema(cat, "printing"))


def test_step1(cat):
    jsonschema.validate({"category": "audio"}, step1_schema(cat))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"category": "cooking"}, step1_schema(cat))
