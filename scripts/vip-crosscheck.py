#!/usr/bin/env python

"""vip-crosscheck.py

Check a given state's members against google civic information api,
and look for possible mismatches.

VIP gets the election results straight from the state, so tends to update faster.

Args:
    state: two letter us state abbreviation
    key: Google Civic api key

TODO:
    Variants of this script that prompt to automatically add to aliases if the VIP
    entry is in fact our person, and script to merge social media into our person record
"""


import glob
import json
import os
import re
import sys
import uuid
import yaml
import yamlordereddictloader
import argparse
import urllib.parse
import requests
from collections import defaultdict, OrderedDict
from utils import reformat_phone_number, get_data_dir

parser = argparse.ArgumentParser()
parser.add_argument("state", help="Two letter state abbreviation")
parser.add_argument(
    "key", help="Google Civic API Key. See https://developers.google.com/civic-information/docs/v2/")

args = parser.parse_args()

args.state = args.state.lower()

dirname = "./test/{}/".format(args.state)
print(dirname)
people = []


# This is a temp function, don't re-use it
def parse_jurisdiction(state, chamber, district):
    if chamber == 'upper':
        jurisdiction_base = 'ocd-division/country:us/state:{}/sldu:{}'
    elif chamber == 'lower':
        jurisdiction_base = 'ocd-division/country:us/state:{}/sldl:{}'

    jurisdiction = jurisdiction_base.format(state, district)

    return jurisdiction


people = {}

# load the members into
# people["OCD ID"] = person
for filename in glob.glob(os.path.join(dirname, '*.yml')):
    with open(filename) as f:
        data = yaml.load(f, Loader=yamlordereddictloader.Loader)

        names = []
        # note, once we start populating the jurisdiction into roles,
        # use that key instead of building it,
        # since some states (NH) will break right now
        jurisdiction = parse_jurisdiction(args.state,
                                          data['roles'][0]['chamber'],
                                          data['roles'][0]['district'],
                                          )

        names.append(data['name'])
        if 'other_names' in data:
            for other_name in data['other_names']:
                # todo if name end_date > now or null
                names.append(other_name['name'])

        if jurisdiction in people:
            people[jurisdiction] = people[jurisdiction] + names
        else:
            people[jurisdiction] = names

# print(people)

url_pattern = 'https://www.googleapis.com/civicinfo/v2/representatives/{}?key={}'
for ocd, names in people.items():
    vip_officials = []

    url = url_pattern.format(
        urllib.parse.quote_plus(ocd),
        args.key,
    )
    resp = requests.get(url)
    vip = json.loads(resp.content)
    for role in vip['offices']:
        if 'legislatorLowerBody' in role['roles'] or 'legislatorUpperBody' in role['roles']:
            for index in role['officialIndices']:
                vip_officials.append(vip['officials'][index]['name'])

    # print("***")
    # print (vip_officials)
    # print("----")
    # print(people[ocd])

    for vip_name in vip_officials:
        if vip_name not in people[ocd]:
            print(
                'Mismatch with VIP: {} not found in {}. Our names are: {}'.format(
                    vip_name,
                    ocd,
                    ', '.join(people[ocd])
                )
            )

    # sys.exit()