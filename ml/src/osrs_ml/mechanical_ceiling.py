"""Descriptive matched-cycle capacity sensitivity; never an own-fill backtest."""

import argparse
import json
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import alchemy, costs
from .data import sha256
from .diagnostics import atomic_json
from .weekly_ingest import external_directory

PROTOCOL = alchemy.REPO / 'docs/mechanical-ceiling-protocol.md'


@dataclass(frozen=True)
class Recipe:
    name: str
    family: str
    inputs: tuple[tuple[int, int], ...]
    output: int = 0
    coins: int = 0
    fee: int = 0
    slow: int = 0
    fast: int = 0
    casts: bool = False
    strings: bool = False
    stock: int = 0


def catalogue():
    recipes = [Recipe(f'alch_{i}', 'frozen_direct', ((i, 1), (561, 1)),
                      coins=a, casts=True) for i, a in
               [(855, 768), (859, 1536), (19580, 810), (19582, 1170)]]
    recipes += [Recipe('string_magic_sell', 'frozen_bow', ((70, 1), (1777, 1)),
                       output=859, strings=True),
                Recipe('string_yew_sell', 'frozen_bow', ((66, 1), (1777, 1)),
                       output=855, strings=True),
                Recipe('string_magic_alch', 'frozen_combined', ((70, 1), (1777, 1), (561, 1)),
                       coins=1536, casts=True, strings=True)]
    for name, source, output, fee in [
        ('cow_soft', 1739, 1741, 1), ('cow_hard', 1739, 1743, 3),
        ('snake', 6287, 6289, 15), ('snake_swamp', 7801, 6289, 20),
        ('green', 1753, 1745, 20), ('blue', 1751, 2505, 20),
        ('red', 1749, 2507, 20), ('black', 1747, 2509, 20),
    ]:
        recipes.append(Recipe('tan_' + name, 'tanning', ((source, 1),), output=output,
                              fee=fee, slow=1000, fast=2000))
    for source, output, fee in [(1511, 960, 100), (1521, 8778, 250),
                                (6333, 8780, 500), (6332, 8782, 1500)]:
        recipes.append(Recipe(f'plank_{output}', 'sawmill', ((source, 1),), output=output,
                              fee=fee, slow=1000, fast=2000))
    for source, output in [(1973, 1975), (237, 235), (9735, 9736), (5075, 6693)]:
        recipes.append(Recipe(f'grind_{source}', 'grinding', ((source, 1),), output=output,
                              slow=1000, fast=3000))
    for name, inputs, output in [
        ('bronze', ((436, 1), (438, 1)), 2349), ('silver', ((442, 1),), 2355),
        ('gold', ((444, 1),), 2357), ('steel', ((440, 1), (453, 2)), 2353),
        ('mithril', ((447, 1), (453, 4)), 2359),
        ('adamant', ((449, 1), (453, 6)), 2361),
        ('runite', ((451, 1), (453, 8)), 2363),
    ]:
        recipes.append(Recipe('smelt_' + name, 'furnace', inputs, output=output,
                              slow=400, fast=800))
    recipes.append(Recipe('gold_bracelet_alch', 'fixed_chain', ((2357, 1), (561, 1)),
                          coins=330, casts=True, slow=600, fast=1000))
    for item, fee in [(8794, 13), (8790, 650), (4819, 2), (4820, 5), (1539, 3)]:
        recipes.append(Recipe(f'shop_{item}', 'shop', (), output=item, fee=fee,
                              slow=200, fast=800, stock=1000))
    for quota in (15, 30, 60, 120):
        recipes.append(Recipe(f'zaff_{quota}', 'daily_vendor', (), output=1391, fee=7000,
                              slow=200, fast=800, stock=quota))
    return recipes


@dataclass(frozen=True)
class Assumptions:
    name: str = 'reference'
    casts: int = 1000
    strings: int = 1800
    setup_minutes: int = 5
    retained: float = 1
    share: float = .01
    completion: float = 1
    cadence: float = 1
    slow: bool = False


def scenarios():
    ref = Assumptions()
    out = [ref, Assumptions('cautious', 600, 1200, 15, .25, .001, .25, slow=True),
           replace(ref, name='optimistic', casts=1200)]
    for field, values in [('casts', (600, 1000, 1200)), ('retained', (.25, .5, 1)),
                          ('share', (0, .001, .01)), ('completion', (0, .25, 1)),
                          ('setup_minutes', (5, 15)), ('cadence', (.25, 1))]:
        out += [replace(ref, name=f'{field}={v}', **{field: v}) for v in values]
    return out


def observations(frame, mapping, recipe):
    """Inner join observed legs; no interpolation or substitution for missing days."""
    fields = ['avg_high_price', 'avg_low_price', 'high_price_volume', 'low_price_volume']
    x = frame[fields].to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(x).all(axis=1) & (x > 0).all(axis=1) & (x[:, 0] >= x[:, 1])
    f = frame.loc[valid].set_index(['item_id', 'available_at']).sort_index()
    meta = mapping.set_index('id')
    legs = [i for i, _ in recipe.inputs] + ([recipe.output] if recipe.output else [])
    if len(set(legs)) != len(legs) or len(legs) > 8:
        raise ValueError('Duplicate leg or slot overflow')
    pieces = []
    for item in legs:
        if item not in meta.index:
            raise ValueError(f'Unknown item {item}')
        if recipe.coins and item != 561 and recipe.name.startswith('alch_'):
            if int(meta.loc[item, 'high_alch']) != recipe.coins:
                raise ValueError('Alchemy metadata changed')
        pieces.append(f.loc[item].add_prefix(f'{item}_') if item in f.index.levels[0]
                      else pd.DataFrame(index=pd.Index([], name='available_at')))
    result = pd.concat(pieces, axis=1, join='inner')
    return result, meta


def economics(rows, recipe, side='high'):
    total = pd.Series(recipe.fee, index=rows.index, dtype=float)
    for item, coefficient in recipe.inputs:
        total += coefficient * np.ceil(rows[f'{item}_avg_{side}_price'] * 1.001)
    if recipe.coins:
        proceeds = pd.Series(recipe.coins, index=rows.index, dtype=float)
    else:
        output = np.floor(rows[f'{recipe.output}_avg_low_price'] * .999).astype('int64')
        proceeds = output.map(lambda p: costs.sale_proceeds(int(p), 1, item_id=recipe.output))
    return total, proceeds - total


def capacity(rows, meta, recipe, a):
    input_cost, gap = economics(rows, recipe)
    # Retained margin is an ASSUMED acquisition penalty, charged before cash sizing.
    paid = input_cost + gap.clip(lower=0) * (1 - a.retained)
    margin = gap.clip(lower=0) * a.retained
    seconds = (3600 / a.casts if recipe.casts else 0)
    seconds += 3600 / a.strings if recipe.strings else 0
    if recipe.fast:
        seconds += 3600 / (recipe.slow if a.slow else recipe.fast)
    setup = a.setup_minutes / 60
    target = pd.Series(math.floor((1 - setup) * 3600 / seconds), index=rows.index)
    budget = 1_000_000 - (1500 if recipe.casts else 0)
    target = np.minimum(target, np.floor(budget / paid))
    for item, coefficient in recipe.inputs:
        limit = meta.loc[item, 'buy_limit']
        if pd.isna(limit) or limit <= 0:
            raise ValueError('Unknown ingredient limit')
        target = np.minimum(target, int(limit) // coefficient)
        target = np.minimum(target, np.floor(rows[f'{item}_high_price_volume'] *
                                             a.share / coefficient))
    if recipe.output:
        target = np.minimum(target, np.floor(rows[f'{recipe.output}_low_price_volume'] * a.share))
    if recipe.stock:
        target = np.minimum(target, recipe.stock)
    target = target.where(gap > 0, 0).astype('int64')
    q = np.floor(target * a.completion).astype('int64')
    hours = q * seconds / 3600
    # On intervening days still charge a full daily check. No free failed attempts.
    daily_hours = setup + a.cadence * hours
    daily_q = a.cadence * q
    daily_gp = daily_q * margin
    assert (q >= 0).all() and (q <= target).all()
    assert (q * paid <= 1_000_000 + 1e-6).all()
    assert (daily_hours <= 1 + 1e-9).all()
    for item, coefficient in recipe.inputs:
        assert (q * coefficient <= int(meta.loc[item, 'buy_limit'])).all()
    result = pd.DataFrame(dict(target_units=target, matched_units=q, units_real_day=daily_q,
                               conditional_gp_real_day=daily_gp, active_hours=daily_hours,
                               matched_input_cash=q * paid, reserved_input_cash=target * paid,
                               full_gap_gp=gap, assumed_retained_gap_gp=margin,
                               assumed_paid_unit_gp=paid))
    return result


def summarize(rows, account, recipe, assumption, days):
    # Missing days remain calendar zero with a failed/check-session time charge.
    missing = len(days) - len(account)
    gp = float(account.conditional_gp_real_day.sum())
    hours = float(account.active_hours.sum()) + missing * assumption.setup_minutes / 60
    calendar = account.reindex(days, fill_value=0)
    return dict(recipe=recipe.name, family=recipe.family, scenario=assumption.name,
                kind='conditional_assumptions_not_observed_account_profit',
                observed_days=len(rows), missing_days=missing,
                units_real_day=float(account.units_real_day.sum() / len(days)),
                units_day_median=float(calendar.units_real_day.median()),
                units_day_max=float(calendar.units_real_day.max()),
                gp_real_day=gp / len(days), gp_active_hour=gp / hours,
                gp_day_p10=float(calendar.conditional_gp_real_day.quantile(.1)),
                gp_day_p90=float(calendar.conditional_gp_real_day.quantile(.9)),
                active_hours_day=hours / len(days),
                peak_reserved_cash_gp=float(account.reserved_input_cash.max()),
                median_reserved_cash_gp=float(account.reserved_input_cash.median()),
                gp_first_staff_day=(gp - (1500 if account.matched_units.sum() else 0)) / len(days)
                if recipe.casts else None,
                gp_first_staff_active_hour=(gp - (1500 if account.matched_units.sum() else 0)) / hours
                if recipe.casts else None,
                staff_once_gp=1500 if recipe.casts else 0,
                required_slots=len(recipe.inputs) + bool(recipe.output))


def run(root, output):
    output = external_directory(output, True)
    run_path = output / 'run.json'
    with run_path.open('x') as stream:
        json.dump(dict(status='reserved', holdout_read=False), stream)
    manifest = dict(status='running', holdout_read=False, profit_tests_run=0,
                    observed_profit_gp=None, protocol_sha256=sha256(PROTOCOL),
                    code_sha256={p.name: sha256(p) for p in
                                 [Path(__file__), Path(alchemy.__file__), Path(costs.__file__)]},
                    assumptions=[a.__dict__ for a in scenarios()],
                    catalogue=[r.__dict__ for r in catalogue()])
    atomic_json(run_path, manifest)
    try:
        frame, mapping, provenance = alchemy.load_development(root)
        manifest.update(provenance, source_rows=len(frame),
                        min_available_at=int(frame.available_at.min()),
                        max_available_at=int(frame.available_at.max()))
        assert manifest['max_available_at'] < alchemy.registration()['holdout_start']
        days = sorted(frame.available_at.unique())
        original, original_summary = alchemy.screen(frame, mapping)
        check = original.groupby('side').apply(
            lambda p: pd.Series(dict(positive=int((p.gap_gp > 0).sum()),
                                     unit_gap_sum=int(p.loc[p.gap_gp > 0, 'gap_gp'].sum()))),
            include_groups=False)
        assert check.loc['low'].tolist() == [24622, 11398956]
        assert check.loc['high'].tolist() == [13915, 3422903]
        print('ORIGINAL SCREEN RECONCILED\n' + check.to_string(), flush=True)
        aggregate = 11398956 / len(days)
        screens, summaries, details, limit_rows = [], [], [], []
        for recipe in catalogue():
            rows, meta = observations(frame, mapping, recipe)
            for side in ('high', 'low'):
                _, gap = economics(rows, recipe, side)
                pos = gap[gap > 0]
                screens.append(dict(recipe=recipe.name, family=recipe.family, input_side=side,
                                    kind='observed_average_gap_current_mechanics', days=len(gap),
                                    missing_days=len(days) - len(gap), positive_days=len(pos),
                                    positive_fraction=len(pos) / len(gap) if len(gap) else None,
                                    all_gap_median=float(gap.median()),
                                    positive_gap_min=float(pos.min()) if len(pos) else None,
                                    positive_gap_median=float(pos.median()) if len(pos) else None,
                                    positive_gap_p90=float(pos.quantile(.9)) if len(pos) else None,
                                    positive_gap_max=float(pos.max()) if len(pos) else None))
            for item, coefficient in recipe.inputs:
                limit_rows.append(dict(recipe=recipe.name, item_id=item,
                                       name=meta.loc[item, 'name'], units_per_conversion=coefficient,
                                       current_limit_4h=int(meta.loc[item, 'buy_limit']),
                                       theoretical_units_24h=6 * int(meta.loc[item, 'buy_limit']),
                                       kind='current_metadata_and_full_reset_assumption'))
            for assumption in scenarios():
                account = capacity(rows, meta, recipe, assumption)
                summary = summarize(rows, account, recipe, assumption, days)
                summary['ratio_to_one_unit_sum_pct'] = 100 * summary['gp_real_day'] / aggregate
                summaries.append(summary)
                details.append(account.assign(recipe=recipe.name, scenario=assumption.name)
                               .reset_index())
        pd.DataFrame(screens).to_csv(output / 'screens.csv', index=False)
        summary = pd.DataFrame(summaries)
        summary.to_csv(output / 'capacity.csv', index=False)
        pd.DataFrame(limit_rows).to_csv(output / 'limits.csv', index=False)
        pd.concat(details).to_parquet(output / 'capacity-days.parquet', index=False)
        original_summary.to_csv(output / 'original-screen.csv', index=False)
        manifest.update(status='complete', calendar_days=len(days),
                        original_one_unit_gap_gp_day=aggregate,
                        source_kind='daily_development_means_only',
                        outputs_sha256={p.name: sha256(p) for p in sorted(output.iterdir())
                                        if p.name != 'run.json'})
        atomic_json(run_path, manifest)
        print('FROZEN CANDIDATE CONDITIONAL ENDPOINTS (ASSUMPTIONS)')
        columns = ['recipe', 'scenario', 'units_real_day', 'gp_real_day', 'gp_active_hour',
                   'active_hours_day', 'peak_reserved_cash_gp', 'ratio_to_one_unit_sum_pct']
        print(summary[summary.family.str.startswith('frozen') &
                      summary.scenario.isin(['cautious', 'optimistic'])][columns]
              .round(2).to_string(index=False), flush=True)
        print('OTHER MECHANICS: ALL MEMBERS, HIGH INPUT SIDE OBSERVED GAPS')
        print(pd.DataFrame(screens).query("input_side == 'high'").round(2).to_string(index=False))
        print(f'PASS: {len(frame)} development rows; {len(days)} calendar days; '
              f'{len(catalogue())} recipes; {len(summaries)} sensitivity rows; '
              'capacity/cash/time/limit assertions passed; profit_tests=0; holdout_read=False')
    except Exception as exc:
        manifest.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        atomic_json(run_path, manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(Path(os.environ['OSRS_DATA_DIR']), args.output)


if __name__ == '__main__':
    main()
