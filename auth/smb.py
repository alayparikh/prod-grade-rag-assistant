"""NAS-backed authentication and per-file authorization over SMB.

The NAS is the only source of truth for who may see a file. This module
never keeps a user or group table: a login is an SMB session opened with
the user's own credentials, and an access check is an SMB open-for-read
of the specific file using that session. A file the NAS refuses to open
is a file the assistant must not show.

Configuration (env):
    RAG_NAS_HOST          NAS hostname/IP. Required unless RAG_AUTH_MODE=none.
    RAG_NAS_SHARE         Share name (default "shared").
    RAG_DOCS_PATH         Local mount of that share (default /mnt/nas). Used to
                          translate indexed local paths back to share-relative
                          SMB paths.
    RAG_NAS_PORT          Default 445.
    RAG_SESSION_IDLE_MIN  Idle minutes before a login expires (default 30).
    RAG_AUTH_MODE         "nas" (default) or "none" (local dev only: no login,
                          no access checks - never set this in production).
"""
import os
import time
import uuid

NAS_HOST = os.environ.get("RAG_NAS_HOST", "")
NAS_SHARE = os.environ.get("RAG_NAS_SHARE", "shared")
NAS_PORT = int(os.environ.get("RAG_NAS_PORT", 445))
NAS_MOUNT = os.environ.get("RAG_DOCS_PATH", "/mnt/nas")
SESSION_IDLE_SECONDS = int(os.environ.get("RAG_SESSION_IDLE_MIN", 30)) * 60
AUTH_MODE = os.environ.get("RAG_AUTH_MODE", "nas")
CONNECT_TIMEOUT_SECONDS = 10


class NasUnavailable(Exception):
    """The NAS could not be reached or refused the connection for a reason
    other than bad credentials. Callers show a "try again" message rather
    than "wrong password"."""


def auth_enabled():
    return AUTH_MODE != "none"


# Translate an indexed local path (under the read-only mount the indexer
# uses) into the share-relative, backslash-separated path SMB expects.
# "/mnt/nas/HR/roster.xlsx" -> "HR\\roster.xlsx". A path outside the mount is
# refused rather than guessed at: an access check on the wrong path would
# either fail closed (harmless) or, worse, succeed on some other file.
def to_share_path(local_path, mount=None):
    mount = os.path.abspath(mount or NAS_MOUNT)
    absolute = os.path.abspath(local_path)
    if absolute != mount and not absolute.startswith(mount + os.sep):
        raise ValueError(f"{local_path!r} is not under the NAS mount {mount!r}")
    relative = absolute[len(mount):].lstrip(os.sep)
    return relative.replace("/", "\\")


# Links the UI renders next to a citation. Windows Explorer wants a UNC
# path; macOS Finder and Linux file managers open smb:// URLs.
def nas_links(local_path, host=None, share=None, mount=None):
    host = host or NAS_HOST
    share = share or NAS_SHARE
    if not host:
        # No NAS configured (local development). Half-built links like
        # "\\\shared\file" look like a path and silently fail to open, so
        # callers are told to show the plain path instead.
        raise ValueError("no NAS host configured; cannot build a share link")
    share_path = to_share_path(local_path, mount)
    return {
        "unc": f"\\\\{host}\\{share}\\{share_path}",
        "smb": f"smb://{host}/{share}/{share_path.replace(chr(92), '/')}",
    }


class NasSession:
    """One logged-in user's SMB session. Holds the live connection objects
    and the last-used timestamp; never the password."""

    def __init__(self, username, connection, session, tree):
        self.username = username
        self._connection = connection
        self._session = session
        self._tree = tree
        self.created_at = time.time()
        self.last_used = self.created_at

    def touch(self):
        self.last_used = time.time()

    def expired(self, now=None):
        return (now or time.time()) - self.last_used > SESSION_IDLE_SECONDS

    # Authoritative per-file check: open the file for read as this user and
    # close it again. Anything other than a successful open is a denial -
    # including "not found", so a stale index entry cannot leak a path the
    # user can no longer reach.
    def can_read(self, local_path):
        try:
            share_path = to_share_path(local_path)
        except ValueError:
            return False
        try:
            return _open_for_read(self._tree, share_path)
        except NasUnavailable:
            return False

    def close(self):
        for obj in (self._tree, self._session, self._connection):
            try:
                obj.disconnect()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass


# Validate credentials by opening a real SMB session. Returns a NasSession
# on success, None on bad credentials, raises NasUnavailable when the NAS
# cannot be reached (so the UI can tell the two apart).
def login(username, password, host=None, share=None, port=None):
    host = host or NAS_HOST
    share = share or NAS_SHARE
    port = port or NAS_PORT
    if not host:
        raise NasUnavailable("RAG_NAS_HOST is not set")
    if not username or not password:
        return None

    from smbprotocol.connection import Connection
    from smbprotocol.exceptions import SMBAuthenticationError, SMBException
    from smbprotocol.header import NtStatus
    from smbprotocol.session import Session
    from smbprotocol.tree import TreeConnect

    connection = Connection(uuid.uuid4(), host, port)
    try:
        connection.connect(timeout=CONNECT_TIMEOUT_SECONDS)
    except (SMBException, OSError) as e:
        raise NasUnavailable(f"cannot reach {host}:{port}: {e}") from e

    session = Session(connection, username, password, require_encryption=False)
    try:
        session.connect()
    except SMBAuthenticationError:
        connection.disconnect()
        return None
    except (SMBException, OSError) as e:
        connection.disconnect()
        raise NasUnavailable(f"session setup failed: {e}") from e

    tree = TreeConnect(session, f"\\\\{host}\\{share}")
    try:
        tree.connect()
    except (SMBException, OSError) as e:
        session.disconnect()
        connection.disconnect()
        # A user who authenticates but is not allowed on the share has no
        # access to anything the assistant indexes - treat as login failure.
        if getattr(e, "status", None) == NtStatus.STATUS_ACCESS_DENIED:
            return None
        raise NasUnavailable(f"tree connect failed: {e}") from e

    return NasSession(username, connection, session, tree)


def _open_for_read(tree, share_path):
    from smbprotocol.exceptions import SMBException, SMBResponseException
    from smbprotocol.open import (
        CreateDisposition,
        CreateOptions,
        FileAttributes,
        FilePipePrinterAccessMask,
        ImpersonationLevel,
        Open,
        ShareAccess,
    )

    handle = Open(tree, share_path)
    try:
        handle.create(
            ImpersonationLevel.Impersonation,
            FilePipePrinterAccessMask.FILE_READ_DATA,
            FileAttributes.FILE_ATTRIBUTE_NORMAL,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
            CreateDisposition.FILE_OPEN,
            CreateOptions.FILE_NON_DIRECTORY_FILE,
        )
    except SMBResponseException:
        return False  # access denied, not found, sharing violation: all "no"
    except (SMBException, OSError) as e:
        raise NasUnavailable(str(e)) from e
    else:
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass
        return True


class AccessChecker:
    """Callable wrapper around NasSession.can_read with a per-question memo.
    Retrieval returns many chunks from the same few files, so one SMB open
    per distinct path per question is enough."""

    def __init__(self, session):
        self.session = session
        self._memo = {}
        self.checked = 0
        self.denied = 0

    def __call__(self, local_path):
        if local_path in self._memo:
            return self._memo[local_path]
        self.session.touch()
        allowed = bool(self.session.can_read(local_path))
        self._memo[local_path] = allowed
        self.checked += 1
        if not allowed:
            self.denied += 1
        return allowed
