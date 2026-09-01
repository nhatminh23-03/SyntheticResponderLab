"""Randomly assigned persona names.

Why names are assigned here rather than written by the language model:

An earlier version let the model name each persona. Given income and county, it reliably produced
ethnically-coded names that tracked income — the lowest earners drew Hispanic-coded names and the
highest drew a narrow set of Anglo and East Asian ones. That is the demographic stereotyping the
Stanford generative-agent work found in demographics-only agents, and instructing a model not to do
it does not reliably work.

Drawing the name from a fixed pool with its own random stream makes correlation with income,
occupation, or county impossible by construction rather than by instruction. The name carries no
information about the household and is not a Census-derived attribute.

The pool spans naming traditions common in California so the set does not read as uniform. Names
are drawn WITHOUT reference to any persona attribute except sex, which is a real Census variable.
"""

from __future__ import annotations

import numpy as np

FEMALE_FIRST = [
    "Alison", "Amara", "Ana", "Angela", "Anjali", "Bianca", "Carmen", "Catherine", "Chloe",
    "Claudia", "Dana", "Deborah", "Diane", "Elena", "Emily", "Esperanza", "Fatima", "Gabrielle",
    "Grace", "Hana", "Heather", "Ingrid", "Iris", "Jacqueline", "Janet", "Jasmine", "Joanna",
    "Julia", "Karen", "Kavita", "Kimberly", "Lakshmi", "Laura", "Leilani", "Linda", "Lorena",
    "Madeline", "Margaret", "Mei", "Melissa", "Mina", "Monica", "Nadia", "Naomi", "Nicole",
    "Olivia", "Paloma", "Patricia", "Priya", "Rachel", "Rebecca", "Rosa", "Sandra", "Sarah",
    "Serena", "Simone", "Sofia", "Stephanie", "Tessa", "Theresa", "Valerie", "Vanessa", "Vera",
    "Whitney", "Yolanda", "Yuki", "Zara",
]

MALE_FIRST = [
    "Aaron", "Adrian", "Alan", "Alejandro", "Andre", "Anthony", "Arjun", "Benjamin", "Brandon",
    "Brian", "Bruce", "Carlos", "Cesar", "Christopher", "Daniel", "Darius", "David", "Dennis",
    "Diego", "Douglas", "Edward", "Elias", "Eric", "Ethan", "Franklin", "Gabriel", "Gerald",
    "Gregory", "Harold", "Hector", "Henry", "Ian", "Isaac", "Jacob", "Jared", "Javier", "Jeffrey",
    "Jonathan", "Jorge", "Joseph", "Julian", "Keith", "Kenji", "Kevin", "Lawrence", "Leon",
    "Malik", "Marcus", "Martin", "Mateo", "Nathan", "Nicholas", "Omar", "Patrick", "Paul",
    "Peter", "Rajesh", "Ramon", "Raymond", "Ricardo", "Robert", "Samuel", "Sean", "Stephen",
    "Terrence", "Thomas", "Timothy", "Victor", "Wesley", "William",
]

SURNAMES = [
    "Abbott", "Acosta", "Aguilar", "Alvarez", "Andersen", "Bailey", "Barrett", "Beltran",
    "Bennett", "Blackwell", "Brennan", "Cabrera", "Callahan", "Campos", "Carrillo", "Castillo",
    "Chan", "Chandler", "Chavez", "Chen", "Cho", "Clarke", "Contreras", "Cortez", "Delgado",
    "Donnelly", "Duarte", "Dunn", "Ellis", "Escobar", "Farrell", "Fischer", "Fletcher", "Fuentes",
    "Gallagher", "Garrett", "Gill", "Gonzales", "Greene", "Gupta", "Hahn", "Hammond", "Harper",
    "Hayashi", "Henderson", "Hoang", "Holloway", "Ibarra", "Iyer", "Jenkins", "Kaplan", "Kaur",
    "Keller", "Khan", "Kim", "Kowalski", "Lambert", "Lam", "Larsen", "Le", "Leung", "Lindgren",
    "Lozano", "Mackenzie", "Maldonado", "Mansour", "Marsh", "Mathis", "McBride", "Medina",
    "Mehta", "Mendez", "Mercado", "Molina", "Moreno", "Nakamura", "Navarro", "Nguyen", "Nolan",
    "Ochoa", "Okafor", "Ortega", "Osborne", "Padilla", "Park", "Patel", "Pham", "Preston",
    "Quinn", "Ramos", "Reyes", "Rhodes", "Rivas", "Rosales", "Sandoval", "Santana", "Sawyer",
    "Serrano", "Shah", "Sharma", "Singh", "Solis", "Sousa", "Stafford", "Sullivan", "Tanaka",
    "Thornton", "Trujillo", "Vargas", "Vega", "Vo", "Wallace", "Weaver", "Whitfield", "Wong",
    "Yamamoto", "Yang", "Zamora", "Zhao",
]


def assign_names(sexes: list[str | None], seed: int) -> list[str]:
    """Assign one distinct name per persona, independent of every attribute except sex.

    Uses its own random stream so the assignment cannot line up with the order personas were
    drawn in, which itself carries no meaning but is better kept uncorrelated anyway.
    """
    rng = np.random.default_rng(seed)
    used_first: set[str] = set()
    used_last: set[str] = set()
    assigned: list[str] = []

    for sex in sexes:
        pool = FEMALE_FIRST if str(sex).strip().lower() == "female" else MALE_FIRST

        available_first = [n for n in pool if n not in used_first] or pool
        first = str(rng.choice(available_first))
        used_first.add(first)

        available_last = [n for n in SURNAMES if n not in used_last] or SURNAMES
        last = str(rng.choice(available_last))
        used_last.add(last)

        assigned.append(f"{first} {last}")

    return assigned
