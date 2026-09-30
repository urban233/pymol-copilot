# Integrated TaskSuccess against offline

| Condition | Offline TaskSuccess | Integrated TaskSuccess | Only offline | Only integrated | Exact McNemar p |
| --- | --- | --- | --- | --- | --- |
| grammar | 32/68 (47.1%, 35.7-58.8%) | 33/68 (48.5%, 37.1-60.2%) | 0 | 1 | 1 |
| no-grammar | 19/68 (27.9%, 18.7-39.6%) | 19/68 (27.9%, 18.7-39.6%) | 0 | 0 | 1 |

## grammar

- Outcomes: applied 68, not_applicable 0, apply_restored 0, apply_refused 0, no_plan 0, timeout 0.
- Prompt skew (live structure not the recorded one): 0 of 68.
- Latency: preview p50 8.9 s, p90 11.3 s; apply p50 2.0 s, p90 2.3 s.

### Every sample whose outcome differs

| Sample | Offline | Integrated | Live outcome | Offline outcome | Explanation |
| --- | --- | --- | --- | --- | --- |
| gold_044 | False | True | applied | executed_wrong | engine_drift |

### By shape

| Shape | n | Offline | Integrated |
| --- | --- | --- | --- |
| and | 9 | 3 | 4 |
| and+not | 4 | 1 | 1 |
| and_or | 6 | 0 | 0 |
| or | 5 | 0 | 0 |
| single | 38 | 23 | 23 |
| single+not | 6 | 5 | 5 |

### By category

| Category | n | Offline | Integrated |
| --- | --- | --- | --- |
| color+select+show/chain+resi/and | 1 | 0 | 0 |
| color+select+show/chain+resn/and | 1 | 0 | 0 |
| color+select+show/chain/single | 1 | 1 | 1 |
| color+select+show/hetatm/single | 1 | 1 | 1 |
| color+select+show/name/single | 1 | 0 | 0 |
| color+select+show/resi/single+not | 1 | 1 | 1 |
| color+select+show/resn/single | 1 | 1 | 1 |
| color+select/chain+resi/and_or | 1 | 0 | 0 |
| color+select/chain+resn/and_or | 1 | 0 | 0 |
| color+select/chain/single | 1 | 1 | 1 |
| color+select/hetatm/single | 1 | 1 | 1 |
| color+select/name+resn/and_or | 1 | 0 | 0 |
| color+select/name/single | 1 | 0 | 0 |
| color+select/resi/single | 1 | 0 | 0 |
| color+select/resn/or | 1 | 0 | 0 |
| color+select/resn/single | 1 | 0 | 0 |
| color+select/resn/single+not | 1 | 1 | 1 |
| color+show/chain+resi/and | 1 | 0 | 0 |
| color/chain+hetatm/and+not | 1 | 0 | 0 |
| color/chain+name+resn/and_or | 1 | 0 | 0 |
| color/chain+name/and | 1 | 1 | 1 |
| color/chain+resi/and | 1 | 0 | 0 |
| color/chain/or | 1 | 0 | 0 |
| color/chain/single | 1 | 1 | 1 |
| color/chain/single+not | 1 | 1 | 1 |
| color/hetatm/single | 1 | 0 | 0 |
| color/name/single | 1 | 0 | 0 |
| color/resi/single | 1 | 1 | 1 |
| color/resn/or | 1 | 0 | 0 |
| color/resn/single | 2 | 0 | 0 |
| hide+select/chain+hetatm/and | 1 | 1 | 1 |
| hide+select/chain/single | 1 | 1 | 1 |
| hide+select/name/single | 1 | 0 | 0 |
| hide+select/resi/single | 1 | 1 | 1 |
| hide+select/resn/single | 1 | 0 | 0 |
| hide+show/chain/single | 1 | 0 | 0 |
| hide+show/name/or | 1 | 0 | 0 |
| hide+show/resi/single | 1 | 1 | 1 |
| hide+show/resn/single | 1 | 0 | 0 |
| hide/chain+hetatm/and+not | 1 | 1 | 1 |
| hide/chain+name/and | 1 | 0 | 1 |
| hide/chain/single | 1 | 1 | 1 |
| hide/chain/single+not | 1 | 1 | 1 |
| hide/hetatm+resn/and+not | 1 | 0 | 0 |
| hide/hetatm/single | 1 | 1 | 1 |
| hide/hetatm/single+not | 1 | 1 | 1 |
| hide/name/single | 1 | 1 | 1 |
| hide/resi/single | 1 | 0 | 0 |
| hide/resn/single | 1 | 0 | 0 |
| orient+select/chain+resi/and | 1 | 1 | 1 |
| orient+select/chain/single | 1 | 1 | 1 |
| orient+select/hetatm/single | 1 | 1 | 1 |
| orient+select/name/single | 1 | 1 | 1 |
| orient+select/resi/single | 1 | 1 | 1 |
| orient+select/resn/single | 1 | 1 | 1 |
| show/chain+hetatm/and+not | 1 | 0 | 0 |
| show/chain+name/and_or | 1 | 0 | 0 |
| show/chain+resi/and | 1 | 0 | 0 |
| show/chain+resn/and_or | 1 | 0 | 0 |
| show/chain/single | 2 | 2 | 2 |
| show/hetatm/single | 1 | 1 | 1 |
| show/name/single | 1 | 1 | 1 |
| show/resi/or | 1 | 0 | 0 |
| show/resi/single | 1 | 1 | 1 |
| show/resn/single | 1 | 0 | 0 |
| show/resn/single+not | 1 | 0 | 0 |

## no-grammar

- Outcomes: applied 25, not_applicable 0, apply_restored 0, apply_refused 0, no_plan 43, timeout 0.
- Prompt skew (live structure not the recorded one): 0 of 68.
- Latency: preview p50 5.7 s, p90 8.9 s; apply p50 1.0 s, p90 2.0 s.

### Every sample whose outcome differs

None: every sample has the offline outcome.

### By shape

| Shape | n | Offline | Integrated |
| --- | --- | --- | --- |
| and | 9 | 2 | 2 |
| and+not | 4 | 0 | 0 |
| and_or | 6 | 0 | 0 |
| or | 5 | 0 | 0 |
| single | 38 | 15 | 15 |
| single+not | 6 | 2 | 2 |

### By category

| Category | n | Offline | Integrated |
| --- | --- | --- | --- |
| color+select+show/chain+resi/and | 1 | 0 | 0 |
| color+select+show/chain+resn/and | 1 | 0 | 0 |
| color+select+show/chain/single | 1 | 0 | 0 |
| color+select+show/hetatm/single | 1 | 1 | 1 |
| color+select+show/name/single | 1 | 0 | 0 |
| color+select+show/resi/single+not | 1 | 0 | 0 |
| color+select+show/resn/single | 1 | 0 | 0 |
| color+select/chain+resi/and_or | 1 | 0 | 0 |
| color+select/chain+resn/and_or | 1 | 0 | 0 |
| color+select/chain/single | 1 | 1 | 1 |
| color+select/hetatm/single | 1 | 1 | 1 |
| color+select/name+resn/and_or | 1 | 0 | 0 |
| color+select/name/single | 1 | 0 | 0 |
| color+select/resi/single | 1 | 0 | 0 |
| color+select/resn/or | 1 | 0 | 0 |
| color+select/resn/single | 1 | 0 | 0 |
| color+select/resn/single+not | 1 | 0 | 0 |
| color+show/chain+resi/and | 1 | 0 | 0 |
| color/chain+hetatm/and+not | 1 | 0 | 0 |
| color/chain+name+resn/and_or | 1 | 0 | 0 |
| color/chain+name/and | 1 | 1 | 1 |
| color/chain+resi/and | 1 | 0 | 0 |
| color/chain/or | 1 | 0 | 0 |
| color/chain/single | 1 | 0 | 0 |
| color/chain/single+not | 1 | 0 | 0 |
| color/hetatm/single | 1 | 0 | 0 |
| color/name/single | 1 | 0 | 0 |
| color/resi/single | 1 | 0 | 0 |
| color/resn/or | 1 | 0 | 0 |
| color/resn/single | 2 | 0 | 0 |
| hide+select/chain+hetatm/and | 1 | 1 | 1 |
| hide+select/chain/single | 1 | 1 | 1 |
| hide+select/name/single | 1 | 0 | 0 |
| hide+select/resi/single | 1 | 1 | 1 |
| hide+select/resn/single | 1 | 0 | 0 |
| hide+show/chain/single | 1 | 0 | 0 |
| hide+show/name/or | 1 | 0 | 0 |
| hide+show/resi/single | 1 | 0 | 0 |
| hide+show/resn/single | 1 | 0 | 0 |
| hide/chain+hetatm/and+not | 1 | 0 | 0 |
| hide/chain+name/and | 1 | 0 | 0 |
| hide/chain/single | 1 | 1 | 1 |
| hide/chain/single+not | 1 | 1 | 1 |
| hide/hetatm+resn/and+not | 1 | 0 | 0 |
| hide/hetatm/single | 1 | 1 | 1 |
| hide/hetatm/single+not | 1 | 1 | 1 |
| hide/name/single | 1 | 1 | 1 |
| hide/resi/single | 1 | 0 | 0 |
| hide/resn/single | 1 | 0 | 0 |
| orient+select/chain+resi/and | 1 | 0 | 0 |
| orient+select/chain/single | 1 | 0 | 0 |
| orient+select/hetatm/single | 1 | 1 | 1 |
| orient+select/name/single | 1 | 1 | 1 |
| orient+select/resi/single | 1 | 1 | 1 |
| orient+select/resn/single | 1 | 0 | 0 |
| show/chain+hetatm/and+not | 1 | 0 | 0 |
| show/chain+name/and_or | 1 | 0 | 0 |
| show/chain+resi/and | 1 | 0 | 0 |
| show/chain+resn/and_or | 1 | 0 | 0 |
| show/chain/single | 2 | 1 | 1 |
| show/hetatm/single | 1 | 1 | 1 |
| show/name/single | 1 | 1 | 1 |
| show/resi/or | 1 | 0 | 0 |
| show/resi/single | 1 | 1 | 1 |
| show/resn/single | 1 | 0 | 0 |
| show/resn/single+not | 1 | 0 | 0 |
