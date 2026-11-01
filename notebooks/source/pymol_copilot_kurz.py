# Copyright 2026 Hannah Kullik & Martin Urban.
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
# 3. **Datensatz**: automatisch erzeugt und von einem **Orakel** geprüft
# 4. **Fine-Tuning** eines kleinen Sprachmodells (Llama-3.2-1B) mit **LoRA**
# 5. **Evaluation**: Basismodell und feinabgestimmtes Modell im Vergleich
# 6. **Anwendung**: der Copilot in PyMOL
# 7. **Grenzen** und Ausblick

# %% [markdown]
# <img src="../assets/splash_screen.png" width="500px">

# %% [markdown]
# - Kurzfassung des ausführlichen englischen Notebooks `pymol_copilot.ipynb`
# - Das Notebook ist mit allen Ausgaben gespeichert: Man kann es lesen, ohne etwas auszuführen
# - Rechenintensive Schritte (Datensatz erzeugen, Training, Evaluation) laufen hier **nicht** erneut
#     - stattdessen werden die Ergebnisse geladen, die im Repository abgelegt sind
# - Schnelle Schritte (Millisekunden) laufen dagegen live
# - Alle Strukturbilder rendert PyMOL selbst, live in diesem Kernel und ohne eigenes Fenster
# - Für die Live-Vorführung des Copiloten (Abschnitt 6) wird ein Lemonade-Server mit dem Modell benötigt
#     - einzuschalten über die Umgebungsvariable `PMC_NOTEBOOK_DEMO=1`
#     - im Windows-Bundle geschieht das automatisch: Es startet einen eigenen Server, der auf der CPU rechnet

# %%
# Copyright 2026 Hannah Kullik & Martin Urban.
"""Kernel vorbereiten: die Pakete des Repositorys einbinden, PyMOL starten."""

import importlib
import os
import sys
import warnings
from pathlib import Path

# Fortschrittsbalken des Tokenizers bräuchten ipywidgets
warnings.filterwarnings("ignore", message="IProgress not found")

# Die Hilfsfunktionen liegen neben dem Notebook im Ordner notebooks/
sys.path.insert(0, str(Path.cwd()))
support = importlib.import_module("notebook_support")

# Pakete des Repositorys (src/) importierbar machen
support.setup_paths()

# Live-Vorführung in Abschnitt 6: nur mit Lemonade-Server und Modell
RUN_DEMO = os.environ.get("PMC_NOTEBOOK_DEMO") == "1"

# PyMOL läuft ohne Fenster in diesem Kernel und rendert die Bilder.
# Es muss vor Tokenizer und LangGraph starten: Unter Windows lässt es
# sich danach im Jupyter-Kernel nicht mehr starten
cmd = support.launch_pymol()

# %% [markdown]
# ## 1 Problemstellung

# %% [markdown]
# - **PyMOL**: Programm zur Darstellung von Molekülstrukturen, gesteuert über eine eigene Befehlssprache
# - Beispiele:
#     - `color red, chain A` färbt alle Atome der Kette A rot
#     - `show sticks, resn ZN` stellt die Zink-Ionen als Stäbchen dar
# - Wer solche Befehle schreibt, muss die **Selektionssyntax** von PyMOL beherrschen
# - Idee: Man beschreibt in eigenen Worten, was man sehen möchte, und ein **LLM** schreibt die Befehle
# - Problem: Ein allgemeines Chat-LLM ist dafür **nicht sicher genug**
#     - PyMOLs Befehlssprache kann auch Python-Code ausführen, Dateien laden und Plugins aufrufen
# - Ziel: ein **kleines, lokales** Modell; keine Daten verlassen den Rechner
# - Das Modell liefert einen **Plan**, also eine kurze Liste von PyMOL-Befehlen

# %% [markdown]
# ### 1.1 Ablauf einer Anfrage
# 1. **Snapshot**: Die laufende PyMOL-Sitzung wird ausgelesen
# 2. **Strukturkarte**: Der Snapshot wird als Text dargestellt (Objekt, Atome, Farben, Darstellungsformen)
# 3. **Generierung**: Das lokale LLM erhält Strukturkarte und Anfrage und schreibt daraus den Plan
# 4. **Validierung**: Der Plan wird
#     - geparst,
#     - von einer unabhängigen Regelprüfung (Policy) kontrolliert und
#     - zur Probe in einem *separaten* PyMOL-Prozess ausgeführt
#     - Schlägt dabei etwas fehl, gibt es höchstens zwei Reparaturversuche
# 5. **Freigabe**: Man sieht die Befehle und wie viele Atome sie jeweils treffen, und bestätigt mit `copilot_apply`
# 6. **Anwenden**: Die Sitzung wird vorher gesichert und bei einem Fehler wiederhergestellt
#
# - **Gelernt** wird nur ein einziger Teil: das **Sprachmodell** in Schritt 3

# %% [markdown]
# ## 2 Eine eingeschränkte Befehlssprache

# %% [markdown]
# - nur **fünf Verben**: `select`, `color`, `show`, `hide`, `orient`
# - Selektionen werden aus **sechs Bausteinen** gebildet: `chain`, `resi`, `resn`, `name`, `hetatm`, `polymer`
# - verknüpft mit `and`, `or` und `not`
# - Alles andere wird abgelehnt, **bevor** etwas ausgeführt wird
# - Eigener Parser (`pmc_core.parser`): Ungeprüfter Text gelangt *nie* zum Parser von PyMOL

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
# - Beachte: Der Parser **normalisiert nichts**, nicht einmal die Groß- und Kleinschreibung (`Color`)
#     - Ein Parser, der normalisiert, akzeptiert schnell Eingaben, an die niemand gedacht hat

# %% [markdown]
# ## 3 Datensatz

# %% [markdown]
# - Ein Modell lernt aus Beispielen der Form (Struktur, Anfrage, korrekter Plan)
# - Echte Beispiele aus der Praxis gibt es dafür nicht
# - Pläne, die von Hand oder von einem anderen LLM geschrieben werden, können **falsch** sein
# - Deshalb entsteht jedes Beispiel **programmgesteuert** ("program-first"):
#     - Ein Programm zählt die Pläne systematisch auf
#     - Ein **Orakel** sagt das Ergebnis jedes Plans voraus, *ohne* PyMOL zu benutzen
#     - Der Plan wird in echtem PyMOL ausgeführt
#     - Das Beispiel wird nur behalten, wenn PyMOL **exakt** das vorhergesagte Ergebnis liefert

# %% [markdown]
# ### 3.1 Synthetische Strukturen und Strukturkarte
# - 24 kleine, **synthetische** Proteine
#     - mit mehreren Ketten, Heteroatomen (Zink, Wasser), mehreren Zuständen (States), alternativen Atompositionen und Insertion Codes
# - Bewusst synthetisch: keine Daten aus der PDB, jedes Atom ist bekannt
# - Das Modell sieht eine Struktur als **Strukturkarte**, also als Text, zum Beispiel:

# %%
from pmc_core.card import render_for_runtime
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

# Eine Anfrage aus der handgeprüften Gold-Testmenge und ihre Struktur
gold = support.load_jsonl("src/pmc_data/gold/gold_samples.jsonl")
beispiel = next(row for row in gold if row["sample_id"] == "gold_056")
spec = StructureSpec.from_dict(beispiel["structure"]["spec"])
snapshot = build_structure(spec)

anzahl_atome = sum(len(state.atoms) for state in snapshot.states)
print(f"Struktur '{spec.spec_id}' mit {anzahl_atome} Atomen")
print("Anfrage:", beispiel["intent"])
print()
karte = render_for_runtime(snapshot)
print("\n".join(karte.splitlines()[:10]))
print("...")

# %% [markdown]
# - Dieselbe Struktur in PyMOL:
#     - Jede kleine Kugel ist ein Atom in seiner aktuellen Farbe: Protein grün, Zink und Wasser gelb
#     - Beschriftet sind Kette und Residuennummer, bei Zink (`ZN`) und Wasser (`HOH`) auch der Residuenname
# - Die Atome liegen zufällig verteilt in einem Würfel von 60 Å Kantenlänge und sind nicht miteinander verbunden
#     - ein Testobjekt, kein gefaltetes Protein
#     - Linien (`lines`) und Stäbchen (`sticks`) brauchen Bindungen und bleiben deshalb unsichtbar
#     - Die kleinen Kugeln fügt nur das Bild hinzu; die Sitzung selbst bleibt unverändert
# - Zink und Wasser sind schon im Ausgangszustand als Kugeln (`spheres`) dargestellt, im Bild vergrößert
# - Meldungen wie `cmd.sync() timed out` gibt PyMOL selbst aus, wenn es in einem Notebook-Kernel läuft; sie sind harmlos

# %%
from pmc_core.snapshot import reconstruct

# PyMOL baut die Struktur Atom für Atom aus dem Snapshot auf
reconstruct(cmd, snapshot)
bild_struktur = support.picture(cmd)
support.show_pictures((f"'{spec.spec_id}' in PyMOL", bild_struktur))

# %% [markdown]
# ### 3.2 Pläne aufzählen
# - `enumerate_plans` erzeugt für jede Struktur Pläne über alle Verben, Bausteine und Ausdrucksformen
# - Zu jedem Plan gehört eine Anfrage, die aus einer **Satzvorlage** entsteht

# %%
from pmc_data.taxonomy import enumerate_plans

kandidaten = enumerate_plans(snapshot, seed=20260921)
plan = next(
    c for c in kandidaten if c.category.startswith("color+select+show/name/")
)

print(f"{len(kandidaten)} mögliche Pläne für diese Struktur, zum Beispiel:")
print("Anfrage:  ", plan.intent)
print("Kategorie:", plan.category)
print(plan.plan.render_pml(), end="")

# %% [markdown]
# ### 3.3 Das Orakel
# - sagt ohne PyMOL voraus:
#     - welchen Zustand die Sitzung nach dem Plan hat
#     - wie viele Atome jede Selektion trifft
# - Grundsatz: lieber **ablehnen als raten**; was sich nicht vorhersagen lässt, wird ausdrücklich benannt

# %%
from pmc_data.oracle import apply_plan

vorhersage = apply_plan(snapshot, plan.plan)
print("Atome je Selektion:  ", vorhersage.selection_counts)
print("Zustand vorhergesagt:", vorhersage.snapshot is not None)
print("Nicht geprüft:       ", vorhersage.unsupported or "nichts")

# %% [markdown]
# - Jetzt läuft derselbe Plan in echtem PyMOL
#     - mit `run_plan`, derselben Funktion, die auch der Probelauf des Copiloten verwendet
# - Anschließend wird der Zustand der Sitzung mit der Vorhersage des Orakels verglichen

# %%
from pmc_core.plan import selection_names
from pmc_core.snapshot import diff
from pmc_core.snapshot import extract
from pmc_sidecar.child import run_plan

lauf = run_plan(cmd, plan.plan)
treffer = tuple(
    (name, cmd.count_atoms(name)) for name in selection_names(plan.plan)
)
abweichungen = diff(vorhersage.snapshot, extract(cmd, snapshot.name))
print("Ergebnis in PyMOL:   ", lauf.status)
print("Atome je Selektion:  ", treffer)
print("Abweichungen:        ", abweichungen or "keine")
support.show_pictures(
    ("vorher", bild_struktur), ("nach dem Plan", support.picture(cmd))
)

# %% [markdown]
# - Orakel und PyMOL stimmen überein: gleiche Trefferzahl, kein Unterschied im Zustand
# - Im Bild: Die acht `C`-Atome haben die Farbe `lanthanum` und werden als große Kugeln (`spheres`) dargestellt
#     - Zink und Wasser waren schon vorher als Kugeln dargestellt
# - Beim Erzeugen des Datensatzes ist jeder Versuch ein solcher **Vergleichstest** zwischen Orakel und PyMOL
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
        "Vom Orakel nicht bewertet",
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
# - **Kein einziger** Versuch wurde abgelehnt, weil Orakel und PyMOL sich widersprochen hätten
# - Alle Ablehnungen gehen auf abgestürzte PyMOL-Prozesse zurück (`child_crash`)
#     - Einzeln wiederholt, wurden alle diese Versuche behalten: Es waren vorübergehende Fehler der Maschine (vermutlich Speichermangel)
# - Was das Orakel nicht bewerten kann, wird markiert, z. B. die Kameraposition nach `orient`

# %% [markdown]
# ### 3.4 Aufteilung in Training und Test
# - Ein Test auf Strukturen, die schon im Training vorkamen, sagt wenig aus
# - Deshalb werden **ganze Strukturen** zurückgehalten: 6 der 24 kommen nur im Test vor
# - Zwei Testmengen:
#     - `test_gold`: handgeprüfte Anfragen in natürlicher Sprache (**primärer Endpunkt**)
#     - `heldout_synthetic`: Beispiele aus Satzvorlagen auf denselben zurückgehaltenen Strukturen
# - Trainingsbeispiele, deren Anfrage einer Gold-Anfrage fast gleicht, werden entfernt (Dekontamination)

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
# - Achtung: `heldout_synthetic` verwendet dieselben Satz*vorlagen* wie das Training
#     - prüft also neue Strukturen, aber **keine** neuen Formulierungen
#     - neue Formulierungen prüft nur `test_gold`

# %% [markdown]
# ## 4 Fine-Tuning

# %% [markdown]
# - Basismodell: **Llama-3.2-1B-Instruct**
# - **LoRA** (Low-Rank Adaptation) mit Unsloth auf den 16-Bit-Gewichten
# - anschließend Export als GGUF und Quantisierung auf **Q4_K_M**
# - eine feste Konfiguration, **ein** Trainingslauf, **ein** Seed, keine Suche nach Hyperparametern
# - trainiert wurde ein einziges Mal, auf einer RTX 4060

# %% [markdown]
# ### 4.1 Gelernt wird nur der Plan (Completion-only)
# - Das Modell sieht Strukturkarte und Anfrage (den Prompt) genau so, wie die Engine sie später aufbereitet
# - Es lernt aber **nur**, den Plan zu schreiben und danach aufzuhören
# - Die Tokens des Prompts werden im Loss **ausgeblendet** (Label `IGNORE_INDEX`)

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
# - Der Prompt umfasst über 2.500 Tokens; gelernt werden nur der kurze Plan und das Stopp-Token `<|eot_id|>`

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
axis.set_title("Training, Loss nur auf dem Plan")
plt.show()

# %% [markdown]
# ## 5 Evaluation

# %% [markdown]
# - Metrik **TaskSuccess**: Der Plan läuft in PyMOL fehlerfrei durch *und* erzeugt exakt den erwarteten Zustand
# - Zwei Bedingungen:
#     - `no-grammar`: freie Generierung
#     - `grammar`: Eine **Grammatik** in der Engine sorgt dafür, dass nur Befehle der eingeschränkten Sprache entstehen können
# - Basismodell und feinabgestimmtes Modell werden Beispiel für Beispiel gepaart verglichen, mit dem exakten zweiseitigen **McNemar-Test**
# - Vergleich und Endpunkt standen fest, *bevor* eines der beiden Modelle ausgewertet wurde

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
    ["Testmenge", "Bedingung", "Basismodell", "Feinabgestimmt", "McNemar p"],
    zeilen,
)

# %% [markdown]
# - Das Basismodell ist **nie** erfolgreich
#     - ohne Grammatik schreibt es die Strukturkarte ab
#     - mit Grammatik wiederholt es Befehle, bis das Token-Limit erreicht ist
# - Das feinabgestimmte Modell ist unter **beiden** Bedingungen deutlich besser
#     - mit Grammatik löst es fast die Hälfte der Gold-Anfragen
# - `heldout_synthetic` löst es vollständig, aber dort stammen die Anfragen aus denselben Satzvorlagen wie im Training (Abschnitt 3.4)
# - Woran es noch scheitert, sind **Umformulierungen** (Paraphrasen):
#     - Ohne Grammatik übernimmt das Modell oft das Verb aus der Anfrage ("make the zinc ions magenta" wird zu `make magenta, ...`)
#     - Aus umgangssprachlichen Bezeichnungen werden erfundene Atomnamen ("the alpha carbons" wird zu `name ALPH`)
#     - "chains A and B" wird wörtlich als `and` übersetzt, gemeint ist aber `or` (beide Ketten)

# %% [markdown]
# ## 6 Anwendung: der Copilot in PyMOL

# %% [markdown]
# - Ein lokaler Server stellt das feinabgestimmte Modell über **Lemonade** bereit (ein lokaler Inferenzserver für CPU oder GPU)
# - In PyMOL registriert der Client neue Befehle:
#     - `copilot <Anfrage>`: erzeugt einen Plan und zeigt ihn als Vorschau
#     - `copilot_apply <id>`: wendet den Plan an
#     - `copilot_reject <id>`: verwirft den Plan
#     - `copilot_rollback <id>`: macht einen angewendeten Plan vollständig rückgängig

# %% [markdown]
# ### 6.1 Server und PyMOL starten
# - Einstellungen des Servers:
#     - Name des Modells
#     - Kontextlänge von 16.384 Tokens (die Strukturkarte führt jedes Atom auf)
#     - derselbe Prompt wie im Training, dazu die Grammatik
# - Welche Engine das Modell ausführt, hängt vom Rechner ab:
#     - auf dem Entwicklungsrechner: Lemonade in Docker
#     - im Windows-Bundle: ein eigenes Lemonade auf der CPU, das vorher die SHA-256-Prüfsumme des Modells kontrolliert

# %%
MODEL_NAME = "Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M"
CONTEXT_SIZE = 16384
SERVER_FLAGS = [
    "--model-name",
    MODEL_NAME,
    "--context-size",
    str(CONTEXT_SIZE),
    "--read-timeout-seconds",
    "600",
    "--prompt",
    "training",
    "--grammar",
    "--max-tokens",
    "256",
    "--generation-deadline-seconds",
    "600",
]
print("python -m pmc_server.main", " ".join(SERVER_FLAGS), "<Engine-Flags>")

# %% [markdown]
# - Geladen wird die Struktur aus Abschnitt 3.1, frisch aufgebaut: `two_chains_hetatm`, die im Training **nie** vorkam
#     - zwei Ketten mit je einem Zink-Ion und einem Wassermolekül
# - Anschließend verbindet sich der Client mit dem Server

# %%
import tempfile

from pmc_client.bootstrap import connect_from_handoff
from pmc_client.recovery import RecoveryStore

ausgabe: list[str] = []
if RUN_DEMO:
    # Engine und Server starten; der Server schreibt Port und Schlüssel in handoff
    lemonade = support.start_engine(MODEL_NAME, CONTEXT_SIZE)
    print("Engine:", " ".join(lemonade.flags))
    arbeitsordner = Path(tempfile.mkdtemp(prefix="pmc-notebook-"))
    handoff = arbeitsordner / "session.json"
    server = support.start_server([*SERVER_FLAGS, *lemonade.flags], handoff)

    # Abschnitt 3.3 hat die Struktur verändert: neu aufbauen, Client verbinden
    cmd.delete("all")
    reconstruct(cmd, snapshot)
    driver = support.ConsoleDriver(cmd)
    client = connect_from_handoff(
        driver,
        ausgabe.append,
        path=handoff,
        recovery_store=RecoveryStore(arbeitsordner),
    )
    print("\n".join(ausgabe))
    ausgabe.clear()
    support.show_pictures(("Ausgangszustand der Sitzung", support.picture(cmd)))
else:
    print("RUN_DEMO ist aus: PMC_NOTEBOOK_DEMO=1 setzen, mit Lemonade-Server.")

# %% [markdown]
# ### 6.2 Eine Anfrage in eigenen Worten
# - die Anfrage aus Abschnitt 3.1 (Gold-Anfrage `gold_056`)
# - Antwortzeit:
#     - GPU: wenige Sekunden
#     - CPU: zehn Sekunden bis etwa eine Minute; fast die ganze Zeit braucht das Modell, um den Prompt (die Strukturkarte) zu lesen

# %%
ANFRAGE = "select the zinc ions, make them silver and show them as dots"
if RUN_DEMO:
    sekunden = driver.run(f"copilot {ANFRAGE}")
    vorschau = "\n".join(ausgabe)
    ausgabe.clear()
    print(vorschau)
    print(f"\n(beantwortet in {sekunden:.1f} s)")

# %% [markdown]
# - Die Vorschau zeigt:
#     - die Befehle
#     - wie viele Atome jede Selektion beim Probelauf im separaten PyMOL-Prozess getroffen hat
#     - was geprüft wurde und was **nicht**, nämlich ob der Plan fachlich das Gemeinte trifft
# - Bis hierhin ist die Sitzung **unverändert**
# - Beachte: Das Modell wählt die Zink-Ionen über den Atomnamen aus (`name ZN`), der Gold-Plan über den Residuennamen (`resn ZN`)
#     - Auf dieser Struktur treffen beide dieselben zwei Atome; deshalb wurde der Plan in der Evaluation als richtig gewertet
# - Meldungen wie `cmd.sync() timed out` gibt PyMOL selbst aus, wenn es in einem Notebook-Kernel läuft; die Befehle werden trotzdem vollständig ausgeführt

# %% [markdown]
# ### 6.3 Plan anwenden
# - `copilot_apply` sichert zuerst die Sitzung und führt dann die Befehle aus

# %%
plan_id = None
if RUN_DEMO:
    plan_id = support.plan_id(vorschau)
if plan_id is not None:
    bild_vorher = support.picture(cmd)
    driver.run(f"copilot_apply {plan_id}")
    print("\n".join(ausgabe))
    ausgabe.clear()
    print("Angelegte Selektion:", cmd.get_names("selections"))
    support.show_pictures(
        ("vorher", bild_vorher), ("nach copilot_apply", support.picture(cmd))
    )
elif RUN_DEMO:
    print("Der Copilot hat keinen Plan angeboten; siehe seine Antwort oben.")

# %% [markdown]
# - Die beiden Zink-Ionen (`ZN A901`, `ZN B901`) sind jetzt silbern
# - Die Punkte (`dots`) sieht man im Bild kaum: Sie liegen dicht am Atom und verschwinden in der Kugel, mit der Zink schon vorher dargestellt war

# %% [markdown]
# ### 6.4 Eine Anfrage, die nie ausgewertet wurde
# - Diese Formulierung kam weder im Training noch in der Evaluation vor
# - Auch dieser Plan wird angewendet

# %%
plan_id_b = None
if RUN_DEMO:
    driver.run("copilot colour chain B marine and show it as sticks")
    vorschau_b = "\n".join(ausgabe)
    ausgabe.clear()
    print(vorschau_b)
    plan_id_b = support.plan_id(vorschau_b)
if plan_id_b is not None:
    bild_vorher_b = support.picture(cmd)
    driver.run(f"copilot_apply {plan_id_b}")
    print("\n".join(ausgabe))
    ausgabe.clear()
    support.show_pictures(
        ("vorher", bild_vorher_b), ("nach copilot_apply", support.picture(cmd))
    )

# %% [markdown]
# - Kette B ist jetzt blau (`marine`), samt Zink-Ion und Wassermolekül: Der Plan färbt die *ganze* Kette
# - Die Stäbchen (`sticks`) sieht man nicht: Stäbchen stellen Bindungen dar, und diese Atome haben keine

# %% [markdown]
# ### 6.5 Rückgängig machen
# - Einen unerwünschten Plan wendet man einfach nicht an: `copilot_reject` verwirft ihn
# - Ein angewendeter Plan lässt sich als Ganzes zurücknehmen, weil die Sitzung vorher gesichert wurde
# - Zurücknehmen lässt sich der zuletzt angewendete Plan, hier der aus 6.4:

# %%
letzter_plan = plan_id_b or plan_id
if letzter_plan is not None:
    bild_vorher = support.picture(cmd)
    driver.run(f"copilot_rollback {letzter_plan}")
    print("\n".join(ausgabe))
    ausgabe.clear()
    support.show_pictures(
        ("vorher", bild_vorher), ("nach copilot_rollback", support.picture(cmd))
    )
if RUN_DEMO:
    support.stop_server(server)
    support.stop_engine(lemonade)

# %% [markdown]
# - Kette B ist wieder grün; die silbernen Zink-Ionen aus 6.3 bleiben erhalten

# %% [markdown]
# ## 7 Grenzen und Ausblick

# %% [markdown]
# - nur **ein** Trainingslauf mit **einem** Seed, keine Ablationsstudien
# - ausgewertet wurde nur die Quantisierung Q4_K_M
# - Die Strukturen sind synthetisch: zufällig verteilte Atome des Proteinrückgrats, meist ohne Bindungen
# - Der Baustein `polymer` wird nie bewertet, `orient` nur über die Zahl der getroffenen Atome
# - Integrierte GPUs (Vulkan) sind nicht erprobt; gemessen wurde auf der CPU und auf einer NVIDIA-GPU
# - Die Anfragen im Training stammen aus **Satzvorlagen**
#     - die größte Schwäche sind daher **natürliche Formulierungen**
#     - genau hier muss der nächste Datensatz ansetzen
