from __future__ import annotations

from typing import TYPE_CHECKING

from .cache import cache
from .ui import Confirm, console, transactions_table

if TYPE_CHECKING:
    from .group import AutoGroupRuleSets, GroupBind


def do_auto_grouping():
    """
    Loops over all the cached transactions, and tests them against the auto-group rules presents in the cache.
    """
    for grouping_rule in cache.grouping_rules:
        matches: set[GroupBind] = set()
        for transaction in cache.transactions:
            if grouping_rule.test_match(transaction):
                matches.add(GroupBind.from_objects(transaction, grouping_rule.group, "auto"))
        confirm_auto_group_updates(grouping_rule, matches)


def confirm_auto_group_updates(grouping_rule: AutoGroupRuleSets, matches: set[GroupBind]):
    """
    Shows a prompt to confirm the addition or suppression of auto-added groups (if the rules got updated).
    """
    already_added = {bind for bind in grouping_rule.group.binds if bind.type == "auto"}
    removed = already_added - matches
    added = matches - already_added

    if not (removed or added):
        return

    console.print(
        f"[bold]:warning: Auto grouping detected some changes for the group [underline]{grouping_rule.group.name}!"
    )

    if removed:
        table = transactions_table(bind.transaction for bind in removed)
        console.print("The following elements will be unassigned:")
        console.print(table)
    if added:
        table = transactions_table(bind.transaction for bind in added)
        console.print("The following elements will be assigned:")
        console.print(table)

    if Confirm.ask("Confirm ?"):
        for bind in added:
            cache.group_binds.add(bind)
        for bind in removed:
            cache.group_binds.remove(bind)
