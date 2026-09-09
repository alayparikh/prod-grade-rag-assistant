"""Stage 1 of authorization: index-time ACL tagging.

Reads each folder's SMB security descriptor as the indexer service
account and turns the allow-ACEs that grant read access into the
`group_*` chunk metadata the Chroma filter already understands. This is a
pre-filter and a snapshot, never the decision: `auth.smb` re-checks every
candidate file as the asking user before generation, and that check is
what actually protects the data.

Two things must hold before this layer is worth enabling, and both are
properties of the specific NAS rather than of this code:

  1. The NAS returns a DACL over SMB. Query support varies by vendor.
  2. The user's own group membership can be resolved at query time -
     an SMB session establishes identity, not membership. That needs
     LDAP (RAG_LDAP_URL) or an equivalent.

If either fails, leave this off. Stage 2 alone is correct; it is only
slower for users who can see very little, because retrieval then has to
over-fetch and discard.
"""
import os
import re

# Read access in the sense that matters here: the right to open and read a
# file's contents. FILE_READ_DATA is the bit that governs it; an ACE that
# only grants FILE_READ_ATTRIBUTES lets someone see that a file exists,
# which is not the same permission and must not be treated as one.
FILE_READ_DATA = 0x00000001
GENERIC_READ = 0x80000000
GENERIC_ALL = 0x10000000
FILE_ALL_ACCESS = 0x001F01FF

ACCESS_ALLOWED_ACE_TYPE = 0x00
ACCESS_DENIED_ACE_TYPE = 0x01

# Well-known SIDs that carry no useful filtering signal: every user is in
# them, so tagging chunks with them says nothing while inflating the
# metadata on every chunk.
UNINTERESTING_SIDS = {
    "S-1-1-0",       # Everyone
    "S-1-5-11",      # Authenticated Users
    "S-1-5-32-544",  # BUILTIN\Administrators
    "S-1-5-18",      # SYSTEM
    "S-1-3-0",       # Creator Owner
}

_UNSAFE = re.compile(r"[^A-Za-z0-9_]+")


# Chroma metadata keys are used as "group_<name>", so a raw SID or a
# domain-qualified name has to be flattened to something key-safe. The
# mapping must be stable and collision-free enough that two different
# principals never land on the same tag.
def sanitize_group(name):
    cleaned = _UNSAFE.sub("_", str(name)).strip("_")
    return cleaned or "unknown"


def grants_read(mask):
    return bool(mask & (FILE_READ_DATA | GENERIC_READ | GENERIC_ALL)
                or (mask & FILE_ALL_ACCESS) == FILE_ALL_ACCESS)


# Turn an unpacked security descriptor into the group tags for a folder.
#
# Deny ACEs win over allow ACEs, matching Windows evaluation order. This
# is a simplification of the real algorithm - it ignores ACE ordering and
# inheritance flags - which is acceptable only because it can just be
# wrong in the safe direction: a principal wrongly excluded here loses
# recall, and one wrongly included is still stopped by the per-file check
# at query time.
def groups_from_descriptor(descriptor):
    dacl = descriptor.get_dacl()
    if dacl is None:
        return []  # no DACL means "no opinion", not "everyone"

    allowed, denied = [], set()
    for ace in dacl["aces"].get_value():
        sid = str(ace["sid"])
        ace_type = ace["ace_type"].get_value()
        mask = ace["mask"].get_value()

        if not grants_read(mask):
            continue
        if ace_type == ACCESS_DENIED_ACE_TYPE:
            denied.add(sid)
        elif ace_type == ACCESS_ALLOWED_ACE_TYPE and sid not in UNINTERESTING_SIDS:
            allowed.append(sid)

    seen, groups = set(), []
    for sid in allowed:
        if sid in denied or sid in seen:
            continue
        seen.add(sid)
        groups.append(sanitize_group(sid))
    return groups


# The wire call. This is the part that must be confirmed against the real
# NAS before stage 1 is enabled - support for querying a security
# descriptor over SMB varies by vendor, and a NAS that refuses it makes
# this whole layer unavailable rather than merely slow.
def read_descriptor(tree, share_path):
    from smbprotocol.exceptions import SMBException, SMBResponseException
    from smbprotocol.open import (
        CreateDisposition,
        CreateOptions,
        FileAttributes,
        FilePipePrinterAccessMask,
        ImpersonationLevel,
        InfoType,
        Open,
        ShareAccess,
        SMB2QueryInfoRequest,
        SMB2QueryInfoResponse,
    )
    from smbprotocol.security_descriptor import SMB2CreateSDBuffer

    OWNER_SECURITY_INFORMATION = 0x00000001
    GROUP_SECURITY_INFORMATION = 0x00000002
    DACL_SECURITY_INFORMATION = 0x00000004

    handle = Open(tree, share_path)
    try:
        handle.create(
            ImpersonationLevel.Impersonation,
            FilePipePrinterAccessMask.READ_CONTROL,
            FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
            CreateDisposition.FILE_OPEN,
            CreateOptions.FILE_DIRECTORY_FILE,
        )
    except (SMBResponseException, SMBException, OSError):
        return None  # cannot even open it to ask: no opinion

    try:
        request = SMB2QueryInfoRequest()
        request["info_type"] = InfoType.SMB2_0_INFO_SECURITY
        request["output_buffer_length"] = 65535
        request["additional_information"] = (
            OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION
            | DACL_SECURITY_INFORMATION
        )
        request["file_id"] = handle.file_id

        request_id = handle.connection.send(request, sid=handle.tree_connect.session
                                            .session_id, tid=handle.tree_connect.tree_connect_id)
        response = handle.connection.receive(request_id)

        query_response = SMB2QueryInfoResponse()
        query_response.unpack(response["data"].get_value())

        descriptor = SMB2CreateSDBuffer()
        descriptor.unpack(query_response["buffer"].get_value())
        return descriptor
    except (SMBResponseException, SMBException, OSError, ValueError):
        return None
    finally:
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass


def acl_enabled():
    return os.environ.get("RAG_ACL_TAGGING", "0") == "1"


# Group membership for the logged-in user, needed to make stage 1 usable:
# an SMB session proves who someone is, not which groups they are in.
# Returns None when it cannot be determined, which the caller must treat
# as "no pre-filter", never as "no groups".
def groups_for_user(username, ldap_url=None, base_dn=None):
    ldap_url = ldap_url or os.environ.get("RAG_LDAP_URL")
    base_dn = base_dn or os.environ.get("RAG_LDAP_BASE_DN")
    if not ldap_url or not base_dn:
        return None

    try:
        import ldap3
    except ImportError:
        return None

    try:
        server = ldap3.Server(ldap_url, get_info=ldap3.NONE)
        connection = ldap3.Connection(server, authentication=ldap3.ANONYMOUS,
                                      auto_bind=True)
        connection.search(
            base_dn,
            f"(sAMAccountName={ldap3.utils.conv.escape_filter_chars(username)})",
            attributes=["objectSid", "tokenGroups"],
        )
        if not connection.entries:
            return None
        entry = connection.entries[0]
        sids = [str(entry.objectSid)] if "objectSid" in entry else []
        sids += [str(v) for v in entry.tokenGroups.values] if "tokenGroups" in entry else []
        return [sanitize_group(s) for s in sids] or None
    except Exception:  # noqa: BLE001 - unresolvable membership means no pre-filter
        return None
