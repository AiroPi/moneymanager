from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    SkipValidation,
    field_serializer,
    field_validator,
    model_validator,
)

from .cache import cache

if TYPE_CHECKING:
    from .transaction import Transaction


class Groups(RootModel[list["Group"]]):
    _mapped_groups: dict[str, Group] = PrivateAttr(default_factory=dict)

    def __iter__(self):  # type: ignore
        return iter(self.root)

    @model_validator(mode="after")
    def _check_double(self) -> Self:
        self._map_groups(self.root)
        return self

    def _map_groups(self, groups: list[Group]):
        for group in groups:
            if group.name in self._mapped_groups:
                raise ValueError(f"Duplicate group {group.name}")
            self._map(group)

    def _map(self, group: Group):
        self._mapped_groups[group.name] = group
        self._map_groups(group.subgroups)

    def get_group(self, name: str) -> Group | None:
        return self._mapped_groups.get(name)

    def update_group_mapping(self, old_name: str, group: Group):
        self._mapped_groups.pop(old_name)
        self._mapped_groups[group.name] = group

    def create(self, name: str, parent: Group | None = None):
        if name in self._mapped_groups:
            raise ValueError("You can't have 2 groups with the same name!")
        group = Group(name=name, parent=parent)
        self._map(group)
        if parent:
            parent.subgroups.append(group)
        return group

    def remove(self, group: Group):
        for bind in group.binds.copy():
            cache.group_binds.remove(bind)
        for sub in group.subgroups.copy():
            self.remove(sub)
        if group.parent:
            group.parent.subgroups.remove(group)
        cache.grouping_rules.root = [r for r in cache.grouping_rules if r.group != group]
        self._mapped_groups.pop(group.name)

    def __getitem__(self, key: str) -> Group:
        return self._mapped_groups[key]


class Group(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Annotated[str, Field(alias="group_name")]
    subgroups: list[Group] = Field(default_factory=list)
    parent: Group | None = Field(None, exclude=True)
    _binds: set[GroupBind] = PrivateAttr(default_factory=set)

    def delete(self):
        cache.groups.remove(self)

    def rename(self, name: str):
        old_name = self.name
        self.name = name
        for bind in self.binds:
            bind.group_name = name
        cache.groups.update_group_mapping(old_name, self)

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


class GroupingRules(RootModel[list["AutoGroupRuleSets"]]):
    def __iter__(self):  # type: ignore
        return iter(self.root)

    def __len__(self):
        return len(self.root)


class AutoGroupRuleSets(BaseModel):
    group: SkipValidation[Group]  # validation made by _bind_group
    rules: list[Rule]

    @field_validator("group", mode="before")
    @classmethod
    def _bind_group(cls, v: str):
        group = cache.groups.get_group(v)
        if group is None:
            raise ValueError(f"The group '{v}' was not found in groups.")
        return group

    @field_serializer("group")
    def serialize_group(self, group: Group):
        return group.name

    def test_match(self, item: Transaction) -> bool:
        # By default, multiple rules out of a AndRule are computed as an and rule.
        return all(rule.test(item) for rule in self.rules)


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

    def __del__(self):
        print("DELETED")
        print(self)


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
