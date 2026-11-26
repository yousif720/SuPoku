"""Answer rarity: a survey-based prior blended with real players' picks.

Before anyone plays a square, each valid answer's share is its survey
popularity weight (data/popularity.json, built by build_popularity.py) divided
by the total weight of every valid answer in that square: the chance that a
random player, picking in proportion to popularity, chooses it.

Player picks then move the shares. The survey's say shrinks as a square
collects picks, but never below SURVEY_FLOOR, so players can shift a square a
long way without wiping out the survey:

    survey_say = max(SURVEY_FLOOR, STRENGTH / (STRENGTH + picks))
    share      = survey_say * prior + (1 - survey_say) * (count / picks)
"""
import json
from pathlib import Path

from daily import CATS

STRENGTH = 30        # picks a square needs before players and survey count equally
SURVEY_FLOOR = 0.3   # the survey always keeps at least this much of every share

_path = Path(__file__).parent / 'data' / 'popularity.json'
try:
    WEIGHTS = {int(k): v for k, v in json.loads(_path.read_text(encoding='utf-8'))['weights'].items()}
except (OSError, ValueError, KeyError):
    WEIGHTS = {}
DEFAULT_WEIGHT = 1.0


def valid_answers(row, col):
    """Pokémon ids that fit both categories, or None for bad indices."""
    if not all(type(i) is int and 0 <= i < len(CATS) for i in (row, col)):
        return None
    return CATS[row]['ids'] & CATS[col]['ids']


def square_key(row, col):
    # Matches the browser's squareKey: the two category keys, sorted.
    return ' & '.join(sorted([CATS[row]['key'], CATS[col]['key']]))


def shares(valid, counts):
    """Percent share for every id in `valid`, given pick counts by id."""
    valid = list(valid)
    if not valid:
        return {}
    picks = sum(counts.get(i, 0) for i in valid)
    weight = sum(WEIGHTS.get(i, DEFAULT_WEIGHT) for i in valid)
    say = max(SURVEY_FLOOR, STRENGTH / (STRENGTH + picks))
    return {i: 100 * (say * WEIGHTS.get(i, DEFAULT_WEIGHT) / weight
                      + (1 - say) * (counts.get(i, 0) / picks if picks else 0))
            for i in valid}
