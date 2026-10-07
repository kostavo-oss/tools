"""leeghwater's own errors."""


class LeeghwaterError(Exception):
    """Something leeghwater checked is wrong, and the message says what to do about it."""


class RunFailed(LeeghwaterError):
    """A pipeline ran and its result is not to be trusted: the run ends with 1."""
