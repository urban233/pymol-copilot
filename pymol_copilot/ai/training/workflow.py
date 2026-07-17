# workflow.py
"""
NeMo Data Designer synthesis loop for the cBioMOL PyMOL copilot dataset.

Design note on scope
--------------------
The real tool_schemas.py registers 22 tools across six categories
(loading, representation, selection/annotation, measurement, alignment,
export). The copilot is powered by a LangGraph agent whose planner model
must produce a *complete sequential plan* — potentially 10–25 tool calls —
from a single user prompt.

This file samples only the parameters a real user WOULD say out loud
(PDB IDs, representation style, color, chain letter, background, label
type, file path, residue names, distances). Parameters a user would NOT
specify (atom names, exact residue-id lists, measurement/object names,
radii, cutoffs) are synthesized deterministically in build_conversations.py
from a per-row seeded RNG, then validated against the JSON Schemas in
tool_schemas.py (including the nested atom-selector object).

Each row is assigned a "scenario" — a named, realistic multi-tool workflow.
27 scenarios are defined below; together they exercise all 22 tools many
times across a wide range of complexity (1 tool to 25 tools).

Scenario categories
-------------------
  Lightweight (1–4 tools, weight ~0.30): fast, common single-purpose ops.
  Medium (4–8 tools, weight ~0.35): multi-step but routine lab tasks.
  Deep (8–25 tools, weight ~0.35): complex workflows the LangGraph agent
      must plan without truncation — the model must never have seen a
      ceiling below 25 calls.

Add more scenarios by:
  (a) adding an entry to SCENARIO_WEIGHTS,
  (b) adding a branch to the Jinja prompt template,
  (c) adding a matching dispatch function in build_conversations.py.
"""
import os

import data_designer.config as dd
from data_designer.interface import DataDesigner

# ---------------------------------------------------------------------------
# 1. Custom Infrastructure Provider Registration (OpenRouter Free Tier)
# ---------------------------------------------------------------------------
openrouter_provider = dd.ModelProvider(
    name="openrouter_endpoint",
    endpoint="https://openrouter.ai/api/v1",
    provider_type="openai",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

model_configs = [
    dd.ModelConfig(
        alias="nemotron-ultra",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        provider="openrouter_endpoint",
        inference_parameters=dd.ChatCompletionInferenceParams(
            temperature=0.8, max_tokens=400, max_parallel_requests=4
        ),
    ),
    dd.ModelConfig(
        alias="hy3-grounded",
        model="tencent/hy3:free",
        provider="openrouter_endpoint",
        inference_parameters=dd.ChatCompletionInferenceParams(
            temperature=0.5, max_tokens=400, max_parallel_requests=4
        ),
    ),
    dd.ModelConfig(
        alias="gemma-fast",
        model="google/gemma-4-26b-a4b-it:free",
        provider="openrouter_endpoint",
        inference_parameters=dd.ChatCompletionInferenceParams(
            temperature=0.7, max_tokens=400, max_parallel_requests=4
        ),
    ),
]

data_designer = DataDesigner(model_providers=[openrouter_provider])
config_builder = dd.DataDesignerConfigBuilder(model_configs=model_configs)

# ---------------------------------------------------------------------------
# 2. Unique row identifier
# ---------------------------------------------------------------------------
# Doubles as the seed for the deterministic "tool-only" parameter synthesis
# in build_conversations.py, and as the required unique id_field for NeMo
# Curator dedup (never use a sampled categorical like pdb_id for that).
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="row_uid", sampler_type=dd.SamplerType.UUID
    )
)

# ---------------------------------------------------------------------------
# 3. Scenario selector
# ---------------------------------------------------------------------------
# Weights are designed so that:
#   - Lightweight single-purpose ops dominate (~30%) — they are the most
#     common real-world requests and must not be underrepresented.
#   - Medium multi-step workflows cover ~35% of the dataset.
#   - Deep complex workflows (8–25 tool calls) cover ~35%.
#     This forces the model to plan long sequences without truncating.
# All weights must sum to exactly 1.0 (enforced by the assert below).
SCENARIO_WEIGHTS = {
    # ------------------------------------------------------------------ Light
    "load_and_visualize": 0.07,
    "load_only": 0.03,
    "chain_coloring": 0.03,
    "secondary_structure_and_background": 0.03,
    "hydrogens_workflow": 0.02,
    "active_site_selection": 0.03,
    "local_file_workflow": 0.03,
    "housekeeping_workflow": 0.02,
    "chain_isolation_export": 0.02,
    # ----------------------------------------------------------------- Medium
    "binding_site_proximity": 0.04,
    "measure_distance_workflow": 0.04,
    "measure_angle_workflow": 0.03,
    "contacts_workflow": 0.04,
    "align_structures_workflow": 0.04,
    "export_image_and_session": 0.04,
    # ------------------------------------------------------------------- Deep
    "antibody_cdr_analysis": 0.05,
    "comparative_binding_site": 0.05,
    "full_active_site_workflow": 0.05,
    "multi_chain_coloring_export": 0.04,
    "ligand_environment_deep": 0.05,
    "interface_analysis": 0.05,
    "structure_comparison_full": 0.05,
    "publication_figure": 0.04,
    "batch_measurement_workflow": 0.04,
    "hydrogen_bond_network": 0.04,
    "multi_structure_session": 0.04,
    "cryo_em_refinement_view": 0.04,
}
assert abs(sum(SCENARIO_WEIGHTS.values()) - 1.0) < 1e-6

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="scenario",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=list(SCENARIO_WEIGHTS.keys()),
            weights=list(SCENARIO_WEIGHTS.values()),
        ),
    )
)

# ---------------------------------------------------------------------------
# 4. Samplers for "user-mentioned" parameters
# ---------------------------------------------------------------------------

# Extended PDB ID catalogue — covers a wide range of structural biology:
#   antibodies, ribosomes, ion channels, membrane proteins, GroEL, kinases,
#   virus capsids, allosteric proteins, and classic references.
PDB_IDS = [
    # Classic references
    "7BZ5", "1BL8", "1A2U", "4PZB", "6LU7", "3HHR", "1QLY", "6VXX",
    "1HHO", "2RH1", "1AKE", "4HHB", "1CRN", "6M0J", "3POZ", "1IGT",
    "2GS6", "1STP", "5XNL", "1UBQ", "3EML", "1XQ8", "6YB7", "1LYZ",
    "2VGB", "4EY7", "1B0Y",
    # Antibody Fab fragments (multi-chain, CDR loop analysis)
    "6XC2", "5XSZ",
    # Ribosomes (large RNA + protein assemblies)
    "4V9D", "7K00",
    # Ion channels (multiple chains, cofactors)
    "6J8J", "2ZW3",
    # Large kinase complexes
    "6S9T", "4GH8",
    # Chaperonin GroEL ring (7-fold symmetry, deep scenario)
    "1AON", "1G9I",
    # Membrane proteins
    "3SN6", "6CMO",
    # Virus-capsid subunit
    "1YHT", "4HVP",
    # Allosteric haemoglobin T-state
    "2HHB",
    # Adenylate kinase closed state (for comparative workflow)
    "4AKE",
    # Thrombin with inhibitor (hydrogen-bond network scenario)
    "2BXT",
    # EGFR kinase with ATP analog
    "1IEP",
]

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="pdb_id",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=PDB_IDS),
    )
)
# Independently sampled second PDB ID for scenarios needing two structures.
# build_conversations.py re-rolls deterministically if it collides with
# pdb_id.
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="pdb_id_secondary",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=PDB_IDS),
    )
)
# Third PDB ID for the multi_structure_session scenario (3 structures).
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="pdb_id_tertiary",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=PDB_IDS),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="representation_style",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "cartoon", "sticks", "spheres", "surface",
                "ribbon", "lines", "dots",
            ]
        ),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="pymol_color",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "marine", "forest", "firebrick", "wheat", "slate",
                "hotpink", "orange", "purple", "teal", "yellow",
                "spectrum", "chainbows", "cyan", "red", "blue",
                "green", "magenta", "salmon", "limon", "brightorange",
            ]
        ),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="background_color",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=["white", "black", "grey"]),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="chain_letter",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=["A", "B", "C", "D"]),
    )
)

# Second chain letter for cross-chain operations (interface analysis etc.)
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="chain_letter_b",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=["B", "C", "D", "E"]),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="label_type",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "residue_name", "residue_number", "chain", "b_factor",
            ]
        ),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="file_path_stub",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "~/structures/sample_complex.pdb",
                "/data/cryoem/receptor_model.cif",
                "./local_files/ligand_bound_state.mol2",
                "/home/user/downloads/homology_model.pdb",
                "~/Desktop/refined_structure.cif",
            ]
        ),
    )
)

config_builder.add_column(
    dd.SamplerColumnConfig(
        name="persona",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "terse lab-shorthand",
                "polite full-sentence",
                "typo-prone rushed",
                "detailed structural-biology jargon",
            ]
        ),
    )
)

# Catalytic/binding-pocket residue name (3-letter code) for deep scenarios
# that reference residues by chemical identity rather than sequence number.
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="residue_name_3letter",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "HIS", "ASP", "SER", "CYS", "GLU",
                "LYS", "ARG", "TYR", "TRP", "ASN",
            ]
        ),
    )
)

# Short (H-bond / polar contact) distance in Angstroms
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="radius_angstrom_small",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=["3.0", "3.5", "4.0"]),
    )
)

# Larger (binding-site shell) distance in Angstroms
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="radius_angstrom_large",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(values=["5.0", "6.0", "8.0"]),
    )
)

# ---------------------------------------------------------------------------
# 5. Structural Biology Prompt Generation via OpenRouter Free Node
# ---------------------------------------------------------------------------
PROMPT_SYNTHESIS_TEMPLATE = """\
You are an experimental structural biologist interacting with a PyMOL
copilot. The copilot is a LangGraph agent that generates a complete
sequential plan of tool calls from your single request — it is NOT a
chatbot. You should write a single, complete multi-step request as you
would actually type it.

Formulate a single natural-language request, written in a {{ persona }}
tone, for the following task. Only mention the specific details given
below — do NOT invent atom names, residue numbers, or exact technical
parameters; a real researcher would leave those to the assistant.
Do NOT mention code, JSON, tools, parameters, or schemas.
Output only the request phrase, nothing else.

{% if scenario == "load_and_visualize" %}
Load PDB structure {{ pdb_id }}, then display it as \
{{ representation_style }} colored {{ pymol_color }}.
{% elif scenario == "load_only" %}
Load PDB structure {{ pdb_id }}. Do not mention representation or color.
{% elif scenario == "chain_coloring" %}
Load PDB structure {{ pdb_id }} and color each chain a different color.
{% elif scenario == "secondary_structure_and_background" %}
Load PDB structure {{ pdb_id }}, show it as {{ representation_style }},
color it by secondary structure, and set the viewport background to
{{ background_color }}.
{% elif scenario == "hydrogens_workflow" %}
Load PDB structure {{ pdb_id }} and add missing hydrogen atoms to it.
{% elif scenario == "active_site_selection" %}
Load PDB structure {{ pdb_id }}, select the active-site residues in
chain {{ chain_letter }}, and label them by {{ label_type }}.
{% elif scenario == "local_file_workflow" %}
Load the local structure file at {{ file_path_stub }} and display it
as {{ representation_style }}.
{% elif scenario == "housekeeping_workflow" %}
Load PDB structures {{ pdb_id }} and {{ pdb_id_secondary }}, list
everything currently loaded, then remove one of them.
{% elif scenario == "chain_isolation_export" %}
Load PDB structure {{ pdb_id }}, isolate chain {{ chain_letter }},
and export just that chain's coordinates to a file.
{% elif scenario == "binding_site_proximity" %}
Load PDB structure {{ pdb_id }}, select the bound ligand(s), select
everything near the binding site, and show that region as
{{ representation_style }}.
{% elif scenario == "measure_distance_workflow" %}
Load PDB structure {{ pdb_id }} and measure the distance between two
specific atoms of interest (let the assistant pick reasonable atoms).
{% elif scenario == "measure_angle_workflow" %}
Load PDB structure {{ pdb_id }} and measure a bond angle at a residue
of interest.
{% elif scenario == "contacts_workflow" %}
Load PDB structure {{ pdb_id }}, select the ligand, and show all close
contacts between the ligand and the protein.
{% elif scenario == "align_structures_workflow" %}
Load PDB structures {{ pdb_id }} and {{ pdb_id_secondary }}, then
structurally align the second one onto the first.
{% elif scenario == "export_image_and_session" %}
Load PDB structure {{ pdb_id }}, display it as {{ representation_style }},
save a figure of the current view, and save the whole session so you can
come back to it later.
{% elif scenario == "antibody_cdr_analysis" %}
Load antibody structure {{ pdb_id }}, select each of the six CDR loops
(L1, L2, L3 on the light chain and H1, H2, H3 on the heavy chain)
individually, color each CDR loop a different color (using
{{ pymol_color }} as the overall palette direction), show contacts
between the CDR loops and the antigen, label all CDR residues with their
residue names, and save a ray-traced publication figure with a
{{ background_color }} background.
{% elif scenario == "comparative_binding_site" %}
Load PDB structures {{ pdb_id }} (reference) and {{ pdb_id_secondary }}
(alternative conformation), structurally align the second onto the first,
select the binding site in each structure (residues near any ligand),
measure three key distances in each binding site, export each binding site
selection as a PDB file, and save the aligned session.
{% elif scenario == "full_active_site_workflow" %}
Load PDB structure {{ pdb_id }}, select the catalytic triad residues
({{ residue_name_3letter }} and its partners) in chain {{ chain_letter }},
show those as sticks, label them by residue name, select all HETATM
within {{ radius_angstrom_small }} Å excluding water molecules, show the
ligand as sticks, measure the two most important active-site distances,
show contacts at {{ radius_angstrom_small }} Å between the catalytic
residues and the ligand, and save a session file.
{% elif scenario == "multi_chain_coloring_export" %}
Load PDB structure {{ pdb_id }}, show the whole complex as
{{ representation_style }}, color each chain a distinct color, select
chain {{ chain_letter }} individually and export it as a PDB file,
select chain {{ chain_letter_b }} and export it too, then save a session
with the current state.
{% elif scenario == "ligand_environment_deep" %}
Load PDB structure {{ pdb_id }}, select all HETATM records excluding
water to isolate the ligand, select all amino-acid residues within
{{ radius_angstrom_large }} Å of the ligand to define the binding pocket,
also select crystallographic waters within {{ radius_angstrom_small }} Å,
show the ligand as sticks, show the pocket as {{ representation_style }},
color the pocket residues by {{ pymol_color }}, show all contacts between
the ligand and pocket within {{ radius_angstrom_small }} Å, label the
pocket residues by residue name, export the pocket selection as a PDB
file, and save a ray-traced figure with {{ background_color }} background.
{% elif scenario == "interface_analysis" %}
Load the dimer structure {{ pdb_id }}, select chain {{ chain_letter }}
and chain {{ chain_letter_b }} separately, show contacts at the interface
(within {{ radius_angstrom_small }} Å across the two chains), measure
four specific cross-chain distances that look structurally interesting,
color chain {{ chain_letter }} as {{ pymol_color }} and chain
{{ chain_letter_b }} slate, set the background to {{ background_color }},
save a session, and export a ray-traced figure.
{% elif scenario == "structure_comparison_full" %}
Load the wild-type structure {{ pdb_id }} and the mutant/alternative
{{ pdb_id_secondary }}, structurally align the second onto the first,
select the active site in both structures (chain {{ chain_letter }},
residues near the catalytic {{ residue_name_3letter }}), measure three
distances in the wild-type active site and the same three in the mutant,
color the wild-type {{ pymol_color }} and the mutant firebrick, set the
background to {{ background_color }}, save a ray-traced comparison
figure, and save the session.
{% elif scenario == "publication_figure" %}
Load PDB structure {{ pdb_id }}, show as {{ representation_style }},
color by secondary structure, set the background to white, then select
all ligands and show them as sticks, select the binding-site pocket
(all residues within {{ radius_angstrom_large }} Å of the ligand),
color the pocket {{ pymol_color }}, show the pocket as sticks as well,
label all pocket residues by residue name, and export a high-resolution
ray-traced publication PNG.
{% elif scenario == "batch_measurement_workflow" %}
Load PDB structure {{ pdb_id }}, select four pairs of structurally
important residues in chain {{ chain_letter }} (including
{{ residue_name_3letter }} pairs), measure the distance for each pair,
label all measured residues with their residue names and numbers, and
save the session so all distance markers are preserved.
{% elif scenario == "hydrogen_bond_network" %}
Load PDB structure {{ pdb_id }}, add all missing hydrogen atoms, select
the likely hydrogen-bond donors in chain {{ chain_letter }} ({{ residue_name_3letter }}
and related residues), show contacts within {{ radius_angstrom_small }} Å
to map the H-bond network, label all donor residues by residue name,
show those residues as sticks, and export the selection as a PDB file.
{% elif scenario == "multi_structure_session" %}
Load three related PDB structures: {{ pdb_id }}, {{ pdb_id_secondary }},
and {{ pdb_id_tertiary }}. Structurally align the second and third onto
the first, color each structure a distinct color ({{ pymol_color }} for
the reference, and contrasting colors for the other two), show all three
as {{ representation_style }}, and save the combined session.
{% elif scenario == "cryo_em_refinement_view" %}
Load the local cryo-EM model at {{ file_path_stub }}, show the protein
backbone as cartoon, select the ligand and show it as sticks, color the
overall structure by chain, color the ligand {{ pymol_color }}, select
all residues within {{ radius_angstrom_large }} Å of the ligand to define
the density-supported environment, label those residues by residue name,
and save a ray-traced figure with {{ background_color }} background.
{% endif %}
"""

config_builder.add_column(
    dd.LLMTextColumnConfig(
        name="user_query",
        # nemotron-ultra produces the most structurally-aware paraphrases;
        # swap to 'hy3-grounded' or 'gemma-fast' for cost-sensitive runs.
        model_alias="nemotron-ultra",
        prompt=PROMPT_SYNTHESIS_TEMPLATE,
    )
)

# NOTE: the assistant-side ChatML/tool-call JSON is intentionally NOT built
# here. See build_conversations.py, which reads the raw generated rows,
# deterministically synthesizes the tool-only parameters per scenario, and
# validates the full call sequence against tool_schemas.TOOL_SCHEMAS_BY_NAME.
