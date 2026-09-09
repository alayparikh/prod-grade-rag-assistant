"""ACL-mapping tests.

Built on real SMB2CreateSDBuffer objects rather than hand-rolled fakes, so
the parsing agrees with the structures the NAS will actually send. What is
*not* covered here is whether a given NAS answers a security-descriptor
query at all - that is a property of the device and needs the on-site
spike.

Errors in this layer are recall bugs, not leaks: stage 2 re-checks every
file as the asking user before generation. The tests still assert the
safe direction, because a pre-filter that over-grants makes stage 2 the
only thing standing between a user and someone else's payroll.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer import acl  # noqa: E402
from smbprotocol.security_descriptor import (  # noqa: E402
    AccessAllowedAce,
    AccessDeniedAce,
    AclPacket,
    SIDPacket,
    SMB2CreateSDBuffer,
)


def sid(text):
    packet = SIDPacket()
    packet.from_string(text)
    return packet


def descriptor(*aces):
    dacl = AclPacket()
    dacl["aces"] = list(aces)
    sd = SMB2CreateSDBuffer()
    sd.set_dacl(dacl)
    return sd


def allow(sid_text, mask=acl.FILE_READ_DATA):
    ace = AccessAllowedAce()
    ace["mask"] = mask
    ace["sid"] = sid(sid_text)
    return ace


def deny(sid_text, mask=acl.FILE_READ_DATA):
    ace = AccessDeniedAce()
    ace["mask"] = mask
    ace["sid"] = sid(sid_text)
    return ace


HR = "S-1-5-21-1111-2222-3333-1001"
ENG = "S-1-5-21-1111-2222-3333-1002"
ALICE = "S-1-5-21-1111-2222-3333-500"


class TestGroupsFromDescriptor:
    def test_reads_allowed_principals(self):
        groups = acl.groups_from_descriptor(descriptor(allow(HR), allow(ENG)))
        assert groups == [acl.sanitize_group(HR), acl.sanitize_group(ENG)]

    def test_deny_beats_allow(self):
        # Windows evaluates deny first; a principal both allowed and denied
        # must not be tagged.
        groups = acl.groups_from_descriptor(descriptor(allow(HR), deny(HR)))
        assert groups == []

    def test_deny_for_one_principal_leaves_others(self):
        groups = acl.groups_from_descriptor(
            descriptor(allow(HR), allow(ENG), deny(ENG)))
        assert groups == [acl.sanitize_group(HR)]

    def test_ignores_aces_that_do_not_grant_read(self):
        FILE_WRITE_DATA = 0x00000002
        assert acl.groups_from_descriptor(descriptor(allow(HR, FILE_WRITE_DATA))) == []

    def test_attribute_only_access_is_not_read_access(self):
        # Seeing that a file exists is a different permission from reading
        # it, and conflating them would tag chunks as readable by people
        # who can only list the folder.
        FILE_READ_ATTRIBUTES = 0x00000080
        assert acl.groups_from_descriptor(
            descriptor(allow(HR, FILE_READ_ATTRIBUTES))) == []

    def test_generic_read_counts(self):
        assert acl.groups_from_descriptor(descriptor(allow(HR, acl.GENERIC_READ)))

    def test_full_control_counts(self):
        assert acl.groups_from_descriptor(descriptor(allow(HR, acl.FILE_ALL_ACCESS)))

    def test_drops_well_known_everyone_sids(self):
        # "Everyone" tags say nothing and would be written onto every chunk.
        groups = acl.groups_from_descriptor(descriptor(allow("S-1-1-0"), allow(HR)))
        assert groups == [acl.sanitize_group(HR)]

    def test_deduplicates(self):
        groups = acl.groups_from_descriptor(descriptor(allow(HR), allow(HR)))
        assert groups == [acl.sanitize_group(HR)]

    def test_missing_dacl_means_no_opinion_not_everyone(self):
        # A descriptor with no DACL must not be read as a grant.
        assert acl.groups_from_descriptor(SMB2CreateSDBuffer()) == []

    def test_empty_dacl_grants_nothing(self):
        assert acl.groups_from_descriptor(descriptor()) == []


class TestSanitizeGroup:
    def test_makes_a_sid_key_safe(self):
        assert acl.sanitize_group(HR) == "S_1_5_21_1111_2222_3333_1001"

    def test_distinct_sids_stay_distinct(self):
        # A collision here would merge two groups' access into one tag.
        assert acl.sanitize_group(HR) != acl.sanitize_group(ENG)

    def test_handles_domain_qualified_names(self):
        assert acl.sanitize_group("COMPANY\\HR Team") == "COMPANY_HR_Team"

    def test_never_returns_an_empty_key(self):
        assert acl.sanitize_group("---") == "unknown"


class TestGrantsRead:
    @pytest.mark.parametrize("mask", [acl.FILE_READ_DATA, acl.GENERIC_READ,
                                      acl.GENERIC_ALL, acl.FILE_ALL_ACCESS])
    def test_read_masks(self, mask):
        assert acl.grants_read(mask)

    @pytest.mark.parametrize("mask", [0x00000002, 0x00000080, 0x00000000])
    def test_non_read_masks(self, mask):
        assert not acl.grants_read(mask)


class TestFeatureGate:
    def test_off_by_default(self, monkeypatch):
        # Stage 1 requires two NAS properties that must be confirmed on
        # site; until then stage 2 alone is the correct configuration.
        monkeypatch.delenv("RAG_ACL_TAGGING", raising=False)
        assert acl.acl_enabled() is False

    def test_enabled_explicitly(self, monkeypatch):
        monkeypatch.setenv("RAG_ACL_TAGGING", "1")
        assert acl.acl_enabled() is True


class TestGroupsForUser:
    def test_no_ldap_configured_means_no_prefilter(self, monkeypatch):
        # None means "cannot pre-filter", which the caller must not confuse
        # with "belongs to no groups" - that would deny everything.
        monkeypatch.delenv("RAG_LDAP_URL", raising=False)
        monkeypatch.delenv("RAG_LDAP_BASE_DN", raising=False)
        assert acl.groups_for_user("alice") is None

    def test_unreachable_directory_means_no_prefilter(self, monkeypatch):
        monkeypatch.setenv("RAG_LDAP_URL", "ldap://127.0.0.1:1")
        monkeypatch.setenv("RAG_LDAP_BASE_DN", "dc=example,dc=com")
        assert acl.groups_for_user("alice") is None
