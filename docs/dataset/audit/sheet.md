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

## 1. `hetatm_and_states_02369`

**Intent:** Show chain A and ZN atoms or chain B as labels.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
show labels, chain A and name ZN or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 2. `everything_three_chains_00854`

**Intent:** Select chain A and orient the view on it.

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
select copilot_sel0016, chain A
orient copilot_sel0016
```

Selection counts: [['copilot_sel0016', 26]]

Not checked by the oracle: camera_view

## 3. `four_chains_00739`

**Intent:** Show SER residues or N atoms as spheres.

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
show spheres, resn SER or name N
```

Selection counts: none

Not checked by the oracle: nothing

## 4. `insertion_and_hetatm_00231`

**Intent:** Show not hetero atoms as nb_spheres, then hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
show nb_spheres, not hetatm
hide lines, not hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 5. `everything_three_chains_00793`

**Intent:** Color chain A or chain B francium.

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
color francium, chain A or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 6. `insertion_codes_03806`

**Intent:** Color not GLY residues bismuth.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
color bismuth, not resn GLY
```

Selection counts: none

Not checked by the oracle: nothing

## 7. `single_chain_hetatm_03046`

**Intent:** Color not SER residues chlorine.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
color chlorine, not resn SER
```

Selection counts: none

Not checked by the oracle: nothing

## 8. `everything_small_01326`

**Intent:** Show not chain B as dots.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
show dots, not chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 9. `altloc_and_hetatm_03004`

**Intent:** Show hetero atoms as ellipsoids.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
show ellipsoids, hetatm
```

Selection counts: none

Not checked by the oracle: unobservable_representation:ellipsoids

## 10. `altloc_and_hetatm_03578`

**Intent:** Color not hetero atoms indium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
color indium, not hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 11. `three_chains_02337`

**Intent:** Hide the volume representation for chain A and N atoms.

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
hide volume, chain A and name N
```

Selection counts: none

Not checked by the oracle: unobservable_representation:volume

## 12. `everything_small_01904`

**Intent:** Hide the spheres representation for chain A.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
hide spheres, chain A
```

Selection counts: none

Not checked by the oracle: nothing

## 13. `three_chains_01854`

**Intent:** Select chain A and N atoms and color it gallium.

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
select copilot_sel0407, chain A and name N
color gallium, copilot_sel0407
```

Selection counts: [['copilot_sel0407', 4]]

Not checked by the oracle: nothing

## 14. `two_states_03708`

**Intent:** Select chain A and color it rhodium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0003, chain A
color rhodium, copilot_sel0003
```

Selection counts: [['copilot_sel0003', 16]]

Not checked by the oracle: nothing

## 15. `altloc_and_states_03684`

**Intent:** Show chain A and C atoms as nb_spheres.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: A1:CB
```

**Plan:**

```
show nb_spheres, chain A and name C
```

Selection counts: none

Not checked by the oracle: nothing

## 16. `single_chain_hetatm_02082`

**Intent:** Select N atoms and color it deepblue.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0282, name N
color deepblue, copilot_sel0282
```

Selection counts: [['copilot_sel0282', 4]]

Not checked by the oracle: nothing

## 17. `bonded_backbone_00518`

**Intent:** Select residues 1 to 4 and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0098, resi 1-4
hide lines, copilot_sel0098
```

Selection counts: [['copilot_sel0098', 16]]

Not checked by the oracle: nothing

## 18. `altloc_pair_00503`

**Intent:** Color residue 3 americium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: A1:CB
```

**Plan:**

```
color americium, resi 3
```

Selection counts: none

Not checked by the oracle: nothing

## 19. `hetatm_and_states_00858`

**Intent:** Select ALA residues or ZN atoms and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0589, resn ALA or name ZN
orient copilot_sel0589
```

Selection counts: [['copilot_sel0589', 10]]

Not checked by the oracle: camera_view

## 20. `everything_small_03274`

**Intent:** Color GLY residues or N atoms skyblue.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
color skyblue, resn GLY or name N
```

Selection counts: none

Not checked by the oracle: nothing

## 21. `altloc_and_hetatm_03377`

**Intent:** Select ZN atoms and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
select copilot_sel0352, name ZN
orient copilot_sel0352
```

Selection counts: [['copilot_sel0352', 1]]

Not checked by the oracle: camera_view

## 22. `two_chains_03689`

**Intent:** Show not chain B as surface.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
show surface, not chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 23. `insertion_and_hetatm_00185`

**Intent:** Select hetero atoms and color it radium.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0364, hetatm
color radium, copilot_sel0364
```

Selection counts: [['copilot_sel0364', 1]]

Not checked by the oracle: nothing

## 24. `hetatm_and_states_01713`

**Intent:** Show chain A and VAL residues as spheres.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
show spheres, chain A and resn VAL
```

Selection counts: none

Not checked by the oracle: nothing

## 25. `altloc_and_hetatm_00520`

**Intent:** Select not VAL residues and hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: A1:CB
```

**Plan:**

```
select copilot_sel0415, not resn VAL
hide lines, copilot_sel0415
```

Selection counts: [['copilot_sel0415', 15]]

Not checked by the oracle: nothing

## 26. `everything_small_00238`

**Intent:** Hide the volume representation for chain A and not hetero atoms.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: A1A:CB
```

**Plan:**

```
hide volume, chain A and not hetatm
```

Selection counts: none

Not checked by the oracle: unobservable_representation:volume

## 27. `two_chains_03333`

**Intent:** Select not chain B and color it tellurium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0344, not chain B
color tellurium, copilot_sel0344
```

Selection counts: [['copilot_sel0344', 16]]

Not checked by the oracle: nothing

## 28. `insertion_and_hetatm_01755`

**Intent:** Select residue 2 and color it calcium.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het)
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0024, resi 2
color calcium, copilot_sel0024
```

Selection counts: [['copilot_sel0024', 4]]

Not checked by the oracle: nothing

## 29. `three_chains_02863`

**Intent:** Show GLY residues as cartoon, then hide its lines representation.

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
show cartoon, resn GLY
hide lines, resn GLY
```

Selection counts: none

Not checked by the oracle: nothing

## 30. `hetatm_and_states_01128`

**Intent:** Hide the lines representation for chain A and not hetero atoms.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
hide lines, chain A and not hetatm
```

Selection counts: none

Not checked by the oracle: nothing

## 31. `two_states_00564`

**Intent:** Select SER residues and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0183, resn SER
orient copilot_sel0183
```

Selection counts: [['copilot_sel0183', 4]]

Not checked by the oracle: camera_view

## 32. `insertion_codes_02956`

**Intent:** Select ALA residues or C atoms and hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0392, resn ALA or name C
hide lines, copilot_sel0392
```

Selection counts: [['copilot_sel0392', 7]]

Not checked by the oracle: nothing

## 33. `everything_four_chains_00939`

**Intent:** Color chain A and ZN residues calcium.

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
color calcium, chain A and resn ZN
```

Selection counts: none

Not checked by the oracle: nothing

## 34. `everything_three_chains_01880`

**Intent:** Color residue 2 limegreen.

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
color limegreen, resi 2
```

Selection counts: none

Not checked by the oracle: nothing

## 35. `bonded_two_chains_00732`

**Intent:** Show chain A and N atoms or chain B as mesh.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
show mesh, chain A and name N or chain B
```

Selection counts: none

Not checked by the oracle: nothing

## 36. `four_chains_02025`

**Intent:** Select chain A and GLY residues and orient the view on it.

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
select copilot_sel0414, chain A and resn GLY
orient copilot_sel0414
```

Selection counts: [['copilot_sel0414', 4]]

Not checked by the oracle: camera_view

## 37. `three_chains_00755`

**Intent:** Select chain A and GLY residues, color it cerium and show it as labels.

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
select copilot_sel0395, chain A and resn GLY
color cerium, copilot_sel0395
show labels, copilot_sel0395
```

Selection counts: [['copilot_sel0395', 4]]

Not checked by the oracle: nothing

## 38. `three_chains_00810`

**Intent:** Select not chain B and hide its lines representation.

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
select copilot_sel0371, not chain B
hide lines, copilot_sel0371
```

Selection counts: [['copilot_sel0371', 32]]

Not checked by the oracle: nothing

## 39. `hetatm_and_states_02109`

**Intent:** Select HOH residues and hide its spheres representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL, 901 ZN (het), 902 HOH (het)
states: 2
alternate locations: none
```

**Plan:**

```
select copilot_sel0205, resn HOH
hide spheres, copilot_sel0205
```

Selection counts: [['copilot_sel0205', 2]]

Not checked by the oracle: nothing

## 40. `altloc_and_states_03886`

**Intent:** Show CB atoms as cartoon, then hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 2
alternate locations: A1:CB
```

**Plan:**

```
show cartoon, name CB
hide lines, name CB
```

Selection counts: none

Not checked by the oracle: nothing

## 41. `everything_three_chains_02883`

**Intent:** Select ALA residues and orient the view on it.

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
select copilot_sel0186, resn ALA
orient copilot_sel0186
```

Selection counts: [['copilot_sel0186', 14]]

Not checked by the oracle: camera_view

## 42. `everything_four_chains_00697`

**Intent:** Hide the lines representation for residues 1 to 4.

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
hide lines, resi 1-4
```

Selection counts: none

Not checked by the oracle: nothing

## 43. `everything_four_chains_02848`

**Intent:** Select chain A and CA atoms and hide its lines representation.

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
select copilot_sel0608, chain A and name CA
hide lines, copilot_sel0608
```

Selection counts: [['copilot_sel0608', 6]]

Not checked by the oracle: nothing

## 44. `minimal_single_chain_01688`

**Intent:** Select chain A and ALA residues and orient the view on it.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0351, chain A and resn ALA
orient copilot_sel0351
```

Selection counts: [['copilot_sel0351', 4]]

Not checked by the oracle: camera_view

## 45. `three_chains_01183`

**Intent:** Show O atoms as spheres.

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
show spheres, name O
```

Selection counts: none

Not checked by the oracle: nothing

## 46. `minimal_single_chain_00993`

**Intent:** Hide the lines representation for residue 2.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
hide lines, resi 2
```

Selection counts: none

Not checked by the oracle: nothing

## 47. `two_chains_03559`

**Intent:** Select chain A or chain B and color it ruthenium.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
chain B: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
select copilot_sel0407, chain A or chain B
color ruthenium, copilot_sel0407
```

Selection counts: [['copilot_sel0407', 32]]

Not checked by the oracle: nothing

## 48. `altloc_pair_02647`

**Intent:** Show chain A and SER residues as nb_spheres, then hide its lines representation.

**Structure:**

```
chain A: 1 ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: A1:CB
```

**Plan:**

```
show nb_spheres, chain A and resn SER
hide lines, chain A and resn SER
```

Selection counts: none

Not checked by the oracle: nothing

## 49. `insertion_codes_02330`

**Intent:** Show chain A as sticks, then hide its lines representation.

**Structure:**

```
chain A: 1A ALA, 2 SER, 3 GLY, 4 VAL
states: 1
alternate locations: none
```

**Plan:**

```
show sticks, chain A
hide lines, chain A
```

Selection counts: none

Not checked by the oracle: nothing

## 50. `everything_four_chains_03905`

**Intent:** Show chain A and not hetero atoms as mesh.

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
show mesh, chain A and not hetatm
```

Selection counts: none

Not checked by the oracle: nothing
