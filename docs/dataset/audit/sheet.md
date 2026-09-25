# Label audit sheet

Fill in `verdict` (correct, wrong or unsure) and, where useful,
`note` for every line of `sheet.jsonl`. This file is for reading;
only `sheet.jsonl` is scored.

A label is WRONG when either of these holds:

1. The plan does not do what the intent asks on this structure: the
   wrong atoms, colour or representation, or an effect the intent did
   not ask for, or a requested effect missing.
2. The intent's wording would lead a structural biologist to expect
   something other than what the plan does -- for example `residues 1
   to 4` on a structure where that range spans an insertion code, or
   `hetero atoms` where the reader would not expect water to count.

Mark UNSURE only when you cannot decide; say why in the note.
Otherwise mark CORRECT.

## 1. `hetatm_and_states_01455`

**Intent:** Show chain B as slice.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
show slice, chain B
```

Selection counts: none

Not checked by the oracle: unobservable_representation:slice

## 2. `everything_three_chains_00390`

**Intent:** Hide the lines representation for chain A and ALA residues.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
states: 3
alternate locations: A1A:CB, A2:CB
```

**Plan:**

```
hide lines, chain A and resn ALA
```

Selection counts: none

Not checked by the oracle: nothing

## 3. `everything_three_chains_03854`

**Intent:** Select chain A and ALA residues and color it splitpea.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
states: 3
alternate locations: A1A:CB, A2:CB
```

**Plan:**

```
select copilot_sel0559, chain A and resn ALA
color splitpea, copilot_sel0559
```

Selection counts: [['copilot_sel0559', 6]]

Not checked by the oracle: nothing

## 4. `hetatm_and_states_03509`

**Intent:** Color SER residues xenon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
color xenon, resn SER
```

Selection counts: none

Not checked by the oracle: nothing

## 5. `everything_three_chains_00315`

**Intent:** Select hetero atoms, color it green and show it as cartoon.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
states: 3
alternate locations: A1A:CB, A2:CB
```

**Plan:**

```
select copilot_sel0483, hetatm
color green, copilot_sel0483
show cartoon, copilot_sel0483
```

Selection counts: [['copilot_sel0483', 6]]

Not checked by the oracle: nothing

## 6. `insertion_codes_02054`

**Intent:** Show not GLY residues as surface.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
show surface, not resn GLY
```

Selection counts: none

Not checked by the oracle: nothing

## 7. `single_chain_hetatm_01620`

**Intent:** Select chain A and GLY residues and color it limon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0445, chain A and resn GLY
color limon, copilot_sel0445
```

Selection counts: [['copilot_sel0445', 4]]

Not checked by the oracle: nothing

## 8. `everything_small_00881`

**Intent:** Show chain A and CA atoms or chain B as surface.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show surface, chain A and name CA or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 9. `altloc_and_hetatm_02918`

**Intent:** Select O atoms, color it uranium and show it as sticks.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
select copilot_sel0333, name O
color uranium, copilot_sel0333
show sticks, copilot_sel0333
```

Selection counts: [['copilot_sel0333', 4]]

Not checked by the oracle: nothing

## 10. `altloc_and_hetatm_03555`

**Intent:** Select chain A and not hetero atoms and color it orange.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
select copilot_sel0445, chain A and not hetatm
color orange, copilot_sel0445
```

Selection counts: [['copilot_sel0445', 18]]

Not checked by the oracle: nothing

## 11. `three_chains_00209`

**Intent:** Select chain A and N atoms and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain C: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0413, chain A and name N
hide lines, copilot_sel0413
```

Selection counts: [['copilot_sel0413', 4]]

Not checked by the oracle: nothing

## 12. `everything_small_01399`

**Intent:** Show chain A and O atoms as ribbon, then hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show ribbon, chain A and name O
hide lines, chain A and name O
```

Selection counts: none

Not checked by the oracle: nothing

## 13. `single_chain_hetatm_03844`

**Intent:** Show ZN residues as cartoon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
show cartoon, resn ZN
```

Selection counts: none

Not checked by the oracle: nothing

## 14. `two_states_00882`

**Intent:** Show chain A and VAL residues as ribbon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: none
```

**Plan:**

```
show ribbon, chain A and resn VAL
```

Selection counts: none

Not checked by the oracle: nothing

## 15. `altloc_and_states_03623`

**Intent:** Show not VAL residues as nonbonded.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: A1:CB
```

**Plan:**

```
show nonbonded, not resn VAL
```

Selection counts: none

Not checked by the oracle: unobservable_representation:nonbonded

## 16. `single_chain_hetatm_00551`

**Intent:** Select chain A and not hetero atoms and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0437, chain A and not hetatm
orient copilot_sel0437
```

Selection counts: [['copilot_sel0437', 16]]

Not checked by the oracle: camera_view

## 17. `bonded_backbone_00183`

**Intent:** Select chain A and color it olive.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0003, chain A
color olive, copilot_sel0003
```

Selection counts: [['copilot_sel0003', 16]]

Not checked by the oracle: nothing

## 18. `altloc_pair_00355`

**Intent:** Color VAL residues samarium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: A1:CB
```

**Plan:**

```
color samarium, resn VAL
```

Selection counts: none

Not checked by the oracle: nothing

## 19. `hetatm_and_states_00032`

**Intent:** Select chain A and VAL residues and color it deepsalmon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0495, chain A and resn VAL
color deepsalmon, copilot_sel0495
```

Selection counts: [['copilot_sel0495', 4]]

Not checked by the oracle: nothing

## 20. `everything_small_02789`

**Intent:** Show chain A and CA atoms or chain B as ribbon.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show ribbon, chain A and name CA or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 21. `altloc_and_hetatm_03342`

**Intent:** Color chain A and not hetero atoms lightteal.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
color lightteal, chain A and not hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 22. `two_chains_01650`

**Intent:** Select chain A or chain B and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0413, chain A or chain B
hide lines, copilot_sel0413
```

Selection counts: [['copilot_sel0413', 32]]

Not checked by the oracle: nothing

## 23. `hetatm_and_states_03432`

**Intent:** Color GLY residues tin.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
color tin, resn GLY
```

Selection counts: none

Not checked by the oracle: nothing

## 24. `hetatm_and_states_01056`

**Intent:** Select hetero atoms, color it fluorine and show it as nb_spheres.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0419, hetatm
color fluorine, copilot_sel0419
show nb_spheres, copilot_sel0419
```

Selection counts: [['copilot_sel0419', 4]]

Not checked by the oracle: nothing

## 25. `altloc_and_hetatm_00505`

**Intent:** Color not VAL residues gallium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
color gallium, not resn VAL
```

Selection counts: none

Not checked by the oracle: nothing

## 26. `everything_four_chains_03798`

**Intent:** Color not chain B gallium.

**Structure:**

```
chain A: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain D: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
color gallium, not chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 27. `two_chains_01251`

**Intent:** Select not chain B and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0350, not chain B
hide lines, copilot_sel0350
```

Selection counts: [['copilot_sel0350', 16]]

Not checked by the oracle: nothing

## 28. `insertion_and_hetatm_00528`

**Intent:** Show hetero atoms as nb_spheres, then hide its spheres representation.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
show nb_spheres, hetatm
hide spheres, hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 29. `three_chains_01140`

**Intent:** Hide the volume representation for residues 1 to 3.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain C: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
hide volume, resi 1-3
```

Selection counts: none

Not checked by the oracle: unobservable_representation:volume

## 30. `hetatm_and_states_00357`

**Intent:** Select chain A and not hetero atoms and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0480, chain A and not hetatm
hide lines, copilot_sel0480
```

Selection counts: [['copilot_sel0480', 16]]

Not checked by the oracle: nothing

## 31. `two_chains_02385`

**Intent:** Select chain A and C atoms, color it blue and show it as labels.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0395, chain A and name C
color blue, copilot_sel0395
show labels, copilot_sel0395
```

Selection counts: [['copilot_sel0395', 4]]

Not checked by the oracle: nothing

## 32. `insertion_codes_00623`

**Intent:** Select GLY residues, color it tv_orange and show it as spheres.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0164, resn GLY
color tv_orange, copilot_sel0164
show spheres, copilot_sel0164
```

Selection counts: [['copilot_sel0164', 4]]

Not checked by the oracle: nothing

## 33. `two_states_03376`

**Intent:** Select chain A and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0015, chain A
orient copilot_sel0015
```

Selection counts: [['copilot_sel0015', 16]]

Not checked by the oracle: camera_view

## 34. `everything_four_chains_00674`

**Intent:** Show chain A or chain B as cartoon, then hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain D: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show cartoon, chain A or chain B
hide lines, chain A or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 35. `everything_three_chains_01421`

**Intent:** Hide the lines representation for N atoms.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
states: 3
alternate locations: A1A:CB, A2:CB
```

**Plan:**

```
hide lines, name N
```

Selection counts: none

Not checked by the oracle: nothing

## 36. `bonded_two_chains_00320`

**Intent:** Select O atoms, color it palegreen and show it as sticks.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0311, name O
color palegreen, copilot_sel0311
show sticks, copilot_sel0311
```

Selection counts: [['copilot_sel0311', 8]]

Not checked by the oracle: nothing

## 37. `four_chains_01130`

**Intent:** Hide the lines representation for chain A and O atoms or chain B.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain C: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain D: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
hide lines, chain A and name O or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 38. `single_chain_hetatm_03110`

**Intent:** Color chain A and not hetero atoms rutherfordium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
color rutherfordium, chain A and not hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 39. `single_chain_hetatm_03126`

**Intent:** Select ZN atoms and hide its spheres representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0330, name ZN
hide spheres, copilot_sel0330
```

Selection counts: [['copilot_sel0330', 1]]

Not checked by the oracle: nothing

## 40. `hetatm_and_states_01337`

**Intent:** Select chain A and VAL residues and color it californium, then select chain A and C atoms and show it as nb_spheres.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0506, chain A and resn VAL
select copilot_sel0507, chain A and name C
color californium, copilot_sel0506
show nb_spheres, copilot_sel0507
```

Selection counts: [['copilot_sel0506', 4], ['copilot_sel0507', 4]]

Not checked by the oracle: nothing

## 41. `altloc_and_states_03776`

**Intent:** Select ALA residues, color it nickel and show it as cartoon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: A1:CB
```

**Plan:**

```
select copilot_sel0143, resn ALA
color nickel, copilot_sel0143
show cartoon, copilot_sel0143
```

Selection counts: [['copilot_sel0143', 6]]

Not checked by the oracle: nothing

## 42. `everything_three_chains_02376`

**Intent:** Show LEU residues or CA atoms as nb_spheres.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 901 ZN (het), 902 HOH (het)
states: 3
alternate locations: A1A:CB, A2:CB
```

**Plan:**

```
show nb_spheres, resn LEU or name CA
```

Selection counts: none

Not checked by the oracle: nothing

## 43. `everything_four_chains_00523`

**Intent:** Show chain A and O atoms or chain B as labels, then hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain D: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show labels, chain A and name O or chain B
hide lines, chain A and name O or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 44. `everything_four_chains_02432`

**Intent:** Select O atoms and hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain C: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
chain D: 1A ALA, 2A SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
select copilot_sel0439, name O
hide lines, copilot_sel0439
```

Selection counts: [['copilot_sel0439', 28]]

Not checked by the oracle: nothing

## 45. `longer_chain_02652`

**Intent:** Show residue 1 as sticks, then hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 7 SER, 8 GLY
states: 1
alternate locations: none
```

**Plan:**

```
show sticks, resi 1
hide lines, resi 1
```

Selection counts: none

Not checked by the oracle: nothing

## 46. `single_chain_hetatm_03418`

**Intent:** Select not SER residues and color it palegreen.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0385, not resn SER
color palegreen, copilot_sel0385
```

Selection counts: [['copilot_sel0385', 13]]

Not checked by the oracle: nothing

## 47. `longer_chain_02306`

**Intent:** Color chain A and CA atoms deuterium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 5 LEU, 6 ALA, 7 SER, 8 GLY
states: 1
alternate locations: none
```

**Plan:**

```
color deuterium, chain A and name CA
```

Selection counts: none

Not checked by the oracle: nothing

## 48. `two_chains_01534`

**Intent:** Show not chain B as labels, then hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
show labels, not chain B
hide lines, not chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 49. `altloc_pair_02473`

**Intent:** Show chain A and N atoms as ribbon.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: A1:CB
```

**Plan:**

```
show ribbon, chain A and name N
```

Selection counts: none

Not checked by the oracle: nothing

## 50. `insertion_and_hetatm_03847`

**Intent:** Select chain A, color it phosphorus and show it as cartoon.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0018, chain A
color phosphorus, copilot_sel0018
show cartoon, copilot_sel0018
```

Selection counts: [['copilot_sel0018', 17]]

Not checked by the oracle: nothing
