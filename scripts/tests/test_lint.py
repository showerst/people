import pytest
from lint_yaml import (is_url, is_social, is_fuzzy_date, is_phone,
                       is_ocd_person, is_legacy_openstates,
                       validate_obj, PERSON_FIELDS, validate_roles,
                       get_expected_districts, compare_districts, Validator) # noqa


def test_is_url():
    assert is_url('http://example.com')
    assert is_url('https://example.com')
    assert not is_url('/fragment')


def test_is_social():
    assert is_social('example_id')
    assert not is_social('@no_at_sign')
    assert not is_social('http://no-urls.com')


def test_is_fuzzy_date():
    assert is_fuzzy_date('2010')
    assert is_fuzzy_date('2019-01')
    assert is_fuzzy_date('2020-01-01')
    assert not is_fuzzy_date('1/1/2011')


def test_is_phone():
    assert is_phone('123-346-7990')
    assert is_phone('1-123-346-7990')
    assert is_phone('1-123-346-7990 ext. 123')
    assert not is_phone('(123) 346-7990')


def test_is_ocd_person():
    assert is_ocd_person('ocd-person/abcdef98-0123-7777-8888-1234567890ab')
    assert not is_ocd_person('abcdef98-0123-7777-8888-1234567890ab')
    assert not is_ocd_person('ocd-person/abcdef980123777788881234567890ab')


def test_is_legacy_openstates():
    assert is_legacy_openstates('AKL000001')
    assert not is_legacy_openstates('AK000001')
    assert not is_legacy_openstates('AK001')


EXAMPLE_OCD_PERSON_ID = 'ocd-person/12345678-0000-1111-2222-1234567890ab'
EXAMPLE_OCD_ORG_ID = 'ocd-organization/00001111-2222-3333-aaaa-444455556666'


def test_validate_required():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
    }

    # with required fields
    assert validate_obj(example, PERSON_FIELDS) == []

    errs = validate_obj({}, PERSON_FIELDS)
    assert len(errs) == 2
    assert 'id missing' in errs


def test_validate_nested_required():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
        'links': [
            {'url': 'https://example.com'},
            {'note': 'note only'},
        ]
    }

    assert validate_obj(example, PERSON_FIELDS) == [
        'links.1.url missing'
    ]


def test_validate_nested_list():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
        'links': [
            {'url': 'example.com'},
        ]
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert 'links.0.url' in errs[0]


def test_validate_nested_role_list():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
        'roles': [
            {'type': 'upper', 'district': '4', 'end_date': '2010',
             'jurisdiction': 'ocd-jurisdiction/country:us/state:nc'},
            {'type': 'gov', 'start_date': '2010',
             'jurisdiction': 'ocd-jurisdiction/country:us/state:nc'},
            # bad roles
            {'type': 'upper',
             'jurisdiction': 'ocd-jurisdiction/country:us/state:nc'},
            {'type': 'gov', 'district': '4',
             'jurisdiction': 'ocd-jurisdiction/country:us/state:nc'},
        ]
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 2
    assert 'roles.2' in errs[0]
    assert 'roles.3' in errs[1]


def test_validate_nested_object():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
        'ids': {
            'twitter': '@bad-name',
            'youtube': 'is-ok',
        }
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert 'ids.twitter' in errs[0]


def test_validate_extra_keys_not_present():
    example = {
        'id': EXAMPLE_OCD_PERSON_ID,
        'name': 'Anne A',
        'junk': 100,
        'links': [
            {'url': 'https://example.com', 'bad': 100},
        ]
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 2
    assert 'extra key: junk' in errs
    assert 'extra key: links.0.bad' in errs


@pytest.mark.parametrize("person,expected", [
    ({"party": [{"name": "Democratic"}]}, []),
    ({"party": [{"name": "Democratic"}, {"name": "Working Families"}]}, []),
    ({"party": []}, ["no active party"]),
    ({"party": [{"name": "Democratic", "end_date": "1990"}]}, ["no active party"]),
])
def test_validate_roles_party(person, expected):
    assert validate_roles(person, "party") == expected


@pytest.mark.parametrize("person,expected", [
    ({"roles": [{"name": "House"}]}, []),
    ({"roles": [{"name": "House"}, {"name": "Senate"}]}, ["2 active roles"]),
    ({"roles": []}, ["no active roles"]),
    ({"roles": [{"name": "House", "end_date": "1990"}]}, ["no active roles"]),
])
def test_validate_roles_roles(person, expected):
    assert validate_roles(person, "roles") == expected


@pytest.mark.parametrize("person,expected", [
    ({"roles": [{"name": "House"}]}, ["1 active roles on retired person"]),
    ({"roles": [{"name": "House"}, {"name": "Senate"}]}, ["2 active roles on retired person"]),
    ({"roles": []}, []),
    ({"roles": [{"name": "House", "end_date": "1990"}]}, []),
])
def test_validate_roles_retired(person, expected):
    assert validate_roles(person, "roles", retired=True) == expected


def test_get_expected_districts():
    expected = get_expected_districts({"upper_seats": 3,
                                       "lower_seats": ["A", "B", "C"],
                                       "legislature_seats": {"At-Large": 3}})
    assert expected['upper'] == {"1": 1, "2": 1, "3": 1}
    assert expected['lower'] == {"A": 1, "B": 1, "C": 1}
    assert expected['legislature'] == {"At-Large": 3}


@pytest.mark.parametrize("expected,actual,errors,warnings", [
    ({"A": 1, "B": 1}, {"A": ['a'], "B": ['a']}, 0, 0),     # good
    ({"A": 1}, {"A": ['a'], "B": ['a']}, 1, 0),             # extra district
    ({"A": 1, "B": 1}, {"A": ['a']}, 0, 1),             # missing district
    ({"A": 1, "B": 1}, {"A": [], "B": ['a']}, 0, 1),     # missing leg
])
def test_compare_districts(expected, actual, errors, warnings):
    e, w = compare_districts({"upper": expected}, {"upper": actual})
    assert len(e) == errors
    assert len(w) == warnings


def test_compare_districts_overfill():
    expected = {"A": 1}
    actual = {'A': [{'id': 'ocd-person/1', 'name': 'Anne'},
                    {'id': 'ocd-person/2', 'name': 'Bob'}]}
    e, w = compare_districts({"upper": expected}, {"upper": actual})
    assert len(e) == 1
    assert len(w) == 0
    assert 'Anne' in e[0]
    assert 'Bob' in e[0]


def test_validator_check_https():
    settings = {'us': {'upper_seats': 100, 'lower_seats': 435},
                'http_whitelist': ['http://bad.example.com']}
    v = Validator(settings, 'us')

    person = {'links': [
        {'url': 'https://example.com'},
        {'url': 'http://insecure.example.com'},
        {'url': 'https://bad.example.com'},
    ]}
    warnings = v.check_https(person)
    assert len(warnings) == 1
    assert 'links.1' in warnings[0]


def test_person_summary():
    settings = {'us': {'upper_seats': 100, 'lower_seats': 435},
                'http_whitelist': ['http://bad.example.com']}
    v = Validator(settings, 'us')

    people = [
        {'gender': 'F', 'image': 'https://example.com/image1',
         'party': [{'name': 'Democratic'}, {'name': 'Democratic', 'end_date': '1990'}],
         },
        {'gender': 'F', 'image': 'https://example.com/image2',
         'party': [{'name': 'Democratic'}, {'name': 'Working Families'}],
         'extras': {'religion': 'Zoroastrian'},
         'contact_details': [{'fax': '123-456-7890'}],
         'other_identifiers': [{'scheme': 'fake', 'identifier': 'abc'}],
         'ids': {'twitter': 'fake'},
         },
        {'gender': 'M', 'image': 'https://example.com/image3',
         'party': [{'name': 'Republican'}],
         'contact_details': [{'phone': '123-456-7890'}],
         'other_identifiers': [{'scheme': 'fake', 'identifier': '123'}],
         },
    ]

    for p in people:
        v.summarize_person(p)

    assert v.parties == {'Republican': 1, 'Democratic': 2,
                         'Working Families': 1}
    assert v.contact_counts == {'phone': 1, 'fax': 1}
    assert v.id_counts == {'fake': 2, 'twitter': 1}
    assert v.optional_fields == {'gender': 3, 'image': 3}
    assert v.extra_counts == {'religion': 1}


def test_validate_org_memberships():
    person = {'id': EXAMPLE_OCD_PERSON_ID,
              'name': 'Jane Smith',
              'roles': [],
              'party': [],
              }
    org = {'id': EXAMPLE_OCD_ORG_ID,
           'name': 'Finance Committee',
           'jurisdiction': 'ocd-jurisdiction/country:us',
           'parent': 'lower',
           'classification': 'committee',
           'memberships': []
           }
    settings = {'us': {'upper_seats': 100, 'lower_seats': 435}}

    # a good membership
    org['memberships'] = [
        {'id': EXAMPLE_OCD_PERSON_ID, 'name': 'Jane Smith'}
    ]
    v = Validator(settings, 'us')
    v.validate_person(person, 'fake-person')    # validate person first to learn ID
    v.validate_org(org, 'fake-org')
    assert v.errors['fake-org'] == []
    assert v.warnings['fake-org'] == []

    # a bad ID
    org['memberships'] = [
        {'id': 'ocd-person/00000000-0000-0000-0000-000000000000', 'name': 'Jane Smith'}
    ]
    v = Validator(settings, 'us')
    v.validate_person(person, 'fake-person')
    v.validate_org(org, 'fake-org')
    assert len(v.errors['fake-org']) == 1

    # bad name, warning
    org['memberships'] = [
        {'id': EXAMPLE_OCD_PERSON_ID, 'name': 'Smith'}
    ]
    v = Validator(settings, 'us')
    v.validate_person(person, 'fake-person')
    v.validate_org(org, 'fake-org')
    assert len(v.warnings['fake-org']) == 1
    assert v.warnings['fake-org']
