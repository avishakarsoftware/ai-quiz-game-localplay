"""Persistence errors shared by the SQLite and Supabase adapters."""


class QuizPackOwnershipError(RuntimeError):
    """A save attempted to replace another wallet's quiz pack."""

    def __init__(self):
        super().__init__("Quiz pack belongs to another wallet")
