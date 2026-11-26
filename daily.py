"""Deterministic daily rules shared by the HTTP service (no client scores trusted)."""
import json
from pathlib import Path
from functools import lru_cache

DATA = json.loads((Path(__file__).parent / 'data/pokedex.json').read_text(encoding='utf-8'))
POKEMON = {p['id']: p for p in DATA['pokemon']}
CATS = []


def add(family, main, test):
    CATS.append({'key': family + '|' + main, 'family': family,
                 'ids': {p['id'] for p in POKEMON.values() if test(p)}})


for t in DATA['types']:
    for family, field in [('type', 'types'), ('weak', 'weakTo'), ('resist', 'resists'), ('immune', 'immuneTo')]:
        add(family, t, lambda p: t in p[field])
regions = ['', 'Kanto', 'Johto', 'Hoenn', 'Sinnoh', 'Unova', 'Kalos', 'Alola', 'Galar', 'Paldea']
forms = dict(Alolan='Alola', Galarian='Galar', Hisuian='Hisui', Paldean='Paldea')
for r in ['Kanto', 'Johto', 'Hoenn', 'Sinnoh', 'Unova', 'Kalos', 'Alola', 'Galar', 'Hisui', 'Paldea']:
    add('region', r, lambda p: forms.get(p['region'], regions[p['gen']]) == r)
add('slots', 'Mono-type', lambda p: len(p['types']) == 1)
add('slots', 'Dual-type', lambda p: len(p['types']) == 2)
for mid in sorted(DATA['categoryMoves'], key=int):
    add('move', DATA['categoryMoves'][mid], lambda p: int(mid) in p['moves'])
for label, field in [('Legendary', 'legendary'), ('Mythical', 'mythical'), ('Baby Pokémon', 'baby')]:
    add('rare', label, lambda p: p[field])
add('rare', 'Not legendary', lambda p: not p['legendary'] and not p['mythical'])
add('form', 'Mega Evolution', lambda p: p['mega'])
add('form', 'Gigantamax', lambda p: p['gmax'])
add('form', 'Regional form', lambda p: bool(p['region']))
for r in forms:
    add('form', r + ' form', lambda p: p['region'] == r)
megas = {p['dex'] for p in POKEMON.values() if p['mega']}
add('form', 'Mega Evolution', lambda p: p['dex'] in megas)
add('evo', 'First in line', lambda p: p['stage'] == 1 and p['evolves'])
add('evo', 'Last in line', lambda p: not p['evolves'] and p['stage'] > 1)
add('evo', 'Never evolves', lambda p: p['stage'] == 1 and not p['evolves'])
add('evo', 'Middle stage', lambda p: p['stage'] == 2 and p['evolves'])
add('size', '100 kg or more', lambda p: p['weight'] >= 1000)
add('size', 'Under 10 kg', lambda p: p['weight'] < 100)
add('size', '2 m or taller', lambda p: p['height'] >= 20)
add('size', 'Under 1 m', lambda p: p['height'] < 10)
POOL = [i for i, c in enumerate(CATS) if len(c['ids']) >= 8]


@lru_cache(maxsize=32)
def puzzle(day):
    a = 2166136261
    for ch in 'pokegrid-' + day:
        a = ((a ^ ord(ch)) * 16777619) & 0xffffffff

    def rng():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xffffffff
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xffffffff
        t = ((t + ((t ^ (t >> 7)) * (61 | t))) & 0xffffffff) ^ t
        return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296

    def shuffle():
        out = POOL[:]
        for i in range(len(out) - 1, 0, -1):
            j = int(rng() * (i + 1))
            out[i], out[j] = out[j], out[i]
        return out

    for _ in range(600):
        rows, cols = [], []
        for i in shuffle():
            if len(rows) == 3:
                break
            if not any(CATS[r]['family'] == CATS[i]['family'] for r in rows):
                rows.append(i)
        for i in shuffle():
            if len(cols) == 3:
                break
            c = CATS[i]
            if any(CATS[r]['key'] == c['key'] for r in rows):
                continue
            if any(CATS[r]['family'] == c['family'] for r in cols):
                continue
            if all(len(CATS[r]['ids'] & c['ids']) >= 3 for r in rows):
                cols.append(i)
        if len(rows) == len(cols) == 3:
            return {'rows': rows, 'cols': cols}
    raise RuntimeError('Cannot generate daily puzzle')


def fresh(day):
    return dict(day=day, **puzzle(day), cells=[None]*9, retried=[False]*9,
                spent=[0]*9, guesses=9, mistakes=0, undoUsed=False, over=False,
                revision=0, points=0, rarities=[None]*9)


def action(game, req):
    if game['over']:
        raise ValueError('This daily result is final. Try a random grid or return tomorrow.')
    if req.get('revision') != game['revision']:
        raise ValueError('Your board changed in another tab. Reload the daily puzzle.')
    kind = req.get('action')
    if kind == 'giveup':
        game['guesses'] = 0
    else:
        i = req.get('cell')
        if type(i) is not int or not 0 <= i < 9:
            raise ValueError('Choose a square.')
        if kind == 'undo':
            if game['undoUsed'] or not (game['cells'][i] or game['retried'][i]):
                raise ValueError('Undo is not available.')
            game['guesses'] += game['spent'][i]
            game['cells'][i], game['spent'][i], game['retried'][i] = None, 0, False
            game.setdefault('rarities', [None]*9)[i] = None
            game['undoUsed'] = True
        elif kind == 'guess':
            pid = req.get('pokemon')
            if type(pid) is not int or pid not in POKEMON:
                raise ValueError('Unknown Pokémon.')
            if game['cells'][i] is not None or pid in game['cells']:
                raise ValueError('That square or Pokémon is already used.')
            valid = pid in CATS[game['rows'][i//3]]['ids'] & CATS[game['cols'][i%3]]['ids']
            if valid:
                game['cells'][i] = pid
            else:
                game['mistakes'] += 1
            if valid or game['retried'][i]:
                game['guesses'] -= 1
                game['spent'][i] += 1
            if not valid:
                game['retried'][i] = True
        else:
            raise ValueError('Unknown game action.')
    filled = sum(p is not None for p in game['cells'])
    game['points'] = max(0, filled * 100 - game['mistakes'] * 10)
    game['over'] = game['guesses'] == 0 or filled == 9
    game['revision'] += 1
    return game
