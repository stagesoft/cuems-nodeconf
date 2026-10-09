"""Regression tests: node fields must not be type-coerced on XML read.

``cuemsutils.xml.Parsers.str_to_value`` guesses a value's Python type from its
text. Before the fix, ``nodeParser`` ran every scalar through it unguarded, so:

- a node named ``"none"`` decoded to ``None`` -> ``<name/>`` -> a hard
  ``NonEmptyString`` validation failure on write;
- ``role_id="n"`` and ``alias="off"`` decoded to ``False`` and
  ``hostname="007"`` to ``7`` -- all schema-valid, so they wrote to disk and
  silently replaced operator data.

The identity fields (role_id/alias/hostname) are the most exposed: role_id is
machine-assigned at adoption and alias is operator free text, both squarely
inside strtobool's vocabulary (n/y/t/f/on/off/no/yes/0/1).
"""
import pytest

from cuemsnodeconf.NodeXmlBuilders import nodeParser

# Stated here as the contract from network_map.xsd, not imported from the
# implementation, so these tests fail on behaviour rather than erroring on a
# missing symbol if the guard is ever removed.
STRING_TYPED_FIELDS = (
    'name', 'node_type', 'ip', 'mac', 'role_id', 'alias', 'hostname',
)


def parse_node(**fields):
    """Run one node dict through the real nodeParser."""
    return nodeParser(init_dict=dict(fields), class_string='node').parse()


class TestStringFieldsSurviveParsing:
    """Values that look like bools/ints/none must stay strings."""

    @pytest.mark.parametrize('value', ['none', 'null', 'n', 'y', 'off', 'on',
                                       'no', 'yes', 'true', 'false', '0', '1',
                                       '007', '42'])
    @pytest.mark.parametrize('field', sorted(STRING_TYPED_FIELDS))
    def test_string_field_not_coerced(self, field, value):
        parsed = parse_node(**{field: value})
        assert parsed[field] == value
        assert isinstance(parsed[field], str)

    def test_node_named_none_survives(self):
        """The hard-failure case: <name/> violates NonEmptyString on write."""
        assert parse_node(name='none')['name'] == 'none'

    def test_identity_fields_survive(self):
        """The silent-corruption case: these validate, so they persist."""
        parsed = parse_node(role_id='n', alias='off', hostname='007')
        assert parsed['role_id'] == 'n'
        assert parsed['alias'] == 'off'
        assert parsed['hostname'] == '007'


class TestIntendedCoercionPreserved:
    """adopted/online -> bool and uuid -> Uuid are relied upon downstream."""

    @pytest.mark.parametrize('field', ['adopted', 'online'])
    @pytest.mark.parametrize('text,expected', [('True', True), ('False', False)])
    def test_bools_still_coerced(self, field, text, expected):
        parsed = parse_node(**{field: text})
        assert parsed[field] is expected

    def test_uuid_still_coerced(self):
        raw = '3f2504e0-4f89-41d3-9a0c-0305e82c3301'
        parsed = parse_node(uuid=raw)
        # Uuid.__eq__/__hash__ interoperate with str, so callers keying on
        # either spelling keep working.
        assert parsed['uuid'] == raw
        assert type(parsed['uuid']).__name__ == 'Uuid'


class TestFullNodeRoundTrip:
    """A whole schema-valid node with adversarial values."""

    def test_all_fields(self):
        node_in = {
            'uuid': '3f2504e0-4f89-41d3-9a0c-0305e82c3301',
            'mac': 'aa:bb:cc:dd:ee:ff',
            'name': 'none',
            'node_type': 'slave',
            'ip': '10.0.0.7',
            'adopted': 'True',
            'online': 'True',
            'role_id': 'n',
            'alias': 'off',
            'hostname': '007',
        }
        parsed = parse_node(**node_in)

        for field in STRING_TYPED_FIELDS:
            assert parsed[field] == node_in[field], f'{field} was coerced'
        assert parsed['adopted'] is True
        assert parsed['online'] is True
        assert parsed['uuid'] == node_in['uuid']
