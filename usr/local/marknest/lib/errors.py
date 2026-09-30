"""Typed exception hierarchy mapped onto the unified API response envelope.

Generic and transport failures take ``1000 + HTTP status``. Everything past
authentication belongs to the note domain and takes a ``3xxx`` code, numbered in
creation order and independent of the HTTP status - the same convention the
platform's other applications follow, so a code tells you which layer answered
without telling you what the status line already says.
"""


class MarkNestError(Exception):
    """Base class for every error that is safe to surface to the frontend."""

    status = 500
    code = 1000
    message = "internal error"

    def __init__(self, message=None, *, code=None, status=None, detail=None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.detail = detail
        super().__init__(self.message)

    def to_payload(self):
        payload = {"code": self.code, "message": self.message, "data": None}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class BadRequest(MarkNestError):
    status = 400
    code = 1400
    message = "invalid request"


class AuthRequired(MarkNestError):
    status = 401
    code = 1401
    message = "session expired, please sign in again"


class NotFound(MarkNestError):
    status = 404
    code = 1404
    message = "resource not found"


class MethodNotAllowed(MarkNestError):
    status = 405
    code = 1405
    message = "method not allowed"


class PayloadTooLarge(MarkNestError):
    status = 413
    code = 1413
    message = "uploaded file is too large"


class UnsupportedMedia(MarkNestError):
    status = 415
    code = 1415
    message = "unsupported file type"


# --------------------------------------------------------------------- domain


class LibraryUnavailable(MarkNestError):
    """The application's own shared folder is missing or unreadable.

    Every note lives in a shared folder the package creates for itself, so this
    means the installation did not finish - the folder was never created, or the
    volume it was created on is gone. Nothing the operator does inside the
    application can fix it, which is why the interface reports it as a whole-app
    condition rather than per-note.
    """

    status = 503
    code = 3001
    message = "the notes library is not available"


class LibraryNotWritable(MarkNestError):
    """The folder exists but writing to it was measured to fail.

    Read and write are separate bits in the platform's ACL, so a library can be
    perfectly readable and still refuse a save. This is raised from a measured
    probe, never from a mode bit.
    """

    status = 403
    code = 3002
    message = "the notes library is not writable"


class PathInvalid(MarkNestError):
    """The requested path is not inside the caller's own library.

    Raised for ``..`` traversal, for an absolute path elsewhere, for a symlink
    that resolves out of the library, and for a symlinked write target.
    """

    status = 400
    code = 3003
    message = "the path is outside your notes library"


class PathDenied(MarkNestError):
    status = 403
    code = 3004
    message = "the notes library refused access to that path"


class NoteNotFound(MarkNestError):
    status = 404
    code = 3005
    message = "the note does not exist"


class NoteExists(MarkNestError):
    status = 409
    code = 3006
    message = "a note already exists at that path"


class ConflictDetected(MarkNestError):
    """The note changed on disk since the client loaded it.

    ``detail`` carries the current revision and content so the interface can
    offer a real choice - overwrite, reload, or keep a copy - instead of
    silently losing whichever edit came second.
    """

    status = 409
    code = 3007
    message = "the note was changed by someone else"


class NoteTooLarge(MarkNestError):
    status = 413
    code = 3008
    message = "the note is too large"


class AttachmentRejected(MarkNestError):
    """The uploaded file's content does not match a type this app will store."""

    status = 415
    code = 3009
    message = "that file type is not accepted as an attachment"


class AttachmentNotFound(MarkNestError):
    status = 404
    code = 3010
    message = "the attachment does not exist"


class IndexUnavailable(MarkNestError):
    """The search index could not be opened or written.

    Distinct from a search that simply found nothing: the note library may be
    perfectly fine while the index is not, and conflating the two would report
    "no matches" for what is really "search is broken".
    """

    status = 503
    code = 3011
    message = "the search index is not available"


class NameInvalid(MarkNestError):
    """A file or folder name that cannot be created as given."""

    status = 400
    code = 3012
    message = "that name cannot be used"


class IdentityRequired(MarkNestError):
    """The request did not carry a usable TOS user identity.

    Each user has their own library, so a request that cannot be attributed to a
    user has no library to answer from. Distinct from ``AuthRequired``, which
    means the session itself was rejected.
    """

    status = 401
    code = 3013
    message = "your TOS user could not be determined"


class ScanBusy(MarkNestError):
    status = 429
    code = 3014
    message = "an index scan is already running"
