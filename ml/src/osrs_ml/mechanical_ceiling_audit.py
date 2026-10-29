"""Independent scalar reconciliation of the descriptive capacity outputs to source."""

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .alchemy import load_development
from .data import sha256


def audit(root, output):
    output = Path(output)
    run = json.loads((output / 'run.json').read_text())
    assert run['status'] == 'complete' and run['holdout_read'] is False
    assert run['profit_tests_run'] == 0 and run['observed_profit_gp'] is None
    repo = Path(__file__).resolve().parents[3]
    assert sha256(repo / 'docs/mechanical-ceiling-protocol.md') == run['protocol_sha256']
    assert sha256(repo / 'docs/mechanical-ceiling-amendment.md') == run['amendment_sha256']
    for name, digest in run['code_sha256'].items():
        assert sha256(Path(__file__).parent / name) == digest
    for name, digest in run['outputs_sha256'].items():
        assert sha256(output / name) == digest
    frame, mapping, provenance = load_development(root)
    assert all(run[k] == v for k, v in provenance.items())
    assert len(frame) == 341047 and frame.available_at.nunique() == 84
    assert int(frame.available_at.max()) < 1785024300
    meta = mapping.set_index('id')
    recipes = {r['name']: r for r in run['catalogue']}
    assumptions = {a['name']: a for a in run['assumptions']}
    # Only real development observations, read once; no generated market fixtures.
    wanted = {i for r in recipes.values() for i, _ in r['inputs']}
    wanted |= {r['output'] for r in recipes.values() if r['output']}
    f = frame[frame.item_id.isin(wanted)]
    source = {(int(r.item_id), int(r.available_at)): r for r in f.itertuples(index=False)}
    panel = pd.read_parquet(output / 'capacity-days.parquet')
    groups = []
    for (name, scenario), part in panel.groupby(['recipe', 'scenario']):
        r, a = recipes[name], assumptions[scenario]
        expected_gp, expected_q, expected_hours, reserved = [], [], [], []
        for row in part.itertuples(index=False):
            unit_cost = r['fee']
            caps = []
            for item, coefficient in r['inputs']:
                obs = source[item, row.available_at]
                assert obs.avg_high_price >= obs.avg_low_price > 0
                unit_cost += coefficient * math.ceil(obs.avg_high_price * 1001 / 1000)
                caps += [int(meta.loc[item, 'buy_limit']) // coefficient,
                         math.floor(obs.high_price_volume * a['share'] / coefficient)]
            if r['coins']:
                payoff = r['coins']
            else:
                obs = source[r['output'], row.available_at]
                assert obs.avg_high_price >= obs.avg_low_price > 0
                sale = math.floor(obs.avg_low_price * 999 / 1000)
                tax = 0 if sale < 50 or r['output'] == 8794 else min(sale * 2 // 100, 5000000)
                payoff = sale - tax
                caps += [math.floor(obs.low_price_volume * a['share'])]
            gap = payoff - unit_cost
            cost = unit_cost + max(0, gap) * (1 - a['retained'])
            seconds = (3600 / a['casts'] if r['casts'] else 0)
            seconds += 3600 / a['strings'] if r['strings'] else 0
            if r['fast']:
                seconds += 3600 / r['slow' if a['slow'] else 'fast']
            caps += [math.floor((1 - a['setup_minutes'] / 60) * 3600 / seconds),
                     math.floor((1000000 - (1500 if r['casts'] else 0)) / cost)]
            if r['stock']:
                caps += [r['stock']]
            target = min(caps) if gap > 0 else 0
            q = math.floor(target * a['completion'])
            gp = q * a['cadence'] * max(0, gap) * a['retained']
            hours = a['setup_minutes'] / 60 + q * a['cadence'] * seconds / 3600
            assert row.target_units == target and row.matched_units == q
            assert math.isclose(row.full_gap_gp, gap, abs_tol=1e-9)
            assert math.isclose(row.conditional_gp_real_day, gp, abs_tol=1e-9)
            assert math.isclose(row.active_hours, hours, abs_tol=1e-9)
            assert math.isclose(row.reserved_input_cash, target * cost, abs_tol=1e-9)
            assert q * cost + (1500 if r['casts'] else 0) <= 1000000 + 1e-9
            assert 0 <= hours <= 1 + 1e-9
            expected_gp.append(gp)
            expected_q.append(q * a['cadence'])
            expected_hours.append(hours)
            reserved.append(target * cost)
        missing = 84 - len(part)
        total_hours = sum(expected_hours) + missing * a['setup_minutes'] / 60
        groups.append(dict(recipe=name, scenario=scenario, gp_real_day=sum(expected_gp) / 84,
                           gp_active_hour=sum(expected_gp) / total_hours,
                           units_real_day=sum(expected_q) / 84,
                           peak_reserved_cash_gp=max(reserved)))
    independent = pd.DataFrame(groups).set_index(['recipe', 'scenario']).sort_index()
    saved = pd.read_csv(output / 'capacity.csv').set_index(['recipe', 'scenario']).sort_index()
    assert len(independent) == len(saved) == 760
    for field in independent:
        assert np.allclose(independent[field], saved[field], rtol=1e-12, atol=1e-8), field
    # Published original denominator is a one-unit sum, not volume-weighted capacity.
    assert run['original_one_unit_gap_gp_day'] == 11398956 / 84
    print(f'PASS: {len(panel)} scalar source reconciliations; 760 sensitivity summaries; '
          'all output/code/protocol hashes; capital, slots, tax, limits and time; holdout_read=False')
    return dict(status='passed', rows=len(panel), summaries=760, holdout_read=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    audit(Path(os.environ['OSRS_DATA_DIR']), args.output)


if __name__ == '__main__':
    main()
