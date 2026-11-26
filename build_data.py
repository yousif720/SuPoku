"""Build data/pokedex.json for SuPoku from the PokeAPI CSV data dumps.

Downloads the CSVs on first run (cached in ./csv), then joins them into a single
JSON payload the front-end loads. Covers every entry in pokemon.csv: all 1330
forms, including all 97 Mega Evolutions (Kalos, Legends: Z-A and the Mega
Dimension DLC), Gigantamax, regional variants and battle forms.

Two rules go beyond a plain type-chart join:
  * immunities account for abilities (Levitate, Flash Fire, Wonder Guard, ...),
    so a Levitate Pokemon is immune to Ground while a plain Electric type is not;
  * Smeargle's learnset is expanded via Sketch, which copies any move except a
    short blacklist.
"""

import csv
import json
import os
import sys
import urllib.request
from collections import defaultdict

BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pokedex.json")
EN = "9"  # local_language_id for English

FILES = [
    "pokemon", "pokemon_species", "pokemon_types", "pokemon_stats",
    "pokemon_abilities", "abilities", "types", "type_efficacy",
    "moves", "move_names", "pokemon_moves", "pokemon_forms", "pokemon_form_names",
    "pokemon_species_names", "pokemon_colors", "pokemon_shapes", "pokemon_habitats",
    "stats",
]

# Abilities that grant a flat immunity to one attacking type.
ABILITY_IMMUNITY = {
    "levitate": "ground",
    "earth-eater": "ground",
    "flash-fire": "fire",
    "well-baked-body": "fire",
    "water-absorb": "water",
    "storm-drain": "water",
    "dry-skin": "water",
    "volt-absorb": "electric",
    "lightning-rod": "electric",
    "motor-drive": "electric",
    "sap-sipper": "grass",
}
# Wonder Guard (Shedinja) blocks everything that is not super effective.
WONDER_GUARD = "wonder-guard"

SKETCH = "sketch"
# Sketch copies any move except these (Gen IX), so Smeargle learns the rest.
UNSKETCHABLE = {
    "struggle", "sketch", "chatter", "dark-void", "hyperspace-fury",
    "revival-blessing", "tera-starstorm",
    "blazing-torque", "wicked-torque", "noxious-torque", "combat-torque",
    "magical-torque",
}
# Max/G-Max moves are name-identifiable; the Colosseum/XD "Shadow moves" are not
# (Shadow Claw and Shadow Sneak are ordinary Ghost moves), so those are
# matched by their shadow type id instead.
UNSKETCHABLE_PREFIXES = ("max-", "g-max-")


def fetch(name):
    """Return rows of csv/<name>.csv as dicts, downloading the file if absent."""
    path = os.path.join(CSV_DIR, name + ".csv")
    if not os.path.exists(path):
        os.makedirs(CSV_DIR, exist_ok=True)
        sys.stderr.write("downloading %s.csv\n" % name)
        urllib.request.urlretrieve("%s/%s.csv" % (BASE, name), path)
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def titlecase(slug):
    small = {"of", "the", "and"}
    parts = slug.split("-")
    return " ".join(p if p in small else p.capitalize() for p in parts)


# ---------------------------------------------------------------- lookups ---
raw = {name: fetch(name) for name in FILES}

type_name = {r["id"]: titlecase(r["identifier"]) for r in raw["types"]}
type_slug = {r["id"]: r["identifier"] for r in raw["types"]}
# Skip non-battle types: the two placeholders plus Stellar, which is a Tera-only
# type with no defensive matchups of its own.
battle_types = [r["id"] for r in raw["types"]
                if r["identifier"] not in ("unknown", "shadow", "stellar")]

ability_slug = {r["id"]: r["identifier"] for r in raw["abilities"]}
ability_label = {r["id"]: titlecase(r["identifier"]) for r in raw["abilities"]}

move_slug = {r["id"]: r["identifier"] for r in raw["moves"]}
move_name = {r["id"]: titlecase(r["identifier"]) for r in raw["moves"]}
for r in raw["move_names"]:
    if r["local_language_id"] == EN:
        move_name[r["move_id"]] = r["name"]

color_name = {r["id"]: titlecase(r["identifier"]) for r in raw["pokemon_colors"]}
shape_name = {r["id"]: titlecase(r["identifier"]) for r in raw["pokemon_shapes"]}
habitat_name = {r["id"]: titlecase(r["identifier"]) for r in raw["pokemon_habitats"]}
stat_key = {r["id"]: r["identifier"] for r in raw["stats"]}

species_en = {r["pokemon_species_id"]: r["name"] for r in raw["pokemon_species_names"]
              if r["local_language_id"] == EN}
genus_en = {r["pokemon_species_id"]: r["genus"] for r in raw["pokemon_species_names"]
            if r["local_language_id"] == EN}

# Full English display name of a form, e.g. "Mega Venusaur", "Alolan Raichu".
form_en = {}
for r in raw["pokemon_form_names"]:
    if r["local_language_id"] == EN and r.get("pokemon_name"):
        form_en[r["pokemon_form_id"]] = r["pokemon_name"]

forms_by_pokemon = defaultdict(list)
for r in raw["pokemon_forms"]:
    forms_by_pokemon[r["pokemon_id"]].append(r)

# ------------------------------------------------------------ type chart ---
# efficacy[attacking][defending] = multiplier
efficacy = defaultdict(dict)
for r in raw["type_efficacy"]:
    efficacy[r["damage_type_id"]][r["target_type_id"]] = int(r["damage_factor"]) / 100.0


def matchups(type_ids, abilities):
    """Defensive matchups for a typing, with ability-granted immunities applied.

    `abilities` is the list of ability identifiers the Pokemon can have (hidden
    ones included). Returns (weak_to, resists, immune_to, immune_via) where
    immune_via maps a type name to the ability responsible, if any.
    """
    granted = {}   # type slug -> ability identifier
    for ab in abilities:
        if ab in ABILITY_IMMUNITY:
            granted.setdefault(ABILITY_IMMUNITY[ab], ab)

    weak, resist, immune, via = [], [], [], {}
    for atk in battle_types:
        mult = 1.0
        for dfn in type_ids:
            mult *= efficacy[atk].get(dfn, 1.0)

        slug, label = type_slug[atk], type_name[atk]
        if slug in granted:
            immune.append(label)
            via[label] = ability_label_by_slug[granted[slug]]
        elif WONDER_GUARD in abilities and mult <= 1:
            # Shedinja: only super-effective hits land at all.
            immune.append(label)
            via[label] = "Wonder Guard"
        elif mult == 0:
            immune.append(label)
        elif mult > 1:
            weak.append(label)
        elif mult < 1:
            resist.append(label)
    return weak, resist, immune, via


ability_label_by_slug = {v: ability_label[k] for k, v in ability_slug.items()}

# --------------------------------------------------------- per-pokemon ---
types_of = defaultdict(list)
for r in sorted(raw["pokemon_types"], key=lambda r: int(r["slot"])):
    types_of[r["pokemon_id"]].append(r["type_id"])

stats_of = defaultdict(dict)
for r in raw["pokemon_stats"]:
    stats_of[r["pokemon_id"]][stat_key[r["stat_id"]]] = int(r["base_stat"])

abilities_of = defaultdict(list)
for r in sorted(raw["pokemon_abilities"], key=lambda r: int(r["slot"])):
    abilities_of[r["pokemon_id"]].append(ability_slug[r["ability_id"]])

moves_of = defaultdict(set)
for r in raw["pokemon_moves"]:
    moves_of[r["pokemon_id"]].add(int(r["move_id"]))

# ------------------------------------------------------------- sketch ---
# Everything Sketch is allowed to copy.
shadow_type = next((r["id"] for r in raw["types"] if r["identifier"] == "shadow"), None)
shadow_moves = {r["id"] for r in raw["moves"] if r["type_id"] == shadow_type}
sketchable = {int(mid) for mid, slug in move_slug.items()
              if slug not in UNSKETCHABLE
              and not slug.startswith(UNSKETCHABLE_PREFIXES)
              and mid not in shadow_moves}
sketch_id = next(int(mid) for mid, slug in move_slug.items() if slug == SKETCH)

sketchers = [pid for pid, mv in moves_of.items() if sketch_id in mv]
for pid in sketchers:
    moves_of[pid] |= sketchable

species = {r["id"]: r for r in raw["pokemon_species"]}

# Evolution position, derived from the species graph.
evolves_from = {sid: s["evolves_from_species_id"] for sid, s in species.items()}
has_evolution = set(v for v in evolves_from.values() if v)


def evo_stage(sid):
    """1, 2 or 3: how deep this species sits in its evolution line."""
    depth, seen = 1, set()
    cur = evolves_from.get(sid)
    while cur and cur not in seen:
        seen.add(cur)
        depth += 1
        cur = evolves_from.get(cur)
    return min(depth, 3)


REGIONS = {
    "alola": "Alolan", "galar": "Galarian", "hisui": "Hisuian", "paldea": "Paldean",
}

pokedex = []
for r in raw["pokemon"]:
    pid, sid = r["id"], r["species_id"]
    sp = species.get(sid)
    if not sp:
        continue
    # Totem forms are oversized Alola duplicates of a base form, sharing its
    # typing and stats, so they only pad the answer list.
    if "totem" in r["identifier"]:
        continue
    # Koraidon and Miraidon's travel builds are ride variants of the same
    # Pokemon, with no artwork or sprite of their own. These suffixes match
    # those eight forms and nothing else in the dex.
    if r["identifier"].endswith(("-build", "-mode")):
        continue
    # Busted Mimikyu is the same Pokemon with its disguise broken, and has no
    # artwork of its own.
    if r["identifier"].endswith("-busted"):
        continue
    # Minior: keep the base entry and all seven core colours, but drop the other
    # six meteor shades. The default form (774) is itself a meteor, hence the
    # is_default check.
    if r["identifier"].endswith("-meteor") and r["is_default"] != "1":
        continue

    tids = types_of.get(pid, [])
    abils = abilities_of.get(pid, [])
    weak, resist, immune, via = matchups(tids, abils)
    st = stats_of.get(pid, {})
    bst = sum(st.values())

    slug = r["identifier"]
    suffix = slug[len(sp["identifier"]):].strip("-") if slug.startswith(sp["identifier"]) else ""

    # Display name: prefer the curated English form name, else species + suffix.
    name = species_en.get(sid, titlecase(sp["identifier"]))
    if r["is_default"] != "1":
        form_rows = forms_by_pokemon.get(pid, [])
        pretty = next((form_en[f["id"]] for f in form_rows if f["id"] in form_en), None)
        if pretty:
            name = pretty
        elif suffix:
            name = "%s (%s)" % (name, titlecase(suffix))

    is_mega = any(f["is_mega"] == "1" for f in forms_by_pokemon.get(pid, []))
    region = next((v for k, v in REGIONS.items() if k in suffix.split("-")), None)

    # Mega/Gmax forms have no learnset rows of their own; they use the base form's.
    mv = moves_of.get(pid) or moves_of.get(sid) or set()

    pokedex.append({
        "id": int(pid),
        "slug": slug,
        "name": name,
        "dex": int(sid),
        "species": species_en.get(sid, titlecase(sp["identifier"])),
        "genus": genus_en.get(sid, ""),
        "types": [type_name[t] for t in tids],
        "gen": int(sp["generation_id"]),
        "stats": {k: st.get(k, 0) for k in
                  ("hp", "attack", "defense", "special-attack", "special-defense", "speed")},
        "bst": bst,
        "height": int(r["height"] or 0),   # decimetres
        "weight": int(r["weight"] or 0),   # hectograms
        "color": color_name.get(sp["color_id"], ""),
        "shape": shape_name.get(sp["shape_id"], ""),
        "habitat": habitat_name.get(sp["habitat_id"], ""),
        "legendary": sp["is_legendary"] == "1",
        "mythical": sp["is_mythical"] == "1",
        "baby": sp["is_baby"] == "1",
        "default": r["is_default"] == "1",
        "mega": is_mega,
        "gmax": "gmax" in suffix.split("-"),
        "region": region,
        "form": suffix or None,
        "stage": evo_stage(sid),
        "evolves": sid in has_evolution,
        "weakTo": weak,
        "resists": resist,
        "immuneTo": immune,
        "immuneVia": via,
        "moves": sorted(mv),
    })

# A handful of forms share an English name (e.g. male/female Mega Meowstic).
# Disambiguate them with the distinguishing part of their form slug.
seen = {}
for p in pokedex:
    seen.setdefault(p["name"], []).append(p)
for name, group in seen.items():
    if len(group) < 2:
        continue
    for p in group:
        extra = [w for w in (p["form"] or "").split("-") if w not in ("mega", "gmax", "")]
        p["name"] = "%s (%s)" % (name, titlecase("-".join(extra))) if extra else \
                    "%s (#%d)" % (name, p["id"])

pokedex.sort(key=lambda p: (p["dex"], p["id"]))

# Moves worth using as a grid category: anything a fair number of Pokemon can
# learn. There is no upper bound, so common moves like Protect qualify too.
move_counts = defaultdict(int)
for p in pokedex:
    for m in p["moves"]:
        move_counts[m] += 1
category_moves = {str(m): move_name[str(m)] for m, c in move_counts.items()
                  if c >= 25 and str(m) in move_name}

payload = {
    "generatedFrom": "PokeAPI CSV data dump (github.com/PokeAPI/pokeapi)",
    "types": [type_name[t] for t in battle_types],
    "moveNames": {str(m): move_name[str(m)] for m in move_counts},
    "categoryMoves": category_moves,
    "pokemon": pokedex,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)

by_ability = sum(1 for p in pokedex if p["immuneVia"])
print("wrote %s" % OUT)
print("  %d entries  |  %d megas  |  %d gmax  |  %d regional forms"
      % (len(pokedex), sum(1 for p in pokedex if p["mega"]),
         sum(1 for p in pokedex if p["gmax"]), sum(1 for p in pokedex if p["region"])))
print("  %d with an ability-granted immunity  |  %d Sketch users expanded to %d moves"
      % (by_ability, len(sketchers), len(sketchable)))
print("  %d category-eligible moves  |  %.1f MB"
      % (len(category_moves), os.path.getsize(OUT) / 1e6))
