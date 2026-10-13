from enum import StrEnum


class Role(StrEnum):
    WEREWOLF = "Werewolf"
    SEER = "Seer"
    DOCTOR = "Doctor"
    VILLAGER = "Villager"


class Team(StrEnum):
    VILLAGE = "Village"
    WOLVES = "Wolves"


# Roles dealt each game: 2 wolves, 1 Seer, 1 Doctor, 4 villagers.
ROLE_DECK: tuple[Role, ...] = (
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.SEER,
    Role.DOCTOR,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
)
