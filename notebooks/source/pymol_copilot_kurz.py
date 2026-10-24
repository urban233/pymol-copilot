# Copyright 2026 PyMOL Copilot contributors.
# The German short version of the notebook, in the percent format;
# notebooks/build_notebook.py --source source/pymol_copilot_kurz.py
# --out pymol_copilot_kurz.ipynb turns it into the notebook. Its layout
# follows the course's own notebooks: many short cells, bullet points.
# ruff: noqa: E402

# %% [markdown]
# # PyMOL-Copilot: Sichere PyMOL-Befehle mit einem lokalen Sprachmodell
#
# **Autoren:** Martin Urban und Hannah Kullik

# %% [markdown]
# Inhalt:
#
# 1. **Problem**: PyMOL-Befehle aus **natürlicher Sprache** erzeugen
# 2. Eine **eingeschränkte Befehlssprache** als Sicherheitsnetz
# 3. **Datensatz**: per Programm erzeugt und von einem **Orakel** geprüft
# 4. **Fine-Tuning** eines kleinen Sprachmodells (Llama-3.2-1B) mit **LoRA**
# 5. **Evaluation**: Basismodell gegen feinabgestimmtes Modell
# 6. **Anwendung**: der Copilot in PyMOL
# 7. **Grenzen** und Ausblick

# %% [markdown]
# <img src="../assets/splash_screen.png" width="500px">

# %% [markdown]
# - Kurzfassung des ausführlichen (englischen) Notebooks `pymol_copilot.ipynb`
# - Notebook ist *ausgeführt* gespeichert: lesbar, ohne etwas zu starten
# - Rechenintensive Schritte (Datensatz erzeugen, Training, Evaluation) laufen hier **nicht**
#     - stattdessen: Laden der im Repository abgelegten Ergebnisse
# - Schnelle Schritte (Millisekunden) laufen live

# %%
"""Kernel vorbereiten: die Pakete des Repositorys einbinden."""

import sys
import warnings
from pathlib import Path

# Fortschrittsbalken des Tokenizers bräuchten ipywidgets
warnings.filterwarnings("ignore", message="IProgress not found")

# Hilfsfunktionen liegen neben dem Notebook im Ordner notebooks/
sys.path.insert(0, str(Path.cwd()))
import notebook_support as support

# Pakete des Repositorys (src/) importierbar machen
support.setup_paths()

# %% [markdown]
# ## 1 Problemstellung

# %% [markdown]
# - **PyMOL**: Molekülviewer für Proteinstrukturen, gesteuert über eine eigene Befehlssprache
# - Beispiele:
#     - `color red, chain A` färbt alle Atome von Kette A rot
#     - `show sticks, resn ZN` zeigt die Zink-Ionen als Stäbchen
# - Befehle schreiben erfordert Kenntnis der **Selektionssyntax**
# - Idee: Nutzer:in beschreibt den Wunsch in natürlicher Sprache, ein **LLM** schreibt die Befehle
# - Problem: ein allgemeines Chat-LLM ist hier **unsicher**
#     - die PyMOL-Sprache kann auch Python ausführen, Dateien laden und Plugins aufrufen
# - Ziel: ein **kleines, lokales** Modell, nichts verlässt den Rechner
# - Ausgabe des Modells: ein **Plan**, d.h. eine kurze Liste von PyMOL-Befehlen

# %% [markdown]
# ### 1.1 Ablauf einer Anfrage
# 1. **Snapshot**: die laufende PyMOL-Sitzung wird ausgelesen
# 2. **Strukturkarte**: der Snapshot als Text (Objekt, Atome, Farben, Darstellungen)
# 3. **Generierung**: das lokale LLM erhält Karte und Wunsch und schreibt den Plan
# 4. **Validierung**: der Plan wird
#     - geparst,
#     - von einer unabhängigen Policy geprüft und
#     - in einem *separaten* PyMOL-Prozess probeweise ausgeführt
#     - bei einem Fehler: höchstens zwei Reparaturversuche
# 5. **Freigabe**: Nutzer:in sieht die Befehle und die getroffenen Atome und bestätigt mit `copilot_apply`
# 6. **Anwenden**: die Sitzung wird vorher gesichert und bei einem Fehler wiederhergestellt
#
# - der *einzige gelernte* Teil ist das **Sprachmodell** in Schritt 3

# %% [markdown]
# ## 2 Eine eingeschränkte Befehlssprache

# %% [markdown]
# - nur **fünf Verben**: `select`, `color`, `show`, `hide`, `orient`
# - Selektionen aus **sechs Termen**: `chain`, `resi`, `resn`, `name`, `hetatm`, `polymer`
# - verknüpft mit `and`, `or` und `not`
# - alles andere wird **vor** der Ausführung abgelehnt
# - eigener Parser (`pmc_core.parser`): ungeprüfter Text wird *nie* an den Parser von PyMOL gegeben

# %%
from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.policy import evaluate_plan

beispiele = [
    "color red, chain A",
    "hide lines, chain B and not hetatm",
    "load /etc/passwd",
    "set sphere_scale, 2",
    "Color red, chain A",
]
for text in beispiele:
    ergebnis = parse_pml(text + "\n")
    if isinstance(ergebnis, ParseRejection):
        print(f"abgelehnt  {text!r:40} Grund: {ergebnis.category}")
    else:
        erlaubt = evaluate_plan(ergebnis).allowed
        print(f"geparst    {text!r:40} Policy erlaubt: {erlaubt}")

# %% [markdown]
# - Beachte: der Parser **normalisiert nichts**, z.B. keine Groß-/Kleinschreibung (`Color`)
#     - beim Normalisieren beginnt ein Parser, Text zu akzeptieren, an den niemand gedacht hat

# %% [markdown]
# ## 3 Datensatz

# %% [markdown]
# - Ein Modell lernt aus Beispielen: (Struktur, Wunsch, korrekter Plan)
# - Solche Beispiele von Nutzer:innen gibt es nicht
# - Von Hand oder von einem anderen LLM geschriebene Pläne können **falsch** sein
# - Daher wird jedes Beispiel **per Programm** erzeugt ("program-first"):
#     - der Plan wird per Code aufgezählt
#     - ein **Orakel** sagt sein Ergebnis voraus, *ohne* PyMOL
#     - der Plan wird in echtem PyMOL ausgeführt
#     - das Beispiel bleibt nur, wenn PyMOLs Ergebnis **exakt** der Vorhersage entspricht

# %% [markdown]
# ### 3.1 Synthetische Strukturen und Strukturkarte
# - 24 kleine, **synthetische** Proteine
#     - mehrere Ketten, Hetero-Atome (Zink, Wasser), mehrere Zustände, alternative Positionen, Insertion Codes
# - synthetisch mit Absicht: keine PDB-Daten, jedes Atom ist bekannt
# - das Modell sieht eine Struktur als **Strukturkarte** (Text), z.B.:

# %%
from pmc_core.card import render_for_runtime
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

# Ein Wunsch aus dem handgeprüften Gold-Set und seine Struktur
gold = support.load_jsonl("src/pmc_data/gold/gold_samples.jsonl")
beispiel = next(row for row in gold if row["sample_id"] == "gold_056")
spec = StructureSpec.from_dict(beispiel["structure"]["spec"])
snapshot = build_structure(spec)

anzahl_atome = sum(len(state.atoms) for state in snapshot.states)
print(f"Struktur '{spec.spec_id}' mit {anzahl_atome} Atomen")
print("Wunsch:", beispiel["intent"])
print()
karte = render_for_runtime(snapshot)
print("\n".join(karte.splitlines()[:10]))
print("...")

# %% [markdown]
# ### 3.2 Pläne aufzählen
# - `enumerate_plans` erzeugt je Struktur Pläne über alle Verben, Terme und Ausdrucksformen
# - jeder Plan erhält einen Wunsch aus einer **Satzvorlage**

# %%
from pmc_data.taxonomy import enumerate_plans

kandidaten = enumerate_plans(snapshot, seed=20260921)
plan = next(c for c in kandidaten if c.category.startswith("color+select"))

print(f"{len(kandidaten)} Kandidaten-Pläne für diese Struktur, z.B.:")
print("Wunsch:   ", plan.intent)
print("Kategorie:", plan.category)
print(plan.plan.render_pml(), end="")

# %% [markdown]
# ### 3.3 Das Orakel
# - sagt ohne PyMOL voraus:
#     - den Zustand nach dem Plan
#     - wie viele Atome jede Selektion trifft
# - lieber **ablehnen als raten**: was nicht vorhersagbar ist, wird benannt

# %%
from pmc_data.oracle import apply_plan

vorhersage = apply_plan(snapshot, plan.plan)
print("Atome je Selektion:  ", vorhersage.selection_counts)
print("Zustand vorhergesagt:", vorhersage.snapshot is not None)
print("Nicht geprüft:       ", vorhersage.unsupported or "nichts")

# %% [markdown]
# - jeder Versuch beim Erzeugen des Datensatzes ist damit ein **Differenztest**: Orakel gegen PyMOL
# - Ergebnis für 4.000 Versuche:

# %%
bericht = support.load_json("docs/dataset/linux-regeneration/report.json")
gruende: dict[str, int] = {}
for kategorie in bericht["categories"]:
    for grund, anzahl in kategorie["rejected_by_reason"].items():
        gruende[grund] = gruende.get(grund, 0) + anzahl

support.markdown_table(
    [
        "Versucht",
        "Behalten",
        "Abgelehnt",
        "Orakel lehnt Bewertung ab",
        "Ablehnungsgründe",
    ],
    [
        (
            bericht["attempted"],
            bericht["kept"],
            bericht["rejected"],
            bericht["unsupported"],
            gruende,
        )
    ],
)

# %% [markdown]
# - **Keine einzige** Ablehnung, weil Orakel und PyMOL sich widersprechen
# - alle Ablehnungen: abgestürzte PyMOL-Prozesse (`child_crash`)
#     - einzeln wiederholt wurden alle behalten: vorübergehende Fehler der Maschine (vermutlich Speicher)
# - was das Orakel nicht bewertet, wird markiert, z.B. die Kameraposition nach `orient`

# %% [markdown]
# ### 3.4 Aufteilung in Training und Test
# - Ein Test auf den Trainingsstrukturen beweist wenig
# - daher werden **ganze Strukturen** zurückgehalten: 6 von 24 nur im Test
# - zwei Testmengen:
#     - `test_gold`: handgeprüfte Wünsche in natürlicher Sprache (**primärer Endpunkt**)
#     - `heldout_synthetic`: Beispiele aus Satzvorlagen auf denselben zurückgehaltenen Strukturen
# - Trainingsbeispiele, deren Wunsch einem Gold-Wunsch fast gleicht, werden entfernt (Dekontamination)

# %%
manifest = support.load_json("docs/dataset/manifest.json")
counts = manifest["counts"]
support.markdown_table(
    ["Datei", "Beispiele"],
    [
        ("train", counts["train"]["total"]),
        ("test_gold", counts["test_gold"]["total"]),
        ("heldout_synthetic", counts["heldout_synthetic"]["total"]),
        ("durch Dekontamination entfernt", counts["decontam_dropped"]),
    ],
)

# %% [markdown]
# - Achtung: `heldout_synthetic` teilt die Satz*vorlagen* mit dem Training
#     - testet neue Strukturen, aber **keine** neuen Formulierungen
#     - neue Formulierungen testet nur `test_gold`

# %% [markdown]
# ## 4 Fine-Tuning

# %% [markdown]
# - Basismodell: **Llama-3.2-1B-Instruct**
# - **LoRA** (Low-Rank Adaptation) mit Unsloth auf den 16-Bit-Gewichten
# - danach Export als GGUF, quantisiert auf **Q4_K_M**
# - eine feste Konfiguration, **ein** Trainingslauf, **ein** Seed, keine Hyperparametersuche
# - Training einmalig auf einer RTX 4060

# %% [markdown]
# ### 4.1 Completion-only-Training
# - das Modell sieht Strukturkarte und Wunsch (den Prompt) genau so, wie die Engine sie später darstellt
# - es lernt aber **nur**, den Plan zu schreiben und dann aufzuhören
# - die Prompt-Tokens werden im Loss **maskiert** (Label `IGNORE_INDEX`)

# %%
from transformers import AutoTokenizer

from pmc_train.config import load_config
from pmc_train.examples import IGNORE_INDEX
from pmc_train.examples import build_example

config = load_config(support.ROOT / "configs" / "training" / "lora-v1.json")
tokenizer = AutoTokenizer.from_pretrained(
    config.base_model.repo, revision=config.base_model.revision
)
maskiert = build_example(
    beispiel["sample_id"],
    beispiel["prompt_text"],
    beispiel["plan_pml"],
    tokenizer,
    config.chat_template_date,
    config.max_seq_length,
)
trainiert = [t for t in maskiert.labels if t != IGNORE_INDEX]
print(f"{len(maskiert.input_ids)} Tokens, davon {len(trainiert)} im Loss:")
print(repr(tokenizer.decode(trainiert)))

# %% [markdown]
# - über 2.500 Tokens Prompt, aber nur der kurze Plan (und das Stopp-Token `<|eot_id|>`) wird gelernt

# %% [markdown]
# ### 4.2 Trainingsverlauf

# %%
import matplotlib.pyplot as plt

RUN_DIR = "docs/training/runs/train-e6c6c4dd8f6caaf9"
losses = [
    row for row in support.load_jsonl(f"{RUN_DIR}/loss.jsonl") if "loss" in row
]

figure, axis = plt.subplots(figsize=(7, 3))
axis.plot([row["step"] for row in losses], [row["loss"] for row in losses])
axis.set_xlabel("Optimierungsschritt")
axis.set_ylabel("Trainings-Loss")
axis.set_yscale("log")
axis.set_title("Completion-only-Training")
plt.show()

# %% [markdown]
# ## 5 Evaluation

# %% [markdown]
# - Metrik **TaskSuccess**: der Plan läuft fehlerfrei in PyMOL *und* erzeugt exakt den erwarteten Zustand
# - zwei Bedingungen:
#     - `no-grammar`: freie Generierung
#     - `grammar`: die Engine erzwingt per **Grammatik**, dass nur die eingeschränkte Sprache entsteht
# - Vergleich Basismodell gegen Fine-Tune, gepaart je Beispiel, mit exaktem zweiseitigem **McNemar-Test**
# - Vergleich und Endpunkt wurden festgelegt, *bevor* eines der Modelle ausgewertet war

# %%
from pmc_eval.compare import compare
from pmc_eval.eval_cli import read_run

EVALUATION = support.ROOT / "docs" / "evaluation"
CONFIGS = support.ROOT / "configs" / "evaluation"

# compare() rechnet jeden Bericht aus den gespeicherten Einzelergebnissen nach
vergleich = compare(
    EVALUATION / "baseline",
    EVALUATION / "finetuned",
    CONFIGS / "baseline.json",
    CONFIGS / "finetuned.json",
    read_run,
)
zeilen = []
for menge in ("test_gold", "heldout_synthetic"):
    for bedingung in ("no-grammar", "grammar"):
        block = vergleich["sets"][menge][bedingung]
        paar = block["paired_task_success"]
        tuned = block["overall"]["**TaskSuccess**"]["candidate"]
        zeilen.append(
            (
                menge,
                bedingung,
                support.rate(0, paar["n"]),
                support.rate(tuned["k"], tuned["n"]),
                f"{paar['mcnemar_exact_p']:.2g}",
            )
        )
support.markdown_table(
    ["Testmenge", "Bedingung", "Basismodell", "Fine-Tune", "McNemar p"], zeilen
)

# %% [markdown]
# - in Klammern: Anteil und 95%-Konfidenzintervall nach Wilson
# - Basismodell: **nie** erfolgreich
#     - ohne Grammatik kopiert es die Strukturkarte zurück
#     - mit Grammatik wiederholt es Befehle bis zum Token-Limit
# - Fine-Tune: unter **beiden** Bedingungen klar besser als das Basismodell
#     - mit Grammatik fast die Hälfte der Gold-Wünsche richtig
# - `heldout_synthetic` vollständig richtig, aber: gleiche Satzvorlagen wie im Training (Abschnitt 3.4)
# - Was noch scheitert, sind **Umformulierungen** (Paraphrasen):
#     - ohne Grammatik behält das Modell oft das Verb der Nutzer:in ("make the zinc ions magenta" wird zu `make magenta, ...`)
#     - aus Alltagsnamen werden erfundene Atomnamen ("the alpha carbons" wird zu `name ALPH`)
#     - "chains A and B" wird als `and` gelesen, gemeint ist aber `or`

# %% [markdown]
# ## 6 Anwendung: der Copilot in PyMOL

# %% [markdown]
# - ein lokaler Server lädt den Fine-Tune über **Lemonade** (lokaler Inferenzserver, CPU oder GPU)
# - in PyMOL registriert der Client neue Befehle:
#     - `copilot <Wunsch>`: Plan erzeugen und als Vorschau zeigen
#     - `copilot_apply <id>`: Plan anwenden
#     - `copilot_reject <id>`: Plan verwerfen
#     - `copilot_rollback <id>`: angewendeten Plan komplett rückgängig machen
# - Live-Vorführung (braucht einen Lemonade-Server): ausführliches Notebook, Abschnitt 9
# - Ausschnitt aus dessen Lauf, auf der im Training nie gesehenen Struktur `two_chains_hetatm`:
#
# ```
# PyMOL>copilot select the zinc ions, make them silver and show them as dots
#
# copilot plan p-5667af31-... (expires ..., in 5 min)
#   object:    pmc_structure (36 atoms, 1 state)
#   commands:
#     1 | select copilot_sel0244, name ZN   -> 2 atoms
#     2 | color silver, copilot_sel0244
#     3 | show dots, copilot_sel0244
#   warnings:  none
#   fidelity:  exact on the declared state scope
#   NOT checked: whether this is scientifically what you meant
#   apply:     copilot_apply p-5667af31-...
#   reject:    copilot_reject p-5667af31-...
# ```

# %% [markdown]
# - die Vorschau zeigt:
#     - die Befehle
#     - wie viele Atome jede Selektion beim Probelauf getroffen hat
#     - was geprüft wurde und was **nicht** (ob der Plan fachlich gemeint war)
# - die Sitzung ist bis hierhin **unverändert**
# - `copilot_apply` sichert die Sitzung zuerst, dann werden die Befehle ausgeführt
# - Beachte: das Modell wählt `name ZN` statt `resn ZN`
#     - auf dieser Struktur treffen beide dieselben zwei Atome, daher als richtig gewertet

# %% [markdown]
# ## 7 Grenzen und Ausblick

# %% [markdown]
# - nur **ein** Trainingslauf mit **einem** Seed, keine Ablationen
# - nur die Quantisierung Q4_K_M ausgewertet
# - Strukturen sind synthetisch und enthalten nur Rückgrat-Atome
# - der Term `polymer` wird nie bewertet, `orient` nur über die Anzahl getroffener Atome
# - integrierte GPUs (Vulkan) sind unerprobt; gemessen wurden CPU und eine NVIDIA-GPU
# - Wünsche im Training stammen aus **Satzvorlagen**
#     - größte Schwäche: **natürliche Formulierungen**
#     - hier muss der nächste Datensatz wachsen

# %% [markdown]
# ### Übung
# - Wählen Sie aus `kandidaten` (Abschnitt 3.2) einen Plan, der das Verb `hide` verwendet
# - Lassen Sie ihn vom Orakel (`apply_plan`) bewerten: wie viele Atome trifft jede Selektion?
# - Prüfen Sie mit `parse_pml`, ob der Parser den gerenderten Plan (`render_pml()`) akzeptiert
