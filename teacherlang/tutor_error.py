"""Error shared by the tutor runner and its provider backends."""


class TutorError(RuntimeError):
    """The tutor process failed or returned no usable lesson."""
