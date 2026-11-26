"""Build data/popularity.json: a survey-based popularity weight per Pokédex entry.

Usage: python build_popularity.py "path/to/2025 Pokemon Survey RESULTS.xlsx"

The weights seed answer rarity before anyone has played a square. In a square,
a random player is modelled as picking each valid answer with probability

    weight(p) / sum(weight(q) for every valid answer q)

so a square's starting percentages come from the whole survey, not from zero.
rarity.py then blends in real players' picks.

Every sheet of the workbook feeds the weight, through Bayesian shrinkage:

* "All Forms Ranked" gives each form's own votes (the main signal), matched to
  Pokédex entries by dex number and name.
* "Top Types" totals, the per-form generation, and "Form Fights" (Mega, Alolan,
  Galarian, ... vs original) give what an average Pokémon of the same types,
  generation and kind of form earns. That expectation is added as a small
  pseudo-count, so a form with few or zero votes is estimated from its
  neighbours instead of being treated as never picked.
* "Grouped by Species" covers forms the survey did not list (Gigantamax,
  cosmetic variants): they borrow from their species' total.
* The starter and top-10 sheets restate rows of the sheets above, so they are
  already counted and are not added twice.
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'popularity.json'

# Model constants.
PSEUDO = 0.5   # weight of the type/gen/form expectation, in votes
TEMPER = 0.8   # <1 flattens: grid players reach past favourites more than a fan vote does
FLOOR = 0.25   # no valid answer is ever treated as impossible

STOP = {'form', 'forme', 'mode', 'size', 'cloak', 'breed', 'of', 'the', 'style',
        'pattern', 'flower', 'striped', 'segment', 'rider', 'family',
        'hero', 'many', 'battles'}
ALIAS = {'alolan': 'alola', 'galarian': 'galar', 'hisuian': 'hisui', 'paldean': 'paldea',
         'gigantamax': 'gmax', 'ash': 'ash', 'female': 'female', 'male': 'male',
         'original': 'original', 'east': 'east', 'west': 'west', 'lowkey': 'low'}


def tokens(text):
    text = text.lower().replace('é', 'e').replace("'", '').replace('.', '')
    out = set()
    for t in re.split(r'[^a-z0-9]+', text):
        if t and t not in STOP:
            out.add(ALIAS.get(t, t))
    return out


def sheet(wb, prefix):
    for ws in wb.worksheets:
        if ws.title.startswith(prefix):
            rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
            return rows[1:]
    raise SystemExit(f'Sheet starting "{prefix}" not found.')


def form_kind(p):
    if p['mega']:
        return 'Mega'
    if p['region']:
        return {'Alolan': 'Alola', 'Galarian': 'Galar', 'Hisuian': 'Hisui', 'Paldean': 'Paldea'}[p['region']]
    if p['slug'].endswith('-primal'):
        return 'Primal'
    return 'Original' if p['default'] else 'Other'


def build(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    dex = json.loads((ROOT / 'data' / 'pokedex.json').read_text(encoding='utf-8'))
    poke = dex['pokemon']
    by_dex = defaultdict(list)
    by_id = {p['id']: p for p in poke}
    for p in poke:
        by_dex[p['dex']].append(p)

    survey = [dict(dex=int(r[1]), name=str(r[2]).strip(), gen=r[3], votes=float(r[4] or 0))
              for r in sheet(wb, 'All Forms Ranked') if r[1] is not None and r[2]]
    species = {int(r[1]): float(r[3] or 0) for r in sheet(wb, 'Grouped by Species') if r[1] is not None}
    type_votes = {str(r[1]): float(r[2]) for r in sheet(wb, 'Top Types') if r[1]}
    fights = sheet(wb, 'Form Fights')
    kinds = ['Alola', 'Galar', 'Hisui', 'Mega', 'Original', 'Other', 'Paldea', 'Primal']
    kind_votes = {k: sum(float(r[2 + j] or 0) for r in fights if r[0] is not None) for j, k in enumerate(kinds)}

    # Match survey rows to Pokédex entries within each dex number, best token
    # overlap first. A row naming only the species goes to the default form.
    votes = defaultdict(float)
    matched_rows = 0
    unmatched = []
    for d in sorted({s['dex'] for s in survey}):
        rows = [s for s in survey if s['dex'] == d]
        entries = by_dex.get(d, [])
        base = tokens(entries[0]['species']) if entries else set()
        pairs = []
        for ri, s in enumerate(rows):
            st = tokens(s['name'])
            for p in entries:
                pt = tokens(p['name']) | tokens(p['slug'].replace('-', ' '))
                extra_s, extra_p = st - base, pt - base
                score = len(st & pt) / max(1, len(st | pt))
                if not extra_s and p['default']:
                    score += 1          # plain species name: the default form
                if extra_s and extra_s <= pt:
                    score += 1          # every qualifier in the survey name is on this entry
                score -= 0.01 * len(extra_p - st)
                pairs.append((score, ri, p['id']))
        used_rows, used_ids = set(), set()
        for score, ri, pid in sorted(pairs, reverse=True):
            if ri in used_rows or score <= 0.34:
                continue
            if pid in used_ids:
                # The survey sometimes repeats a name for two forms (its two
                # "Toxtricity" rows are Amped and Low Key). Give the row to the
                # best still-unclaimed regular form of the species; pool only
                # when none is left.
                spare = [(s2, p2) for s2, r2, p2 in pairs if r2 == ri and p2 not in used_ids
                         and not by_id[p2]['gmax'] and s2 > 0]
                if spare:
                    pid = max(spare)[1]
                    used_ids.add(pid)
                votes[pid] += rows[ri]['votes']
                used_rows.add(ri)
                matched_rows += 1
                continue
            used_rows.add(ri)
            used_ids.add(pid)
            votes[pid] += rows[ri]['votes']
            matched_rows += 1
        unmatched += [f"#{d} {rows[i]['name']}" for i in range(len(rows)) if i not in used_rows]

    # Expected votes for an average Pokémon sharing this entry's types, generation and kind of form.
    known = [p for p in poke if p['id'] in votes]
    total = sum(votes.values())
    mean = total / len(known)

    def avg(group_of, totals=None):
        n, s = defaultdict(int), defaultdict(float)
        for p in known:
            for g in group_of(p):
                n[g] += 1
                s[g] += votes[p['id']]
        if totals:   # use the survey's own published totals where it has them
            s = defaultdict(float, {g: totals.get(g, s[g]) for g in n})
        return {g: s[g] / n[g] for g in n}

    t_avg = avg(lambda p: p['types'], type_votes)
    g_avg = avg(lambda p: [p['gen']])
    k_avg = avg(lambda p: [form_kind(p)], kind_votes)

    def expected(p):
        rt = sum(t_avg.get(t, mean) for t in p['types']) / len(p['types']) / mean
        rg = g_avg.get(p['gen'], mean) / mean
        rk = k_avg.get(form_kind(p), mean) / mean
        return mean * (rt * rg * rk) ** (1 / 3)

    # Forms the survey never listed share one estimate per species, so a
    # species with fifteen costume variants does not outweigh its main form.
    unlisted = defaultdict(int)
    for p in poke:
        if p['id'] not in votes:
            unlisted[p['dex']] += 1

    weights = {}
    for p in poke:
        e = expected(p)
        if p['id'] in votes:
            raw = votes[p['id']] + PSEUDO * e
        else:
            # Not in the survey: lean on how loved the species is overall.
            s = species.get(p['dex'], 0.0)
            raw = PSEUDO * e * math.sqrt((s + mean) / (2 * mean)) / unlisted[p['dex']]
        weights[p['id']] = round(max(FLOOR, raw ** TEMPER), 4)

    OUT.write_text(json.dumps({
        'source': '2025 Pokémon survey (Sparklez Squad)',
        'model': {'pseudo': PSEUDO, 'temper': TEMPER, 'floor': FLOOR},
        'weights': weights,
    }, separators=(',', ':')), encoding='utf-8')
    print(f'{len(survey)} survey rows, {matched_rows} matched to {len(known)} Pokédex entries; '
          f'{len(poke) - len(known)} entries estimated from species/type/gen/form.')
    if unmatched:
        print('Unmatched survey rows:', ', '.join(unmatched))
    return weights, votes


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.split('\n\n')[1])
    build(sys.argv[1])
