# Person Schema

* id: UUID representing this person for this data set.  **required**
* name: Full Name.  **required**
* given_name: First name.
* family_name: Last name.
* gender: Male/Female/Other
* biography: Official biography text.
* birth_date: Birth date in YYYY-MM-DD format.
* death_date: Death date in YYYY-MM-DD format.
* image: URL to official photo.
* ids:  nested dictionary of additional ids
    * twitter: username of official Twitter account
    * youtube: username of official YouTube account
    * instagram: username of official Instagram account
    * facebook: username of official Facebook account
    * legacy_openstates: legacy Open States ID (e.g. NCL000123)
* party: list of parties that the legislator has been a part of, each may have the following fields:
    * name: Name of the party.    **required**
    * start_date
    * end_date
* roles: list of legislative & executive roles held by this individual, each may have the following fields:
    * type: upper|lower|legislature|gov|lt_gov    **required**
    * district: name/number of district   **required if not gov/lt_gov**
    * jurisdiction: ocd-jurisdiction identifier **required**
    * start_date
    * end_date
    * contact_details: role-specific contact details (see below for schema)
* contact_details (see below)
* links (see below)
* other_identifiers (see below)
* other_names (see below)
* sources (see below)

# Organization Fields

* id: UUID representing this organization.  **required**
* name: Name of Organization.  **required**
* jurisdiction: ocd-jurisdiction identifier **required**
* parent: Parent of this organization, can be:
    * upper
    * lower
    * legislature
    * ID of a parent committee in the case of subcommittee
    **required**
* classification: Classification, can be:
    * committee
    **required**
* founding_date: Creation date in YYYY-MM-DD format.
* dissolution_date: Dissolution date in YYYY-MM-DD format.
* memberships: list of memberships, each may have the following:
    * id - ocd-person ID if known
    * name - name of person **required**
    * role - role that person fills on committee, if not 'member'
    * start_date
    * end_date


### Common Elements

These sections can have a list of objects, each with the following fields available.

* contact_details: 
    * note: Description of what these details refer to (e.g. "District Office").  **required**
    * address: Mailing address.
    * email: Email address.
    * voice: Phone number used for voice calls.
    * fax: Fax number.

* links:
    * note: description of the purpose of this link
    * url: URL associated with legislator **required**

* other_identifiers:
    * scheme: origin of this identifier (e.g. "votesmart")        **required**
    * identifier: identifier used by the given service/scheme (e.g. 13823)    **required**
    * start_date: optional date identifier started being valid for this person
    * end_date: optional date identifier ceased to be valid for this person

* other_names:
    * name: alternate name that has been seen for this person **required**
    * start_date: optional date name started being valid for this person
    * end_date: optional date name ceased to be valid for this person

* sources:
    * note: description of the usage of this source
    * url: URL used to collect information for this person **required**


### Additional Fields

These fields should only be set by the automated processes, but may also be present.
* summary
* sort_name
* extras
