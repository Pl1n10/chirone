# ruff: noqa: E501  (teacher instructions: prose, kept on one line each)
"""Messages that are not a PC problem chirone can act on -> info.what_i_can_do.

On the browser test VMs (2026-11-10) every such message turned into an action:
"ciao" opened the video player, "chi sei?" Firefox. No training row had ever
said "do nothing" for something that is not a fault. This writes those rows'
language: greetings, questions about chirone, thanks, gibberish, questions
about the PC's specs, and requests no fix can do (call someone, buy something).

The teacher writes language only, the label is fixed by construction. Texts
that look like a real request or complaint (open, search, remind, volume,
internet, printer...) are dropped, so the new label never contradicts an old one.

    TEACHER_BASE_URL=http://gpu-host.lan:11434/v1 TEACHER_MODEL=qwen3:14b \
    TEACHER_API_KEY=ollama TEACHER_EXTRA='{"reasoning_effort": "none"}' \
    python -m datagen.offtopic --lang it --out data/offtopic-it.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path

import yaml

from chirone.llm import OpenAICompat

from .teacher import parse_list

HERE = Path(__file__).parent

KINDS = {
    "it": {
        "greeting": "saluti e chiacchiere senza una richiesta (ciao, buongiorno, come stai, ci sei?)",
        "identity": "domande su chi o cosa è l'assistente (chi sei, sei una persona, chi ti ha fatto, come ti chiami)",
        "capability": "domande su cosa sa fare l'assistente o richieste di aiuto generiche senza dire il problema",
        "thanks": "ringraziamenti, saluti finali, commenti sulla risposta ricevuta",
        "pc_info": "domande sulle caratteristiche del computer (quanta memoria ha, che processore, che sistema è, quanti anni ha)",
        "impossible": "richieste che un assistente sul computer non può fare: telefonare a qualcuno, comprare qualcosa, "
                      "prenotare una visita, riparare il telefono, cambiare la password di un sito, mandare un messaggio a una persona",
        "gibberish": "messaggi senza senso: tasti a caso, frasi interrotte a metà, una parola sola, parole sbagliate",
        "unsupported": "richieste di fare sul computer una cosa che l'assistente non sa fare: "
                       "spegnere il computer, cambiare la luminosità, ingrandire lo schermo, installare o disinstallare "
                       "un programma, cancellare un file, fare uno screenshot, cambiare lo sfondo, scrivere una mail. "
                       "Scritte come richieste dirette all'assistente di farlo lui (es. 'spegni il computer', 'puoi abbassare la luminosità?'), "
                       "non come domande su come si fa",
    },
    "en": {
        "greeting": "greetings and small talk with no request (hi, good morning, how are you, are you there?)",
        "identity": "questions about who or what the assistant is (who are you, are you a person, who made you, your name)",
        "capability": "questions about what the assistant can do, or vague requests for help without saying the problem",
        "thanks": "thanks, goodbyes, comments about the answer received",
        "pc_info": "questions about the computer's specs (how much memory, which processor, which system, how old it is)",
        "impossible": "requests an assistant on the computer cannot do: phone someone, buy something, book an appointment, "
                      "repair the phone, change a website password, send a message to a person",
        "gibberish": "meaningless messages: random keys, sentences cut in half, a single word, misspelled words",
        "unsupported": "requests to do something on the computer the assistant cannot do: "
                       "shut down the computer, change the brightness, zoom the screen, install or uninstall "
                       "a program, delete a file, take a screenshot, change the wallpaper, write an email",
    },
}

PROMPT = {
    "it": "Scrivi {n} messaggi diversi che {persona} scriverebbe nella finestra di un assistente sul computer. "
          "Tipo di messaggio: {kind}. Non descrivere guasti del computer e non chiedere di aprire programmi o siti, "
          "di cercare su internet, di cambiare il volume o di ricordare qualcosa. Scrivi come scriverebbe davvero "
          "quella persona. Rispondi solo con un array JSON di stringhe.",
    "en": "Write {n} different messages that {persona} would type into the window of an assistant on their computer. "
          "Kind of message: {kind}. Do not describe computer faults and do not ask to open programs or websites, "
          "to search the web, to change the volume or to set a reminder. Write the way that person really writes. "
          "Answer only with a JSON array of strings.",
}

# A text with one of these is too close to a real request or complaint: drop it.
CONFLICT = re.compile(
    r"\b(apr[ia]|aprimi|cerca|cercami|ricorda|ricordami|volume|audio|suon|stamp|internet|wifi|wi-fi|rete|"
    r"aggiorn|disco|spazio|lent[oa]|bloccat|non funziona|non va|non si apre|"
    r"open|search|look up|remind|sound|print|network|update|disk|slow|frozen|doesn'?t work|won'?t open)",
    re.IGNORECASE,
)

# For "unsupported" the teacher is asked for actions on purpose: drop only what
# chirone can really do (open, search, a site, a folder, volume, a reminder) and
# what is a fault category (printer, network, sound, updates).
CONFLICT_UNSUPPORTED = re.compile(
    r"\b(apr[ia]|aprimi|cerca|cercami|ricorda|ricordami|volume|audio|suon|stamp|internet|wifi|wi-fi|rete|aggiorn|"
    r"open|search|look up|remind|sound|print|network|update|whatsapp|youtube|google|"
    # closing a program and restarting are real actions since app.close / system.restart
    r"chiud|riavvi|close|restart|reboot)",
    re.IGNORECASE,
)

# "unsupported" keeps only direct requests: a how-to question is labelled noop
# by the existing `other` control rows, and "the program won't close" is a
# real fault (proc.terminate_user_process). Neither may get a second label.
NOT_A_REQUEST = re.compile(
    r"\b(come|non so|non riesco|non si chiude|non risponde|bloccat|how|don'?t know|can'?t|won'?t|frozen|stuck)\b",
    re.IGNORECASE,
)

# Written here, not by the teacher: the shortest inputs a person really types.
SEEDS = {
    "it": ["ciao", "buongiorno", "buonasera", "ehi", "ci sei?", "pronto?", "aiuto", "aiutami", "help",
           "chi sei?", "cosa sai fare?", "come ti chiami?", "grazie", "grazie mille", "ok grazie",
           "ciao ciao", "a domani", "asdf", "qwerty", "...", "boh non so", "niente lascia stare",
           "prova", "prova prova", "test", "come funziona?", "sei un robot?", "che computer è questo?",
           "quanta memoria ha?", "mi chiami mia figlia?", "spegni il computer", "abbassa la luminosità", "ingrandisci lo schermo",
           "cancella questo file", "fai uno screenshot", "cambia lo sfondo", ],
    "en": ["hi", "hello", "hey", "good morning", "are you there?", "help", "help me", "who are you?",
           "what can you do?", "what's your name?", "thanks", "thank you so much", "ok thanks", "bye",
           "asdf", "qwerty", "...", "never mind", "test", "testing", "how does this work?",
           "are you a robot?", "what computer is this?", "how much memory does it have?", "call my daughter",
           "shut down the computer", "turn down the brightness",
           "make the screen bigger", "delete this file", "take a screenshot", "change the wallpaper", ],
}


def keep(text: str, kind: str = "") -> bool:
    rx = CONFLICT_UNSUPPORTED if kind in ("unsupported", "seed") else CONFLICT
    if kind == "unsupported" and NOT_A_REQUEST.search(text):
        return False
    return 1 <= len(text.strip()) <= 200 and not rx.search(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="it", choices=sorted(KINDS))
    ap.add_argument("--per-persona", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--kinds", help="comma-separated subset of kinds (default: all)")
    a = ap.parse_args()

    random.seed(a.seed)
    sfx = "" if a.lang == "it" else f"_{a.lang}"
    personas = yaml.safe_load((HERE / f"personas{sfx}.yaml").read_text(encoding="utf-8"))
    teacher = OpenAICompat(os.environ["TEACHER_BASE_URL"], os.environ["TEACHER_MODEL"], os.environ["TEACHER_API_KEY"],
                           extra=json.loads(os.environ.get("TEACHER_EXTRA", "{}")))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with out.open("w", encoding="utf-8") as f:
        def write(text: str, kind: str, persona: int | None) -> bool:
            key = text.strip().lower()
            if key in seen or not keep(text, kind):
                return False
            seen.add(key)
            f.write(json.dumps({"text": text.strip(), "kind": kind, "lang": a.lang, "persona": persona},
                               ensure_ascii=False) + "\n")
            return True

        for t in SEEDS[a.lang]:
            write(t, "seed", None)
        kinds = a.kinds.split(",") if a.kinds else list(KINDS[a.lang])
        for kind, desc in ((k, KINDS[a.lang][k]) for k in kinds):
            for pi, persona in enumerate(personas):
                prompt = PROMPT[a.lang].format(n=a.per_persona, persona=persona, kind=desc)
                try:
                    items = parse_list(teacher.chat([{"role": "user", "content": prompt}]))
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"{kind} persona {pi}: unparsable ({e})")
                    continue
                kept = sum(write(t, kind, pi) for t in items)
                print(f"{kind:11} persona {pi}: {kept}/{len(items)}", flush=True)


if __name__ == "__main__":
    main()
