from __future__ import annotations

from typing import ClassVar, cast

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, Tree
from textual.widgets.tree import TreeNode

from ..cache import cache
from ..group import Group
from ..loaders import save_config, save_data


class GroupTree(Tree[Group]):
    BINDINGS: ClassVar = [
        ("r", "rename()", "Rename"),
        ("backspace", "delete()", "Delete"),
        Binding("E", "expand()", "Expand selected recursively", show=False),
        Binding("C", "collapse()", "Collapse selected recursively", show=False),
        Binding("enter", "create_or_expand()", "Create a new group, or toggle the group", show=False),
    ]

    def __init__(self, groups: list[Group]):
        super().__init__("groups")
        self.root.allow_expand = False
        self.root.expand()
        self.groups = groups

        for group in groups:
            self.populate_tree(self.root, group)
        self.root.add_leaf("[i]+ New group...", None)

    def populate_tree(self, tree: TreeNode[Group], group: Group):
        subtree = tree.add(group.name, group)
        for group in group.subgroups:
            self.populate_tree(subtree, group)
        subtree.add_leaf("[i]+ New subgroup...", None)

    @work
    async def action_rename(self):
        if self.cursor_node is None or self.cursor_node.data is None:
            return
        result = await self.app.push_screen_wait(RenameGroupModal(self.cursor_node.data.name))
        if result is not None:  # and await self.app.push_screen_wait(ConfirmModal("Are you sure you want to rename?")):
            self.cursor_node.set_label(result)
            self.cursor_node.data.rename(result)
            cast(ManageGroupsApp, self.app).unsaved_changes = True

    @work
    async def action_delete(self):
        if self.cursor_node is None or self.cursor_node.data is None:
            return
        result = await self.app.push_screen_wait(
            ConfirmModal(
                "Are you sure you want to delete this group and all its subgroups (including the associated rules) ?"
            )
        )
        if result:
            self.cursor_node.remove()
            self.cursor_node.data.delete()
            cast(ManageGroupsApp, self.app).unsaved_changes = True

    @work
    async def action_create_or_expand(self):
        if self.cursor_node is None or self.cursor_node.parent is None:
            return
        if self.cursor_node.data is not None:
            self.action_toggle_node()
            return

        name = await self.app.push_screen_wait(CreateGroupModal())
        if name is None:
            return
        group = cache.groups.create(name, parent=self.cursor_node.parent.data)
        self.cursor_node.parent.add(group.name, group, before=self.cursor_node).add_leaf("[i]+ New subgroup...", None)

    def action_expand(self):
        if self.cursor_node is None:
            return
        self.cursor_node.expand_all()

    def action_collapse(self):
        if self.cursor_node is None:
            return
        if self.cursor_node is self.root:
            for tree in self.root.children:
                tree.collapse_all()
        else:
            self.cursor_node.collapse_all()


class RenameGroupModal(ModalScreen[str | None]):
    def __init__(self, initial_value: str) -> None:
        super().__init__(classes="modal")
        self.input = Input(value=initial_value)

    def compose(self) -> ComposeResult:
        yield Grid(
            self.input,
            Button("Cancel", id="cancel-rename", classes="cancel-button"),
            Button("Rename", id="do-rename", classes="confirm-button"),
        )

    def on_button_pressed(self, event: Button.Pressed):
        match event.button:
            case Button(id="do-rename"):
                self.dismiss(self.input.value)
            case Button():
                self.dismiss()

    def on_input_submitted(self, input: Input):
        self.dismiss(input.value)


class CreateGroupModal(ModalScreen[str | None]):
    def __init__(self) -> None:
        super().__init__(classes="modal")
        self.input = Input(placeholder="Group name")

    def compose(self) -> ComposeResult:
        yield Grid(
            self.input,
            Button("Cancel", classes="cancel-button"),
            Button("Create", id="do-create", classes="confirm-button"),
        )

    def on_button_pressed(self, event: Button.Pressed):
        match event.button:
            case Button(id="do-create"):
                self.dismiss(self.input.value)
            case Button():
                self.dismiss()

    def on_input_submitted(self, input: Input):
        self.dismiss(input.value)


class ConfirmModal(ModalScreen[bool]):
    def __init__(self, label: str, ok_button_label: str = "Confirm", cancel_button_label: str = "Cancel"):
        super().__init__(classes="modal")
        self.label = label
        self.cancel_button_label = cancel_button_label
        self.ok_button_label = ok_button_label

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(f"[b]{self.label}[/b]"),
            Button(f"{self.cancel_button_label}", classes="cancel-button"),
            Button(f"{self.ok_button_label}", id="confirm", classes="confirm-button"),
        )

    def on_button_pressed(self, event: Button.Pressed):
        match event.button:
            case Button(id="confirm"):
                self.dismiss(True)
            case Button():
                self.dismiss(False)


class ManageGroupsApp(App[None]):
    CSS_PATH = "manage_groups.tcss"
    BINDINGS: ClassVar = [
        Binding("ctrl+s", "save()", "Save changes"),
        Binding("ctrl+c", "exit()", "Exit the app", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.unsaved_changes: bool = False

    def compose(self) -> ComposeResult:
        yield GroupTree(list(cache.groups))
        yield Footer()

    def action_save(self):
        save_config()
        save_data()
        self.unsaved_changes = False

    @work
    async def action_exit(self):
        if self.unsaved_changes and await self.app.push_screen_wait(ConfirmModal("Save the changes?", "Save", "Abort")):
            self.action_save()
        self.app.exit()


if __name__ == "__main__":
    _app = ManageGroupsApp()
    _app.run()
