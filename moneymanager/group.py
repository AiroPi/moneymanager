from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    model_validator,
)

from .cache import cache

if TYPE_CHECKING:
    from .transaction import Transaction


class Groups(RootModel[list["Group"]]):
    _map: dict[str, Group] = PrivateAttr(default_factory=dict)

    def __iter__(self):  # type: ignore
        return iter(self.root)

    @model_validator(mode="after")
    def _init_map(self) -> Self:
        self._map_group(self.root)
        return self

    def _map_group(self, groups: Group | Iterable[Group]):
        """
        Add a map between the group name to the Group to allow O(1) access by name.
        Also map all the subgroups if any.
        """
        if isinstance(groups, Group):
            groups = (groups,)

        for group in groups:
            if group.name in self._map:
                raise ValueError(f"Duplicate group {group.name}")
            self._map[group.name] = group
            self._map_group(group.subgroups)

    def _recursive_iter(self, groups: Iterable[Group]) -> Generator[Group]:
        for group in groups:
            yield group
            yield from self._recursive_iter(group.subgroups)

    def all(self) -> Generator[Group]:
        """
        Iter recursively over groups and subgroups.
        """
        yield from self._recursive_iter(self.root)

    def __getitem__(self, key: str) -> Group:
        return self._map[key]

    def get(self, name: str) -> Group | None:
        """
        Get a group by name in O(1).
        """
        return self._map.get(name)

    def create(self, name: str, parent: Group | None = None):
        """
        Create a new group, by giving a name and a optionally a parent.
        """
        if name in self._map:
            raise ValueError("You can't have 2 groups with the same name!")
        group = Group(name=name, parent=parent)
        self._map_group(group)
        if parent:
            parent.subgroups.append(group)
        else:
            self.root.append(group)
        return group

    def remove(self, group: Group):
        """
        Delete a group. Also remove all the associated binds.
        Repeat recursively for each subgroups.
        """
        for bind in group.binds.copy():
            cache.group_binds.remove(bind)
        for sub in group.subgroups.copy():
            self.remove(sub)
        if group.parent:
            group.parent.subgroups.remove(group)
        else:
            self.root.remove(group)
        self._map.pop(group.name)

    def rename_group(self, group: Group, new_name: str):
        """
        Rename a group.
        """
        if new_name in self._map:
            raise ValueError(f"Can't rename: name already exist for {new_name}")

        self._map.pop(group.name)  # unmap the group
        group.name = new_name  # rename the group
        self._map[group.name] = group  # remap the group

        for bind in group.binds:
            bind.group_name = new_name


class Group(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Annotated[str, Field(alias="group_name")]
    subgroups: list[Group] = Field(default_factory=list)
    parent: Group | None = Field(None, exclude=True)
    rules: AutoGroupRuleSets | None = Field(default=None)
    _binds: set[GroupBind] = PrivateAttr(default_factory=set)

    def delete(self):
        cache.groups.remove(self)

    def rename(self, name: str):
        cache.groups.rename_group(self, name)

    def model_post_init(self, _: Any) -> None:
        for group in self.subgroups:
            group.parent = self

    @property
    def all_transactions(self) -> Iterator[Transaction]:
        yield from self._iter(set())

    @property
    def transactions(self) -> Iterator[Transaction]:
        yield from (bind.transaction for bind in self._binds)

    @property
    def binds(self):
        return self._binds

    def _iter(self, deduplicate: set[Transaction]) -> Iterator[Transaction]:
        for transaction in self.transactions:
            if transaction in deduplicate:
                continue
            deduplicate.add(transaction)
            yield transaction

        for subgroup in self.subgroups:
            yield from subgroup._iter(deduplicate)

    def __eq__(self, value: object) -> bool:
        return isinstance(value, Group) and value.name == self.name


class AutoGroupRuleSets(RootModel[list["Rule"]]):
    def test_match(self, item: Transaction) -> bool:
        # By default, multiple rules out of an AndRule are computed as an AndRule.
        return all(rule.test(item) for rule in self.root)


type Rule = Annotated[
    OrRule | AndRule | StartswithRule | ContainsRule | EqualRule | IContainsRule, Field(discriminator="type")
]


class NestingRule(BaseModel):
    type: Any  # here to define the ordering
    rules: list[Rule]


class TestRule(BaseModel):
    type: Any  # here to define the ordering
    key: str
    value: str


class OrRule(NestingRule):
    type: Literal["or"]

    def test(self, item: Transaction) -> bool:
        return any(rule.test(item) for rule in self.rules)


class AndRule(NestingRule):
    type: Literal["and"]

    def test(self, item: Transaction) -> bool:
        return all(rule.test(item) for rule in self.rules)


class ContainsRule(TestRule):
    type: Literal["contains"]

    def test(self, item: Transaction) -> bool:
        return self.value in getattr(item, self.key)


class IContainsRule(TestRule):
    type: Literal["icontains"]

    def test(self, item: Transaction) -> bool:
        return self.value.lower() in getattr(item, self.key).lower()


class StartswithRule(TestRule):
    type: Literal["startswith"]

    def test(self, item: Transaction) -> bool:
        return getattr(item, self.key).startswith(self.value)


class EqualRule(TestRule):
    type: Literal["equal", "eq"]

    def test(self, item: Transaction) -> bool:
        return getattr(item, self.key) == self.value


type GroupBindType = Literal["manual", "auto"]


class GroupBinds(RootModel[set["GroupBind"]]):
    def new(self, transaction: Transaction, group: Group, type: GroupBindType):
        bind = GroupBind(transaction_id=transaction.id, group_name=group.name, type=type)
        self.add(bind)

    def add(self, bind: GroupBind):
        self.root.add(bind)
        bind.transaction.binds.add(bind)
        bind.group.binds.add(bind)

    def remove(self, bind: GroupBind):
        self.root.remove(bind)
        bind.transaction.binds.remove(bind)
        bind.group.binds.remove(bind)

    def link_all(self):
        for bind in self.root:
            bind.transaction.binds.add(bind)
            bind.group.binds.add(bind)

    def model_post_init(self, _: Any) -> None:
        self.link_all()


class GroupBind(BaseModel):
    transaction_id: str
    group_name: str
    type: GroupBindType

    @classmethod
    def from_objects(cls, transaction: Transaction, group: Group, type: GroupBindType):
        return cls(transaction_id=transaction.id, group_name=group.name, type=type)

    @property
    def transaction(self) -> Transaction:
        return cache.transactions[self.transaction_id]

    @property
    def group(self) -> Group:
        return cache.groups[self.group_name]

    def __eq__(self, value: object) -> bool:
        return hash(value) == hash(self)

    def __hash__(self) -> int:
        return hash((self.transaction_id, self.group_name))
