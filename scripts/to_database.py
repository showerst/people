#!/usr/bin/env python
import os
import glob
import yaml
import django
from django import conf
from django.db import transaction
import click
from utils import get_data_dir, get_jurisdiction_id


class CancelTransaction(Exception):
    pass


def update_subobjects(person, fieldname, objects, read_manager=None):
    """ returns True if there are any updates """
    # we need the default manager for this field in case we need to do updates
    manager = getattr(person, fieldname)

    # if a read_manager is passed, we'll use that for all read operations
    # this is used for Person.memberships to ensure we don't wipe out committee memberships
    if read_manager is None:
        read_manager = manager

    current_count = read_manager.count()
    updated = False

    # if counts differ, we need to do an update for sure
    if current_count != len(objects):
        updated = True

    # check if all objects exist
    for obj in objects:
        if updated:
            break
        if read_manager.filter(**obj).count() != 1:
            updated = True

    # if there's been an update, wipe the old & insert the new
    if updated:
        if current_count:
            read_manager.all().delete()
        for obj in objects:
            manager.create(**obj)
        # save to bump updated_at timestamp
        person.save()

    return updated


def get_update_or_create(ModelCls, data):
    updated = created = False
    try:
        obj = ModelCls.objects.get(pk=data['id'])
        for field, value in data.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                updated = True
        if updated:
            obj.save()
    except ModelCls.DoesNotExist:
        obj = ModelCls.objects.create(**data)
        created = True
    return obj, created, updated


def load_person(data):
    # import has to be here so that Django is set up
    from opencivicdata.core.models import Person, Organization, Post

    fields = dict(id=data['id'],
                  name=data['name'],
                  given_name=data.get('given_name', ''),
                  family_name=data.get('family_name', ''),
                  gender=data.get('gender', ''),
                  biography=data.get('biography', ''),
                  birth_date=data.get('birth_date', ''),
                  death_date=data.get('death_date', ''),
                  image=data.get('image', ''),
                  extras=data.get('extras', {}),
                  )
    person, created, updated = get_update_or_create(Person, fields)

    updated |= update_subobjects(person, 'other_names', data.get('other_names', []))
    updated |= update_subobjects(person, 'links', data.get('links', []))
    updated |= update_subobjects(person, 'sources', data.get('sources', []))

    identifiers = []
    for scheme, value in data.get('ids', {}).items():
        identifiers.append({'scheme': scheme, 'identifier': value})
    for identifier in data.get('other_identifiers', []):
        identifiers.append(identifier)
    updated |= update_subobjects(person, 'identifiers', identifiers)

    contact_details = []
    for cd in data.get('contact_details', []):
        for type in ('address', 'email', 'voice', 'fax'):
            if cd.get(type):
                contact_details.append({'note': cd.get('note', ''),
                                        'type': type,
                                        'value': cd[type]})
    updated |= update_subobjects(person, 'contact_details', contact_details)

    memberships = []
    for party in data.get('party', []):
        try:
            org = Organization.objects.get(classification='party', name=party['name'])
        except Organization.DoesNotExist:
            click.secho(f"no such party {party['name']}", fg='red')
            raise
        memberships.append({'organization': org,
                            'start_date': party.get('start_date', ''),
                            'end_date': party.get('end_date', '')})
    for role in data.get('roles', []):
        if role['type'] in ('upper', 'lower', 'legislature'):
            try:
                org = Organization.objects.get(classification=role['type'],
                                               jurisdiction_id=role['jurisdiction'])
                post = org.posts.get(label=role['district'])
            except Organization.DoesNotExist:
                click.secho(f"no such organization {role['jurisdiction']} {role['type']}",
                            fg='red')
                raise CancelTransaction()
            except Post.DoesNotExist:
                click.secho(f"no such post {role}", fg='red')
                raise CancelTransaction()
        else:
            raise ValueError('unsupported role type')
        memberships.append({'organization': org,
                            'post': post,
                            'start_date': role.get('start_date', ''),
                            'end_date': role.get('end_date', '')})

    # note that we don't manager committee memberships here
    updated |= update_subobjects(
        person, 'memberships', memberships,
        read_manager=person.memberships.exclude(organization__classification='committee')
    )

    return created, updated


def load_org(data):
    from opencivicdata.core.models import Organization, Person

    parent_id = data['parent']
    if parent_id.startswith('ocd-organization'):
        parent = Organization.objects.get(pk=parent_id)
    else:
        parent = Organization.objects.get(jurisdiction_id=data['jurisdiction'],
                                          classification=parent_id)

    fields = dict(
        id=data['id'],
        name=data['name'],
        jurisdiction_id=data['jurisdiction'],
        classification=data['classification'],
        founding_date=data.get('founding_date', ''),
        dissolution_date=data.get('dissolution_date', ''),
        parent=parent,
    )
    org, created, updated = get_update_or_create(Organization, fields)

    updated |= update_subobjects(org, 'links', data.get('links', []))
    updated |= update_subobjects(org, 'sources', data.get('sources', []))

    memberships = []
    for role in data.get('memberships', []):
        if role.get('id'):
            try:
                person = Person.objects.get(pk=role['id'])
            except Person.DoesNotExist:
                click.secho(f"no such person {role['id']}", fg='red')
                raise CancelTransaction()
        else:
            person = None

        memberships.append({'person': person,
                            'person_name': role['name'],
                            'role': role.get('role', 'member'),
                            'start_date': role.get('start_date', ''),
                            'end_date': role.get('end_date', '')})
    updated |= update_subobjects(org, 'memberships', memberships)

    return created, updated


def load_directory(files, type, jurisdiction_id, purge):
    ids = set()
    created_count = 0
    updated_count = 0

    if type == 'person':
        from opencivicdata.core.models import Person
        existing_ids = set(Person.objects.filter(
            memberships__organization__jurisdiction_id=jurisdiction_id
        ).values_list('id', flat=True))
        ModelCls = Person
        load_func = load_person
    elif type == 'organization':
        from opencivicdata.core.models import Organization
        existing_ids = set(Organization.objects.filter(
            jurisdiction_id=jurisdiction_id,
            classification='committee',
        ).values_list('id', flat=True))
        ModelCls = Organization
        load_func = load_org
    else:
        raise ValueError(type)

    for filename in files:
        with open(filename) as f:
            data = yaml.load(f)
            ids.add(data['id'])
            created, updated = load_func(data)

        if created:
            click.secho(f'created {type} from {filename}', fg='cyan', bold=True)
        elif updated:
            click.secho(f'updated {type} from {filename}', fg='cyan')

    missing_ids = existing_ids - ids
    if missing_ids and not purge:
        click.secho(f'{len(missing_ids)} went missing, run with --purge to remove',
                    fg='red')
        for id in missing_ids:
            click.secho(f'  {id}')
        raise CancelTransaction()
    elif missing_ids and purge:
        click.secho(f'{len(missing_ids)} purged', fg='yellow')
        ModelCls.objects.filter(id__in=missing_ids).delete()

    # TODO: check new_ids?
    # new_ids = ids - existing_ids
    click.secho(f'processed {len(ids)} {type} files, {created_count} created, '
                f'{updated_count} updated', fg='green')


def init_django():
    conf.settings.configure(
        conf.global_settings,
        SECRET_KEY='not-important',
        DEBUG=False,
        INSTALLED_APPS=(
             'django.contrib.contenttypes',
             'opencivicdata.core.apps.BaseConfig',
        ),
        DATABASES={
            'default': {
                'ENGINE': 'django.contrib.gis.db.backends.postgis',
                'NAME': os.environ['OCD_DATABASE_NAME'],
                'USER': os.environ['OCD_DATABASE_USER'],
                'PASSWORD': os.environ['OCD_DATABASE_PASSWORD'],
                'HOST': 'localhost',
            }
        },
        MIDDLEWARE_CLASSES=(),
    )
    django.setup()


@click.command()
@click.argument('abbr', default='*')
@click.option('-v', '--verbose', count=True)
@click.option('--summary/--no-summary', default=False)
@click.option('--purge/--no-purge', default=False)
@click.option('--safe/--no-safe', default=False)
def to_database(abbr, verbose, summary, purge, safe):
    init_django()
    directory = get_data_dir(abbr)
    jurisdiction_id = get_jurisdiction_id(abbr)

    person_files = (glob.glob(os.path.join(directory, 'people/*.yml')) +
                    glob.glob(os.path.join(directory, 'retired/*.yml')))
    committee_files = glob.glob(os.path.join(directory, 'organizations/*.yml'))

    if safe:
        click.secho('running in safe mode, no changes will be made', fg='magenta')

    try:
        with transaction.atomic():
            load_directory(person_files, 'person', jurisdiction_id, purge=purge)
            load_directory(committee_files, 'organization', jurisdiction_id, purge=purge)
            if safe:
                click.secho('ran in safe mode, no changes were made', fg='magenta')
                raise CancelTransaction()
    except CancelTransaction:
        pass


if __name__ == '__main__':
    to_database()
