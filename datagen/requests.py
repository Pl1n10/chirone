"""Generate everyday requests for the `actions` category with the teacher.

Two kinds, both labelled by construction, never by the teacher's judgement:

* open a program: the teacher writes requests for a *concept* ("the
  calculator", "something to write a letter"); the label is resolved later,
  per PC, to the desktop id of that concept installed there (apps.yaml).
* search the web: the teacher writes {request, query} pairs; a pair is kept
  only if the query appears verbatim in the request and is a valid param, so
  the model learns to copy the person's words, not to invent a search.

    python -m datagen.requests --lang it --per-persona 4 --out data/requests-it.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path

import yaml

from chirone.catalog import Catalog, ParamError
from chirone.llm import OpenAICompat

HERE = Path(__file__).parent

OPEN_PROMPT = {
    "it": """Stai generando dati di addestramento per un piccolo assistente che aiuta persone non esperte
a usare un vecchio PC con Linux. Scrivi {n} messaggi diversi con cui questa persona chiede
al computer di aprire un programma.

La persona: {persona}
Cosa vuole aprire (non conosce il nome tecnico del programma): {concept}

Regole: solo italiano; da 2 parole a 2 frasi; a volte nomina il programma, più spesso dice
cosa vuole fare; errori di battitura e dialetto benvenuti se adatti alla persona; niente
numeri né spiegazioni. Rispondi solo con un array JSON di {n} stringhe.""",
    "en": """You are generating training data for a tiny assistant that helps non-technical people use
an old Linux PC. Write {n} different messages in which this person asks the computer to
open a program.

The person: {persona}
What they want to open (they don't know the program's technical name): {concept}

Rules: English only; 2 words to 2 sentences; sometimes they name the program, more often
they say what they want to do; typos welcome when they fit the persona; no numbering or
explanations. Answer only with a JSON array of {n} strings.""",
}

CLOSE_PROMPT = {
    "it": """Stai generando dati di addestramento per un piccolo assistente che aiuta persone non esperte
a usare un vecchio PC con Linux. Scrivi {n} messaggi diversi con cui questa persona chiede
al computer di chiudere un programma che ha aperto.

La persona: {persona}
Cosa vuole chiudere (non conosce il nome tecnico del programma): {concept}

Regole: solo italiano; da 2 parole a 2 frasi; è una richiesta di chiuderlo, non un guasto (il
programma funziona, la persona ha finito); a volte nomina il programma, più spesso dice cosa
stava facendo; errori di battitura e dialetto benvenuti se adatti alla persona; niente numeri
né spiegazioni. Rispondi solo con un array JSON di {n} stringhe.""",
    "en": """You are generating training data for a tiny assistant that helps non-technical people use
an old Linux PC. Write {n} different messages in which this person asks the computer to close
a program they have open.

The person: {persona}
What they want to close (they don't know the program's technical name): {concept}

Rules: English only; 2 words to 2 sentences; it is a request to close it, not a fault (the
program works, the person is done with it); sometimes they name the program, more often they
say what they were doing; typos welcome when they fit the persona; no numbering or explanations.
Answer only with a JSON array of {n} strings.""",
}

# A close request that sounds like a fault belongs to proc.terminate_user_process.
NOT_A_CLOSE_REQUEST = re.compile(
    r"non si chiude|bloccat|non risponde|impallat|incantat|won'?t close|frozen|stuck|not responding|hang",
    re.IGNORECASE,
)

SEARCH_PROMPT = {
    "it": """Stai generando dati di addestramento per un piccolo assistente che aiuta persone non esperte
a usare un vecchio PC con Linux. Scrivi {n} messaggi diversi con cui questa persona chiede al
computer di cercare qualcosa su internet, su argomenti vari della vita di tutti i giorni
(salute, orari, ricette, notizie, burocrazia, meteo, sport, hobby).

La persona: {persona}

Il messaggio è rivolto al computer, come lo direbbe questa persona ("mi cerchi...", "vorrei
sapere...", "trova...", "fammi vedere...", con o senza saluti e giri di parole).
Per ogni messaggio indica anche la ricerca da fare, come la scriveresti in un motore di
ricerca: SOLO parole che compaiono nel messaggio, scritte uguali (stesse lettere, stessi
accenti), senza aggiungerne di nuove, senza virgolette, al massimo 100 caratteri.
Rispondi solo con un array JSON di {n} oggetti {{"request": "...", "query": "..."}}.""",
    "en": """You are generating training data for a tiny assistant that helps non-technical people use
an old Linux PC. Write {n} different messages in which this person asks the computer to look
something up on the internet, on everyday topics (health, opening hours, recipes, news,
paperwork, weather, sport, hobbies).

The person: {persona}

The message is addressed to the computer, the way this person would say it ("can you look
up...", "I'd like to know...", "find...", "show me...", with or without greetings and detours).
For each message also give the search to run, as you would type it in a search engine: ONLY
words that appear in the message, spelled the same, adding none of your own, no quotes, at
most 100 characters.
Answer only with a JSON array of {n} objects {{"request": "...", "query": "..."}}.""",
}


INTENT_PROMPT = {
    "it": """Stai generando dati di addestramento per un piccolo assistente che aiuta persone non esperte
a usare un vecchio PC con Linux. Scrivi {n} messaggi diversi con cui questa persona chiede al
computer di: {concept}.

La persona: {persona}

Regole: solo italiano; da 2 parole a 2 frasi; come parlerebbe davvero questa persona; errori
di battitura e dialetto benvenuti se adatti; niente numeri d'elenco né spiegazioni.
Rispondi solo con un array JSON di {n} stringhe.""",
    "en": """You are generating training data for a tiny assistant that helps non-technical people use
an old Linux PC. Write {n} different messages in which this person asks the computer to: {concept}.

The person: {persona}

Rules: English only; 2 words to 2 sentences; the way this person would really say it; typos
welcome when they fit; no numbering or explanations.
Answer only with a JSON array of {n} strings.""",
}

REMINDER_PROMPT = {
    "it": """Stai generando dati di addestramento per un piccolo assistente per un vecchio PC con Linux.
Scrivi {n} messaggi diversi con cui questa persona chiede al computer di ricordarle una cosa
tra un certo tempo (da qualche minuto a qualche ora: medicine, telefonate, il forno, un
appuntamento, la lavatrice...). Indica il tempo in modi diversi: "tra 10 minuti", "fra
mezz'ora", "tra un'ora", "tra due ore", "tra un quarto d'ora", "tra 45 minuti".

La persona: {persona}

Per ogni messaggio indica "minutes" (il tempo in minuti, un intero) e "text" (cosa ricordare,
SOLO parole del messaggio scritte uguali, senza la parte di tempo, al massimo 80 caratteri).
Rispondi solo con un array JSON di {n} oggetti {{"request": "...", "minutes": 30, "text": "..."}}.""",
    "en": """You are generating training data for a tiny assistant for an old Linux PC. Write {n} different
messages in which this person asks the computer to remind them of something after some time
(a few minutes to a few hours: medicine, a phone call, the oven, an appointment, the
washing machine...). Say the time in different ways: "in 10 minutes", "in half an hour",
"in an hour", "in two hours", "in a quarter of an hour", "in 45 minutes".

The person: {persona}

For each message give "minutes" (the delay in minutes, an integer) and "text" (what to remember,
ONLY words from the message spelled the same, without the time part, at most 80 characters).
Answer only with a JSON array of {n} objects {{"request": "...", "minutes": 30, "text": "..."}}.""",
}

VOLUME_PROMPT = {
    "it": """Scrivi {n} messaggi diversi con cui questa persona chiede a un vecchio PC di mettere il
volume a un livello preciso, in percentuale o con un numero da 10 a 100 ("metti il volume
al 50", "volume a 80 per cento"). La persona: {persona}
Per ogni messaggio indica "percent" (intero da 10 a 100, il numero scritto nel messaggio).
Rispondi solo con un array JSON di {n} oggetti {{"request": "...", "percent": 50}}.""",
    "en": """Write {n} different messages in which this person asks an old PC to set the volume to a
precise level, as a percentage or a number from 10 to 100 ("set the volume to 50", "volume
80 percent"). The person: {persona}
For each message give "percent" (integer 10 to 100, the number written in the message).
Answer only with a JSON array of {n} objects {{"request": "...", "percent": 50}}.""",
}

NUMBERS = {
    "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
    "quarantacinque": 45, "cinquanta": 50, "novanta": 90,
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "ninety": 90,
}
HOUR = {"ora", "ore", "hour", "hours", "h"}
MINUTE = {"minuto", "minuti", "min", "minute", "minutes", "mins"}


def minutes_mentioned(text: str) -> set[int]:
    """Every delay in minutes a request literally states; the teacher's number
    is kept only if it is one of these (the label is never its arithmetic)."""
    t = text.lower().replace("’", "'")
    out: set[int] = set()
    if re.search(r"mezz'?\s?ora|half an hour", t):
        out.add(30)
    if re.search(r"(un )?quarto d'?\s?ora|quarter of an hour", t):
        out.add(15)
    if re.search(r"un'?\s?ora e mezza|an hour and a half", t):
        out.add(90)
    words = re.findall(r"\d+|[a-zà-ù]+", t.replace("'", " "))
    for i, w in enumerate(words[:-1]):
        n = int(w) if w.isdigit() else NUMBERS.get(w)
        unit = words[i + 1]
        if n is None:
            continue
        if unit in MINUTE:
            out.add(n)
        elif unit in HOUR:
            out.add(n * 60)
    if re.search(r"\b(un'?\s?ora|an hour)\b", t):
        out.add(60)
    return out


def valid_reminder(item, text_param) -> dict | None:
    if not isinstance(item, dict):
        return None
    req = str(item.get("request", "")).strip()
    text = " ".join(str(item.get("text", "")).split())
    try:
        minutes = int(item.get("minutes"))
    except (TypeError, ValueError):
        return None
    if not req or not text or minutes not in minutes_mentioned(req) or not 1 <= minutes <= 1440:
        return None
    req_words = {w.lower() for w in WORD.findall(req)}
    if any(w.lower() not in req_words for w in WORD.findall(text)):
        return None
    try:
        text_param.coerce(text)
    except ParamError:
        return None
    return {"request": req, "minutes": minutes, "text": text}


def valid_volume(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    req = str(item.get("request", "")).strip()
    try:
        pct = int(item.get("percent"))
    except (TypeError, ValueError):
        return None
    if not 10 <= pct <= 100 or str(pct) not in re.findall(r"\d+", req):
        return None
    return {"request": req, "percent": pct}


def parse_array(text: str) -> list:
    t = text.strip()
    return json.loads(t[t.find("["): t.rfind("]") + 1])


WORD = re.compile(r"\w+", re.UNICODE)


def valid_search(item, query_param, rng: random.Random | None = None) -> tuple[str, str] | None:
    """Keep a pair only if every word of the query is one of the person's words.

    The query may drop words and reorder them (that is what makes a good
    search), never add any: a label with a word the person did not write
    would teach the model to invent searches.
    """
    if not isinstance(item, dict):
        return None
    req, q = str(item.get("request", "")).strip(), " ".join(str(item.get("query", "")).split())
    if not req or not q:
        return None
    req_words = {w.lower() for w in WORD.findall(req)}
    q_words = [w.lower() for w in WORD.findall(q)]
    if not q_words or any(w not in req_words for w in q_words):
        return None
    # a bare query typed as the whole message happens, but the model must
    # mostly learn to cut the asking part away: keep only a few of those
    if len(q_words) >= len(WORD.findall(req)) and (rng or random).random() > 0.2:
        return None
    try:
        query_param.coerce(q)
    except ParamError:
        return None
    return req, q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="it", choices=["it", "en"])
    ap.add_argument("--per-persona", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--kinds", default="apps,close,search,intents,reminders,volume")
    ap.add_argument("--intents", help="comma-separated subset of intents.yaml (default: all)")
    a = ap.parse_args()

    random.seed(a.seed)
    teacher = OpenAICompat(os.environ["TEACHER_BASE_URL"], os.environ["TEACHER_MODEL"], os.environ["TEACHER_API_KEY"],
                           extra=json.loads(os.environ.get("TEACHER_EXTRA", "{}")))
    sfx = "" if a.lang == "it" else f"_{a.lang}"
    personas = yaml.safe_load((HERE / f"personas{sfx}.yaml").read_text(encoding="utf-8"))
    concepts = yaml.safe_load((HERE / "apps.yaml").read_text(encoding="utf-8"))
    cat = Catalog()
    query_param = cat.playbooks["web.search"].params["query"]
    text_param = cat.playbooks["reminder.set"].params["text"]
    intents = yaml.safe_load((HERE / "intents.yaml").read_text(encoding="utf-8"))
    if a.intents:
        intents = {k: v for k, v in intents.items() if k in a.intents.split(",")}
    kinds = set(a.kinds.split(","))
    seen: set[str] = set()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        def write(row: dict) -> bool:
            key = row["request"].lower()
            if key in seen:
                return False
            seen.add(key)
            f.write(json.dumps({**row, "lang": a.lang}, ensure_ascii=False) + "\n")
            f.flush()
            return True

        def ask(prompt: str, what: str) -> list:
            try:
                return parse_array(teacher.chat([{"role": "user", "content": prompt}]))
            except (ValueError, json.JSONDecodeError) as e:
                print(f"{what}: unparsable ({e})")
                return []

        for cid, c in (concepts.items() if "apps" in kinds else []):
            for pi, persona in enumerate(personas):
                prompt = OPEN_PROMPT[a.lang].format(n=a.per_persona, persona=persona, concept=c[a.lang])
                try:
                    items = parse_array(teacher.chat([{"role": "user", "content": prompt}]))
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"open {cid} persona {pi}: unparsable ({e})")
                    continue
                kept = sum(write({"fix_id": "app.open", "concept": cid, "persona": pi, "request": s.strip()})
                           for s in items if isinstance(s, str) and 2 <= len(s.strip()) <= 300)
                print(f"open {cid:16} persona {pi}: {kept}")

        for cid, c in (concepts.items() if "close" in kinds else []):
            for pi, persona in enumerate(personas):
                items = ask(CLOSE_PROMPT[a.lang].format(n=a.per_persona // 2 or 1, persona=persona,
                                                        concept=c[a.lang]), f"close {cid} persona {pi}")
                kept = sum(write({"fix_id": "app.close", "concept": cid, "persona": pi, "request": s.strip()})
                           for s in items if isinstance(s, str) and 2 <= len(s.strip()) <= 300
                           and not NOT_A_CLOSE_REQUEST.search(s))
                print(f"close {cid:15} persona {pi}: {kept}")

        for pi, persona in (enumerate(personas) if "search" in kinds else []):
            for _ in range(3):  # three batches per persona, for topic variety
                prompt = SEARCH_PROMPT[a.lang].format(n=a.per_persona * 2, persona=persona)
                try:
                    items = parse_array(teacher.chat([{"role": "user", "content": prompt}]))
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"search persona {pi}: unparsable ({e})")
                    continue
                kept = 0
                for it in items:
                    v = valid_search(it, query_param)
                    if v:
                        kept += write({"fix_id": "web.search", "persona": pi, "request": v[0], "query": v[1]})
                print(f"search persona {pi}: {kept}/{len(items)}")


        for iid, it in (intents.items() if "intents" in kinds else []):
            for pi, persona in enumerate(personas):
                items = ask(INTENT_PROMPT[a.lang].format(n=a.per_persona // 2 or 1, persona=persona,
                                                         concept=it[a.lang]), f"{iid} persona {pi}")
                kept = sum(write({"fix_id": it["fix_id"], "intent": iid, "params": it["params"], "persona": pi,
                                  "request": x.strip()})
                           for x in items if isinstance(x, str) and 2 <= len(x.strip()) <= 300)
                print(f"intent {iid:18} persona {pi}: {kept}")

        for pi, persona in (enumerate(personas) if "reminders" in kinds else []):
            for _ in range(2):
                items = ask(REMINDER_PROMPT[a.lang].format(n=a.per_persona * 2, persona=persona), f"reminder {pi}")
                good = [r for r in (valid_reminder(x, text_param) for x in items) if r]
                kept = sum(write({"fix_id": "reminder.set", "persona": pi, "request": r["request"],
                                  "params": {"minutes": r["minutes"], "text": r["text"]}}) for r in good)
                print(f"reminder persona {pi}: {kept}/{len(items)}")

        for pi, persona in (enumerate(personas) if "volume" in kinds else []):
            items = ask(VOLUME_PROMPT[a.lang].format(n=a.per_persona, persona=persona), f"volume {pi}")
            good = [v for v in (valid_volume(x) for x in items) if v]
            kept = sum(write({"fix_id": "audio.set_volume", "persona": pi, "request": v["request"],
                              "params": {"percent": v["percent"]}}) for v in good)
            print(f"volume persona {pi}: {kept}/{len(items)}")


if __name__ == "__main__":
    main()
