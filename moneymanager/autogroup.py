from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple, overload

from .cache import cache
from .group import GroupBind
from .ui import Confirm, Markdown, console, transactions_table

if TYPE_CHECKING:
    from .group import AutoGroupRuleSets


class GroupingInfos(NamedTuple):
    groups_updated: int
    binds_added: int
    binds_removed: int


@overload
def prompt_automatic_grouping(*, bypass_confirm: Literal[True] = ..., preview: Literal[False] = ...) -> ...: ...


@overload
def prompt_automatic_grouping(*, bypass_confirm: Literal[False] = ..., preview: Literal[True] = ...) -> ...: ...


def prompt_automatic_grouping(*, bypass_confirm: bool = False, preview: bool = False) -> GroupingInfos:
    """
    Loops over all the cached transactions, and tests them against the auto-group rules presents in the cache.
    """
    if preview and bypass_confirm:
        raise ValueError("`bypass_confirm` and `preview` can't both be True.")

    groups_updated, binds_added, binds_removed = 0, 0, 0
    for grouping_rule in cache.grouping_rules:
        matches: set[GroupBind] = set()
        for transaction in cache.transactions:
            if grouping_rule.test_match(transaction):
                matches.add(GroupBind.from_objects(transaction, grouping_rule.group, "auto"))

        already_added = {bind for bind in grouping_rule.group.binds if bind.type == "auto"}
        removed = already_added - matches
        added = matches - already_added

        if not (added or removed):
            continue

        groups_updated += 1
        binds_added += len(added)
        binds_removed += len(removed)
        if not preview and (bypass_confirm or _confirm_auto_group_updates(grouping_rule, added, removed)):
            _apply_changes(added, removed)
            _added = f"added [bold]{len(added)}[/bold] binds" if added else ""
            _removed = f"removed [bold]{len(removed)}[/bold] binds" if removed else ""
            _and = " and " if removed and added else ""
            console.print(f"Successfully {_added}{_and}{_removed} for the group [underline]{grouping_rule.group.name}")
        elif not preview:
            console.print("[bold]Aborted.")
    if preview and groups_updated:
        plural = "different" if groups_updated > 1 else "single"
        console.print(
            Markdown(
                f"⚠️ Found **{binds_added}** groups to add, **{binds_removed}** groups "
                f"to remove, for **{groups_updated}** {plural} group(s).\n"
                "Please use the command `moneymanager update-auto-group` to update your automatic groups."
            )
        )
    return GroupingInfos(groups_updated, binds_added, binds_removed)


def _apply_changes(added: set[GroupBind], removed: set[GroupBind]):
    for bind in added:
        cache.group_binds.add(bind)
    for bind in removed:
        cache.group_binds.remove(bind)


def _confirm_auto_group_updates(grouping_rule: AutoGroupRuleSets, added: set[GroupBind], removed: set[GroupBind]):
    """
    Shows a prompt to confirm the addition or suppression of auto-added groups (if the rules got updated).
    """
    if not (removed or added):
        return

    console.print(f"Auto grouping detected some changes for the group [underline]{grouping_rule.group.name}!")

    if removed:
        table = transactions_table(bind.transaction for bind in removed)
        console.print("The following elements will be unassigned:")
        console.print(table)
    if added:
        table = transactions_table(bind.transaction for bind in added)
        console.print("The following elements will be assigned:")
        console.print(table)

    return Confirm.ask("Confirm ?")
