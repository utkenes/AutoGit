"""Repository safety information collected before an AutoGit commit."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryState:
    is_repository: bool
    has_head: bool
    branch_name: str | None
    is_detached_head: bool
    merge_in_progress: bool
    rebase_in_progress: bool
    cherry_pick_in_progress: bool
    revert_in_progress: bool

    @property
    def is_safe_for_commit(self) -> bool:
        return (
            self.is_repository
            and self.has_head
            and not self.is_detached_head
            and not self.merge_in_progress
            and not self.rebase_in_progress
            and not self.cherry_pick_in_progress
            and not self.revert_in_progress
        )
