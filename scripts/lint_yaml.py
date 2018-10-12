#!/usr/bin/env python
import re
import os
import yaml
import glob
import click
from utils import get_data_dir, get_filename, role_is_active
from collections import defaultdict, Counter


DATE_RE = re.compile(r'^\d{4}(-\d{2}(-\d{2})?)?$')
PHONE_RE = re.compile(r'^(1-)?\d{3}-\d{3}-\d{4}( ext. \d+)?$')
UUID_RE = re.compile(r'^ocd-\w+/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
LEGACY_OS_ID_RE = re.compile(r'[A-Z]{2}L\d{6}')


class Missing:
    pass


class Required:
    pass


class NestedList:
    def __init__(self, subschema):
        self.subschema = subschema


def is_dict(val):
    return isinstance(val, dict)


def is_string(val):
    return isinstance(val, str) and '\n' not in val


def is_url(val):
    return is_string(val) and val.startswith('http')


def is_social(val):
    return is_string(val) and not val.startswith(('http://', 'https://', '@'))


def is_fuzzy_date(val):
    return is_string(val) and DATE_RE.match(val)


def is_phone(val):
    return is_string(val) and PHONE_RE.match(val)


def is_ocd_jurisdiction(val):
    return is_string(val) and val.startswith('ocd-jurisdiction/')


def is_ocd_person(val):
    return is_string(val) and val.startswith('ocd-person/') and UUID_RE.match(val)


def is_ocd_organization(val):
    return is_string(val) and val.startswith('ocd-organization/') and UUID_RE.match(val)


def is_legacy_openstates(val):
    return is_string(val) and LEGACY_OS_ID_RE.match(val)


URL_LIST = NestedList({
    'note': [is_string],
    'url': [is_url, Required],
})


CONTACT_DETAILS = NestedList({
    'note': [is_string, Required],
    'address': [is_string],
    'email': [is_string],
    'voice': [is_phone],
    'fax': [is_phone],
})


LEGISLATIVE_ROLE_FIELDS = {
    'type': [is_string, Required],
    'district': [is_string, Required],
    'jurisdiction': [is_ocd_jurisdiction, Required],
    'start_date': [is_fuzzy_date],
    'end_date': [is_fuzzy_date],
    'contact_details': CONTACT_DETAILS,
}


EXECUTIVE_ROLE_FIELDS = {
    'type': [is_string, Required],
    'jurisdiction': [is_ocd_jurisdiction, Required],
    'start_date': [is_fuzzy_date],
    'end_date': [is_fuzzy_date],
    'contact_details': CONTACT_DETAILS,
}


def is_role(role):
    role_type = role.get('type')
    if role_type in ('upper', 'lower', 'legislature'):
        return validate_obj(role, LEGISLATIVE_ROLE_FIELDS)
    elif role_type in ('gov', 'lt_gov'):
        return validate_obj(role, EXECUTIVE_ROLE_FIELDS)
    else:
        return ['invalid type']


def is_valid_parent(parent):
    return parent in ('upper', 'lower', 'legislature')


ORGANIZATION_FIELDS = {
    'id': [is_ocd_organization, Required],
    'name': [is_string, Required],
    'jurisdiction': [is_ocd_jurisdiction, Required],
    'parent': [is_valid_parent, Required],
    'classification': [is_string, Required],    # TODO: tighten this
    'founding_date': [is_fuzzy_date],
    'dissolution_date': [is_fuzzy_date],
    'memberships': NestedList({
        'id': [is_ocd_person],
        'name': [is_string, Required],
        'role': [is_string],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'sources': URL_LIST,
    'links': URL_LIST,
}

PERSON_FIELDS = {
    'id': [is_ocd_person, Required],
    'name': [is_string, Required],
    'sort_name': [is_string],
    'given_name': [is_string],
    'family_name': [is_string],
    'gender': [is_string],
    'summary': [is_string],
    'biography': [is_string],
    'birth_date': [is_fuzzy_date],
    'death_date': [is_fuzzy_date],
    'image': [is_url],
    'contact_details': CONTACT_DETAILS,
    'links': URL_LIST,
    'ids': {
        'twitter': [is_social],
        'youtube': [is_social],
        'instagram': [is_social],
        'facebook': [is_social],
        'legacy_openstates': [is_legacy_openstates],
    },
    'other_identifiers': NestedList({
        'identifier': [is_string, Required],
        'scheme': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'other_names': NestedList({
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'sources': URL_LIST,
    'party': NestedList({
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'roles': NestedList(is_role),
    'extras': [is_dict],
}


def validate_obj(obj, schema, prefix=None):
    errors = []

    if prefix:
        prefix_str = '.'.join(prefix) + '.'
    else:
        prefix_str = ''

    for field, validators in schema.items():
        value = obj.get(field, Missing)

        if value is Missing:
            if isinstance(validators, list) and Required in validators:
                errors.append(f'{prefix_str}{field} missing')
            # error or not, don't run other validators against missing fields
            continue

        if isinstance(validators, list):
            for validator in validators:
                # required is checked above
                if validator is Required:
                    continue
                if not validator(value):
                    errors.append(
                        f'{prefix_str}{field} failed validation {validator.__name__}: {value}'
                    )
        elif isinstance(validators, dict):
            errors.extend(validate_obj(value, validators, [field]))
        elif isinstance(validators, NestedList):
            if isinstance(validators.subschema, dict):
                # validate list elements against child schema
                for index, item in enumerate(value):
                    errors.extend(validate_obj(item, validators.subschema, [field, str(index)]))
            else:
                # subschema can also be a validation function
                for index, item in enumerate(value):
                    errors.extend(['.'.join([field, str(index)]) + ': ' + e
                                   for e in validators.subschema(item)])
        else:
            raise Exception('invalid schema {}'.format(validators))

    # check for extra items that went without validation
    for key in set(obj.keys()) - set(schema.keys()):
        errors.append(f'extra key: {prefix_str}{key}')

    return errors


def validate_roles(person, roles_key, retired=False):
    active = [role for role in person[roles_key] if role_is_active(role)]
    if len(active) == 0 and not retired:
        return [f'no active {roles_key}']
    elif roles_key == 'roles' and retired and len(active) > 0:
        return [f'{len(active)} active roles on retired person']
    elif roles_key == 'roles' and len(active) > 1:
        return [f'{len(active)} active roles']
    return []


def get_expected_districts(settings):
    expected = {}
    for key in ('upper', 'lower', 'legislature'):
        seats = settings.get(key + '_seats')
        if not seats:
            continue
        elif isinstance(seats, int):
            # one seat per district by default
            expected[key] = {str(s): 1 for s in range(1, seats+1)}
        elif isinstance(seats, list):
            expected[key] = {s: 1 for s in seats}
        elif isinstance(seats, dict):
            expected[key] = seats
        else:
            raise ValueError(seats)
    return expected


def compare_districts(expected, actual):
    errors = []
    warnings = []

    if expected.keys() != actual.keys():
        errors.append(f'expected districts for {expected.keys()}, got {actual.keys()}')
        return errors, warnings

    for chamber in expected:
        expected_districts = set(expected[chamber].keys())
        actual_districts = set(actual[chamber].keys())
        for district in sorted(expected_districts - actual_districts):
            warnings.append(f'missing legislator for {chamber} {district}')
        for district in sorted(actual_districts - expected_districts):
            errors.append(f'extra legislator for unexpected seat {chamber} {district}')
        for district in sorted(actual_districts & expected_districts):
            if len(actual[chamber][district]) < expected[chamber][district]:
                warnings.append(f'missing legislator for {chamber} {district}')
            if len(actual[chamber][district]) > expected[chamber][district]:
                people = '\n\t'.join(get_filename(o) for o in actual[chamber][district])
                errors.append(f'extra legislator for {chamber} {district}:\n\t' + people)
    return errors, warnings


class Validator:
    OPTIONAL_FIELD_SET = set(('sort_name', 'given_name', 'family_name',
                              'gender', 'summary', 'biography',
                              'birth_date', 'death_date', 'image',
                              'links', 'other_names', 'sources',
                              ))

    def __init__(self, settings, abbr):
        self.http_whitelist = tuple(settings.get('http_whitelist', []))
        self.expected = get_expected_districts(settings[abbr])
        self.errors = defaultdict(list)
        self.warnings = defaultdict(list)
        self.person_count = 0
        self.retired_count = 0
        self.org_count = 0
        self.missing_person_id = 0
        self.role_types = defaultdict(int)
        self.parent_types = defaultdict(int)
        self.person_mapping = {}
        self.parties = Counter()
        self.contact_counts = Counter()
        self.id_counts = Counter()
        self.optional_fields = Counter()
        self.extra_counts = Counter()
        self.active_legislators = defaultdict(lambda: defaultdict(list))

    def validate_person(self, person, filename, retired=False):
        self.errors[filename] = validate_obj(person, PERSON_FIELDS)
        self.errors[filename].extend(validate_roles(person, 'roles', retired))
        self.errors[filename].extend(validate_roles(person, 'party'))
        # TODO: this was too ambitious, disabling this for now
        # self.warnings[filename] = self.check_https(person)
        self.person_mapping[person['id']] = person['name']
        if retired:
            self.retired_count += 1
        else:
            self.summarize_person(person)

    def validate_org(self, org, filename):
        self.errors[filename] = validate_obj(org, ORGANIZATION_FIELDS)
        for m in org['memberships']:
            if not m.get('id'):
                continue
            if m['id'] not in self.person_mapping:
                self.errors[filename].append(f'invalid person ID {m["id"]}')
            elif self.person_mapping[m['id']] != m['name']:
                name = self.person_mapping[m['id']]
                self.warnings[filename].append(f'ID {m["id"]} refers to {name}, not {m["name"]}')
        self.summarize_org(org)

    def check_https_url(self, url):
        if url and url.startswith('http://') and not url.startswith(self.http_whitelist):
            return False
        return True

    def check_https(self, person):
        warnings = []
        if not self.check_https_url(person.get('image')):
            warnings.append(f'image URL {person["image"]} should be HTTPS')
        for i, url in enumerate(person.get('links', [])):
            url = url['url']
            if not self.check_https_url(url):
                warnings.append(f'links.{i} URL {url} should be HTTPS')
        for i, url in enumerate(person.get('sources', [])):
            url = url['url']
            if not self.check_https_url(url):
                warnings.append(f'sources.{i} URL {url} should be HTTPS')
        return warnings

    def summarize_person(self, person):
        role_type = None
        district = None

        self.person_count += 1
        self.optional_fields.update(set(person.keys()) & self.OPTIONAL_FIELD_SET)
        self.extra_counts.update(person.get('extras', {}).keys())

        for role in person.get('roles', []):
            if role_is_active(role):
                role_type = role['type']
                district = role.get('district')
                break
        self.active_legislators[role_type][district].append(person)

        for role in person.get('party', []):
            if role_is_active(role):
                self.parties[role['name']] += 1

        for cd in person.get('contact_details', []):
            for key in cd:
                if key != 'note':
                    self.contact_counts[key] += 1

        for scheme in person.get('ids', {}):
            self.id_counts[scheme] += 1
        for id in person.get('other_identifiers', []):
            self.id_counts[id['scheme']] += 1

    def summarize_org(self, org):
        self.org_count += 1

        if org['parent'].startswith('ocd-organization'):
            self.parent_types['subcommittee'] += 1
        else:
            self.parent_types[org['parent']] += 1

        for m in org['memberships']:
            if not m.get('id'):
                self.missing_person_id += 1
            if role_is_active(m):
                self.role_types[m.get('role', 'member')] += 1

    def print_validation_report(self, verbose):
        for fn, errors in self.errors.items():
            warnings = self.warnings[fn]
            if errors or warnings:
                click.echo(fn)
                for err in errors:
                    click.secho(' ' + err, fg='red')
                for warning in warnings:
                    click.secho(' ' + warning, fg='yellow')
            if not errors and verbose > 0:
                click.secho(fn, 'OK!', fg='green')

        errors, warnings = compare_districts(self.expected, self.active_legislators)
        for err in errors:
            click.secho(err, fg='red')
        for warning in warnings:
            click.secho(warning, fg='yellow')

    def print_summary(self):
        click.secho(f'processed {self.person_count} active people, {self.retired_count} retired & '
                    f'{self.org_count} organizations', bold=True)
        for role_type in self.active_legislators:
            count = sum([len(v) for v in self.active_legislators[role_type].values()])
            click.secho(f'{count:4d} {role_type}')

        click.secho('Parties', bold=True)
        for party, count in self.parties.items():
            if party == 'Republican':
                color = 'red'
            elif party == 'Democratic':
                color = 'blue'
            else:
                color = 'green'
            click.secho(f'{count:4d} {party} ', bg=color)

        for name, collection in {'Contact Info': self.contact_counts,
                                 'Identifiers': self.id_counts,
                                 'Additional Info': self.optional_fields,
                                 'Extras': self.extra_counts}.items():
            if collection:
                click.secho(name, bold=True)
                for type, count in collection.items():
                    click.secho(f'{count:4d} {type} ')
            else:
                click.secho(name + ' - none', bold=True)

        click.secho('Committees', bold=True)
        for parent, count in self.parent_types.items():
            click.secho(f'{count:4d} {parent}')
        click.secho('{:4d} roles missing ID'.format(self.missing_person_id))
        for role, count in self.role_types.items():
            click.secho(f'{count:4d} {role} roles')


def process_dir(abbr, verbose, summary, settings):
    person_filenames = glob.glob(os.path.join(get_data_dir(abbr), 'people', '*.yml'))
    retired_filenames = glob.glob(os.path.join(get_data_dir(abbr), 'retired', '*.yml'))
    org_filenames = glob.glob(os.path.join(get_data_dir(abbr), 'organizations', '*.yml'))
    validator = Validator(settings, abbr)

    for filename in person_filenames:
        print_filename = os.path.basename(filename)
        with open(filename) as f:
            person = yaml.load(f)
            validator.validate_person(person, print_filename)

    for filename in retired_filenames:
        print_filename = os.path.basename(filename)
        with open(filename) as f:
            person = yaml.load(f)
            validator.validate_person(person, print_filename, retired=True)

    for filename in org_filenames:
        print_filename = os.path.basename(filename)
        with open(filename) as f:
            org = yaml.load(f)
            validator.validate_org(org, print_filename)

    validator.print_validation_report(verbose)

    if summary:
        validator.print_summary()


@click.command()
@click.argument('abbr', default='*')
@click.option('-v', '--verbose', count=True)
@click.option('--summary/--no-summary', default=False)
def lint(abbr, verbose, summary):
    settings_file = os.path.join(os.path.dirname(__file__), '../settings.yml')
    with open(settings_file) as f:
        settings = yaml.load(f)

    if abbr == '*':
        all = [k for k in settings.keys() if k != 'http_whitelist' and k in os.listdir('test')]
        for abbr in all:
            click.secho('==== {} ===='.format(abbr), bold=True)
            process_dir(abbr, verbose, summary, settings)
    else:
        process_dir(abbr, verbose, summary, settings)


if __name__ == '__main__':
    lint()
