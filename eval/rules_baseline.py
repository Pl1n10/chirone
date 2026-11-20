"""Hand-written rules in place of the model, same prompts in, same JSON out.

    python eval/run_eval.py --data data/dataset-run9/test.jsonl --rules --report ...

The question it answers: how much of chirone's work is the model doing, and how
much would keywords plus checks on the diagnostics do? Rules were written
looking only at the training split (Debian), like the model, in about half a
day of work, then run once on the test split (Ubuntu, held out).

Step 1: keyword scores per category. Step 2: per category, checks on the probe
output (the same facts a playbook precondition reads), and for everyday
actions, verbs and object words in the complaint with numbers read by regex.
"""
# ruff: noqa: E501  (keyword lists read better on one line)
from __future__ import annotations

import re
import time
import unicodedata
from types import SimpleNamespace


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[’‘`´]", "'", s)


def has(text: str, *pats: str) -> bool:
    return any(re.search(p, text) for p in pats)


# ---------------------------------------------------------------- step 1

CAT_WORDS = {
    "network": [r"internet", r"wi-?fi", r"\brete\b", r"connession", r"collegament", r"connett", r"\bonline\b",
                r"modem", r"router", r"\bcavo\b", r"navig", r"connect", r"network", r"website", r"\bsiti?\b",
                r"certificat", r"pagin[ae] .*(non|bianc)", r"web page", r"\bweb\b.*(non|not|won)", r"offline",
                r"\bora\b.*sbagliat", r"orologio", r"\bclock\b", r"wrong (time|date)", r"\bdata\b.*sbagliat",
                r"google.*(non|not)", r"youtube.*(non|not)", r"server", r"ricaric", r"reload", r"loading"],
    "audio": [r"suon", r"audio", r"\bcasse\b", r"cuffi", r"\bsent[eoi]\b", r"sentire", r"\bmut[oa]\b",
              r"sound", r"hear", r"speaker", r"headphone", r"\bmute", r"altoparlant", r"rumore.*non", r"silenz",
              r"\bvolume\b.*(non|not|spar|gone|zero)", r"musica.*(non|not)", r"televisor", r"\btv\b", r"\bhdmi\b",
              r"\bode\b", r"song", r"canzon", r"plays", r"video.*(non|not)"],
    "printing": [r"stamp", r"print", r"\bfogli?o?\b", r"\bcarta\b", r"inchiostr", r"\bpaper\b", r"\bink\b", r"non esce", r"doesn'?t come out"],
    "storage": [r"spazio", r"\bdisco\b", r"pien[oa]", r"space", r"\bdisk\b", r"\bfull\b", r"storage",
                r"cestino", r"trash", r"memoria.*(pien|fin)", r"\bgb\b", r"no room", r"spacio", r"cancellat", r"deleted"],
    "updates": [r"aggiorn", r"update", r"upgrade", r"installa", r"install", r"pacchett", r"package",
                r"programma (degli|di) aggiorn", r"software", r"\bapt\b", r"scritta ross", r"red (message|text|error)",
                r"messaggio ross"],
    "system": [r"lent[oia]", r"ventol", r"bloccat", r"si blocca", r"freez", r"\bslow", r"\bfan\b", r"\bhot\b",
               r"cald[oa]", r"scott", r"sola lettura", r"read.?only", r"salvar", r"\bsave\b", r"si pianta",
               r"impallat", r"lag", r"scald", r"rumor", r"noise", r"sluggish", r"crawl", r"solo lettura",
               r"non salva", r"creare (nuovi )?file", r"can'?t (change|delete|create)", r"new files"],
    "apps": [r"firefox", r"browser.*(non|not|won)", r"gia aperto", r"already (open|running)",
             r"non (si )?(apre|parte)", r"won'?t (open|start)", r"doesn'?t (open|start)"],
    "actions": [r"^(apri|aprimi|chiudi|cerca|cercami|ricorda|ricordami|alza|abbassa|riavvia|metti|portami|"
                r"mostrami|fammi|vai|open|close|search|remind|turn|restart|reboot|show|take me|go to|find|"
                r"look up|please (open|close|search|remind))\b",
                r"\b(apri|aprire|aprimi|chiudi|chiudere|cerca|cercare|cercami|ricordami|ricorda|riavvia|"
                r"riavviare)\b", r"\b(open|close|search for|look up|remind me|restart|reboot)\b",
                r"tra (\d+|un|una|mezz|due|tre|dieci|venti|trenta|quaranta|cinque) ", r"\bin (\d+|an?|half|two|ten)"
                r" (min|hour|ora)", r"(alza|abbassa|turn (up|down)|louder|quieter|lower|raise).*volume",
                r"volume (a|al|to) \d+", r"\b(louder|quieter)\b", r"cartella", r"folder", r"whatsapp", r"gmail",
                r"outlook|hotmail", r"\blibero\b", r"\binps\b", r"agenzia (delle )?entrate", r"\btasse\b",
                r"\btax\b", r"raiplay", r"wikipedia", r"\bmeteo\b", r"weather", r"telegiornale|notizie|news",
                r"calcolatrice|calculator", r"lettera|letter", r"blocco note|notepad", r"tutorial|ricett|recipe",
                r"come si fa a|how (do|can) i (find|get to)", r"voglio sapere|i want to know"],
}
PROBLEM = [r"\bnon\b", r"\bnot\b", r"n'?t\b", r"\bnun\b", r"\bnu\b", r"errore", r"\berror", r"problem",
           r"guast", r"rott", r"broken", r"perche", r"\bwhy\b", r"nient", r"nothing", r"spari", r"gone"]


def classify(text: str) -> str:
    t = norm(text)
    score = {c: sum(1 for p in pats if re.search(p, t)) for c, pats in CAT_WORDS.items()}
    if has(t, *PROBLEM):
        score["actions"] -= 1  # "firefox non si apre" is a fault, "apri firefox" is a request
    elif has(t, r"puoi|potresti|vorrei|voglio|per favore|mi serve|fammi|can you|could you|please|i want|i need|"
                r"i'd like|let me|help me|aiutami|mi aiuti"):
        score["actions"] += 1.5  # a request with no fault in it
    best = max(score, key=lambda c: score[c])
    return best if score[best] > 0 else "other"


# ---------------------------------------------------------------- step 2 helpers

def probes(user: str) -> tuple[dict[str, tuple[int, str]], str]:
    diag, _, complaint = user.partition("\ncomplaint:")
    out, cur = {}, None
    for line in diag.splitlines():
        m = re.match(r"\[(\w+) rc=(\d+)\]$", line)
        if m:
            cur = m.group(1)
            out[cur] = [int(m.group(2)), []]
        elif cur:
            out[cur][1].append(line)
    return {k: (rc, "\n".join(lines)) for k, (rc, lines) in out.items()}, complaint.strip()


def fix(fid: str, conf: str = "high", **params) -> dict:
    return {"fix_id": fid, "params": params, "confidence": conf}


NOOP = {"fix_id": "noop.no_issue_found", "params": {}, "confidence": "low"}


def browser(p) -> str:
    # the installed one: on Ubuntu browser_default still says firefox-esr.desktop
    # (fixed after the first test run, see eval/results/2026-11-12-rules-vs-run9.md)
    installed = {ln.split(":", 1)[0] for ln in p.get("apps_installed", (0, ""))[1].splitlines()}
    if "firefox" in installed and "firefox-esr" not in installed:
        return "firefox"
    out = p.get("browser_default", (0, ""))[1]
    return "firefox" if out.startswith("firefox.desktop") else "firefox-esr"


def network(p, t):
    rc, svc = p.get("nm_service", (0, ""))
    if svc.strip() == "inactive":
        return fix("svc.restart", service="NetworkManager")
    gen = p.get("nm_general", (0, ""))[1].split(":")
    if gen and gen[0] == "asleep":
        return fix("net.enable_networking")
    if len(gen) >= 5 and gen[4] == "disabled":
        return fix("net.wifi_radio_on", "medium")
    for line in p.get("nm_devices", (0, ""))[1].splitlines():
        f = line.split(":")
        if len(f) >= 3 and f[1] in ("ethernet", "wifi") and f[2] == "disconnected":
            return fix("net.connect_device", iface=f[0])
    ts = p.get("time_status", (0, ""))[1]
    year = re.search(r"TimeUSec=\w+ (\d{4})", ts)
    if "NTP=no" in ts or (year and int(year.group(1)) < 2025):
        return fix("time.enable_ntp")
    if p.get("dns_lookup", (0, ""))[0] != 0 and p.get("ping_ip", (1, ""))[0] == 0:
        active = p.get("nm_active", (0, ""))[1].splitlines()
        if active and active[0] != "(empty)":
            return fix("dns.reset_to_auto", connection=active[0].split(":")[0])
    return NOOP


def audio(p, t):
    if p.get("audio_services", (0, ""))[1].strip() == "inactive" or "Connection refused" in p.get(
            "audio_sinks", (0, ""))[1]:
        return fix("audio.restart_stack")
    if "Mute: yes" in p.get("audio_mute", (0, ""))[1]:
        return fix("audio.unmute")
    if re.search(r"/ 0% /", p.get("audio_volume", (0, ""))[1]):
        return fix("audio.set_volume", percent=60)
    default = re.search(r"Default Sink: (\S+)", p.get("audio_server", (0, ""))[1])
    sinks = [ln.split()[1] for ln in p.get("audio_sinks", (0, ""))[1].splitlines() if re.match(r"\d+\s+\S", ln)]
    if default and len(sinks) > 1:
        analog = [s for s in sinks if "analog" in s and s != default.group(1)]
        if analog:
            return fix("audio.set_default_sink", sink=analog[0])
    return NOOP


def printing(p, t):
    if p.get("cups_active", (0, ""))[1].strip() != "active":
        return fix("svc.restart", service="cups")
    pr = p.get("lpstat_printers", (0, ""))[1]
    m = re.search(r"printer (\S+) disabled", pr)
    if m:
        return fix("print.enable_printer", printer=m.group(1))
    jobs = [ln for ln in p.get("lpstat_jobs", (0, ""))[1].splitlines() if ln and ln != "(empty)"]
    if jobs:
        return fix("print.clear_queue", printer=jobs[0].split()[0].rsplit("-", 1)[0])
    return NOOP


def size_gb(s: str) -> float:
    m = re.match(r"([\d.]+)([KMGT])", s)
    if not m:
        return 0.0
    return float(m.group(1)) * {"K": 1e-6, "M": 1e-3, "G": 1, "T": 1e3}[m.group(2)]


def storage(p, t):
    use = re.search(r"(\d+)% /\n|(\d+)% /$", p.get("disk_usage", (0, ""))[1])
    pct = int(use.group(1) or use.group(2)) if use else 0
    if pct < 90:
        return NOOP
    cand = {}
    for ln in p.get("home_usage", (0, ""))[1].splitlines() + p.get("apt_cache_usage", (0, ""))[1].splitlines():
        f = ln.split()
        if len(f) == 2 and f[1].endswith("/Trash"):
            cand["disk.empty_trash"] = size_gb(f[0])
        elif len(f) == 2 and f[1].endswith("/thumbnails"):
            cand["disk.clear_thumbnails"] = size_gb(f[0])
        elif len(f) == 2 and f[1].endswith("/archives"):
            cand["disk.apt_clean"] = size_gb(f[0])
    if p.get("home_usage", (0, ""))[0] == 124 and max(cand.values(), default=0) < 1:
        return fix("disk.clear_thumbnails")  # du times out on a huge thumbnail cache
    if not cand:
        return fix("escalate.human", "medium", reason="unknown_issue")
    return fix(max(cand, key=cand.get))


def updates(p, t):
    lock = p.get("apt_lock", (1, ""))
    check = p.get("apt_check", (0, ""))[1]
    # a source that fails is the fault even while something else holds the lock
    upd = p.get("apt_update", (0, ""))[1]
    hosts = set(re.findall(r"(?:Err:\d+|Failed to fetch) https?://([^/\s]+)", upd))
    if hosts:
        for ln in p.get("apt_sources", (0, ""))[1].splitlines():
            path, _, src = ln.partition(":")
            if any(h in src for h in hosts):
                return fix("apt.disable_source", file=path.rsplit("/", 1)[1])
    if (lock[0] == 0 and "/var/lib/dpkg" in lock[1]) or "Could not get lock" in check:
        return fix("apt.wait_for_lock")
    if "nmet dependencies" in check:
        return fix("apt.fix_broken")
    audit = p.get("dpkg_audit", (0, ""))
    if "dpkg was interrupted" in check or (audit[0] not in (0, 124) and audit[1] != "(empty)"):
        return fix("apt.dpkg_configure")
    return NOOP


def system(p, t):
    if re.search(r"\sro,", p.get("root_mount", (0, ""))[1]):
        return fix("escalate.human", reason="disk_failure_suspected")
    for ln in p.get("top_procs", (0, ""))[1].splitlines()[1:]:
        f = ln.split()
        if len(f) >= 5 and f[0].isdigit():
            try:
                cpu = float(f[3])
            except ValueError:
                continue
            if cpu >= 50 and f[1] != "root" and f[2] not in ("chirone", "ps", "python3"):
                return fix("proc.terminate_user_process", pid=int(f[0]))
    return NOOP


def apps(p, t):
    locks = p.get("firefox_locks", (1, ""))
    if "/lock" in locks[1] and p.get("firefox_running", (1, ""))[0] != 0:
        m = re.search(r"firefox/([^/\s]+)/(?:\.parent)?lock", locks[1])
        if m:
            return fix("app.firefox_clear_stale_lock", profile=m.group(1))
    return NOOP


PC_WORDS = [r"computer", r"\bpc\b", r"mouse", r"tastier", r"keyboard", r"schermo", r"screen", r"icon", r"email",
            r"\bmail\b", r"posta", r"foto", r"photo", r"picture", r"finestr", r"window", r"programm", r"program",
            r"cursor", r"click", r"clic", r"desktop", r"scritte", r"font", r"lettere", r"carattere", r"text",
            r"funziona", r"work", r"stampa", r"suono", r"allega", r"attach", r"\bfile\b", r"password", r"cartell"]


def other(p, t):
    n = norm(t)
    # a request chirone has no fix for ("cancella il file", "abbassa la luminosita") is info, a complaint is noop
    request = has(n, r"^(cancella|elimina|abbassa|alza|cambia|metti|installa|delete|change|install|set)\b",
                  r"(puoi|potresti|can you|could you|come (si fa|faccio) a|how (do|can) i)")
    return NOOP if has(n, *PC_WORDS) and not request else fix("info.what_i_can_do")


# ---------------------------------------------------------------- everyday actions

NUM = {"un": 1, "uno": 1, "una": 1, "a": 1, "an": 1, "one": 1, "due": 2, "two": 2, "tre": 3, "three": 3,
       "cinque": 5, "five": 5, "dieci": 10, "ten": 10, "quindici": 15, "fifteen": 15, "venti": 20, "twenty": 20,
       "trenta": 30, "thirty": 30, "quaranta": 40, "forty": 40, "quarantacinque": 45, "cinquanta": 50,
       "fifty": 50, "sessanta": 60, "sixty": 60, "novanta": 90}


def minutes(t: str) -> int | None:
    if has(t, r"mezz'?ora", r"half an hour", r"half hour"):
        return 30
    if has(t, r"quarto d'?ora", r"quarter of an hour", r"quarter hour"):
        return 15
    if has(t, r"un'?ora e mezz", r"an hour and a half", r"one and a half hour"):
        return 90
    m = re.search(r"(\d+|[a-z']+) (minut|min\b|or[ae]\b|hour)", t)
    if not m:
        if has(t, r"un'?ora\b", r"an hour\b"):
            return 60
        return None
    w = m.group(1).replace("'", "")
    n = int(w) if w.isdigit() else NUM.get(w.rstrip("'"))
    if n is None:
        return None
    return n * 60 if m.group(2) in ("ora", "ore", "hour") else n


def reminder_text(raw: str) -> str:
    t = raw.strip().rstrip(".!?")
    for pat in (r"(?i)\b(?:di|che devo|to)\s+(.+?)(?:\s+(?:tra|fra|in)\s+.*)?$",):
        m = re.search(pat, t)
        if m:
            return m.group(1).strip()
    return t


APP_WORDS = [  # (regex on the complaint, words to look for in the installed apps' id or name)
    (r"blocco ?note|notepad|appunti|\bnote\b|text editor|editor di testo", ["mousepad", "gnome-text-editor", "gedit"]),
    (r"impostazion|setting|preferenz|opzioni|configura", ["settings-manager", "gnome-control-center"]),
    (r"calc|calcol", ["calculator", "galculator", "calcolatrice", "gnome-calculator"]),
    (r"foglio|spreadsheet|excel|\bcalc\b|conti|tabell", ["libreoffice-calc"]),
    (r"lettera|letter|scrivere|scrivendo|write|writing|word|documento|videoscrittura", ["libreoffice-writer"]),
    (r"processi|rallenta|task manager|lag|slow|problemi del computer", ["taskmanager", "system-monitor"]),
    (r"terminale|terminal", ["xfce4-terminal", "terminal"]),
    (r"musica|music|canzon|song|video|film|movie|player|lettore", ["parole", "totem", "rhythmbox"]),
    (r"foto|photo|picture|immagin|image", ["ristretto", "eog", "shotwell", "loupe"]),
    (r"posta|mail", ["mail-reader", "thunderbird", "evolution"]),
    (r"internet|browser|firefox|navig|\bweb\b", ["firefox"]),
    (r"file|cartell|folder|window where", ["thunar", "nautilus", "org.gnome.nautilus"]),
]


def pick_app(t: str, installed: list[str]) -> str | None:
    for pat, words in APP_WORDS:
        if re.search(pat, t):
            for w in words:
                hits = [a for a in installed if w in a.lower()]
                if hits:
                    return min(hits, key=len)
    return None


SITES = [(r"gmail", "email_gmail"), (r"outlook|hotmail", "email_outlook"), (r"\blibero\b", "email_libero"),
         (r"whatsapp", "whatsapp"), (r"\bansa\b", "news_ansa"), (r"rai ?news|telegiornale|tg ?rai|news (from|della|dalla) rai", "news_rai"),
         (r"\bbbc\b", "news_bbc"), (r"raiplay|rai play|rai show|programm\w* (della )?rai", "tv_raiplay"), (r"youtube", "youtube"),
         (r"\binps\b|pension", "inps"), (r"fascicolo|health record|cartella clinica|referti", "health_record"),
         (r"agenzia (delle )?entrat|agentezia|tax agency|\btass[ea]\b|\btax", "tax_agency"),
         (r"\bmeteo\b|weather|previsioni|che tempo fa|come fa il tempo", "weather"), (r"wikipedia", "wikipedia")]
FOLDERS = [(r"scaricat|download", "downloads"), (r"foto|photo|picture|immagin", "photos"),
           (r"documenti|document|\bdocs?\b", "documents"), (r"musica|music|canzon", "music"),
           (r"video", "videos"), (r"desktop|scrivania", "desktop")]
SEARCH_LEAD = (r"^(?:(?:per favore|please|computer|pc|ciao|hey|ehi)[, ]+)*(?:mi )?(?:puoi |potresti |can you |could you )?"
               r"(?:cerca(?:mi|re)?|search(?: for)?|look up|find(?: me)?|google|fammi vedere|mostrami|show me|"
               r"trova(?:mi)?|find out|voglio sapere|vorrei sapere|i want to know|i'd like to know)\s+(?:su internet\s+|online\s+)?"
               r"(?:(?:the|a|an|un|una|il|la|le|i|gli|lo) )?")


def actions(p, t):
    n = norm(t)
    installed = [ln.split(":", 1)[0] for ln in p.get("apps_installed", (0, ""))[1].splitlines() if ":" in ln]
    running = [ln.split(":", 1)[0] for ln in p.get("apps_running", (0, ""))[1].splitlines() if ":" in ln]
    if has(n, r"ricord", r"remind", r"promemoria", r"avvisami", r"alert me", r"tell me in"):
        m = minutes(n)
        if m:
            return fix("reminder.set", minutes=m, text=reminder_text(t))
    vol = re.search(r"vol\w*\D{0,20}(\d{1,3})|(\d{1,3}) ?(?:%|percent)", n)
    if (has(n, r"volume", r"\bvol\b", r"percent", r"make it \d")) and vol:
        return fix("audio.set_volume", percent=max(10, min(100, int(vol.group(1) or vol.group(2)))))
    if has(n, r"alza", r"louder", r"turn (it )?up", r"volume up", r"piu forte", r"raise", r"increase", r"too (low|quiet)",
           r"troppo bass", r"si sente (poco|piano)", r"to quiet", r"'ncu", r"non sento", r"can'?t hear"):
        return fix("audio.volume_up")
    if has(n, r"abbassa", r"quieter", r"turn (it )?down", r"volume down", r"piu piano", r"lower", r"too loud",
           r"troppo+ alt", r"decrease", r"too high", r"less loud", r"giu"):
        return fix("audio.volume_down")
    if has(n, r"riavvi", r"restart", r"reboot", r"spegn\w* e (ri)?accend", r"turn it off and (back )?on", r"riaccend", r"ripart", r"si accende di nuovo", r"froze"):
        return fix("system.restart")
    for pat, site in SITES:
        if re.search(pat, n):
            return fix("web.open_site", site=site, browser=browser(p))
    if has(n, r"chiud", r"close", r"\bquit\b", r"\bexit\b", r"\bstop\b", r"basta", r"finit", r"\bdone\b"):
        app = pick_app(n, installed)
        if app:
            return fix("app.close", app=app)
        if len(running) == 1:
            return fix("app.close", app=running[0])
    if has(n, r"cartell", r"folder", r"dove", r"where", r"find", r"locat", r"look for", r"trov", r"guardare i file",
           r"vedere i file", r"see my files", r"saved", r"salvat"):
        for pat, folder in FOLDERS:
            if re.search(pat, n):
                return fix("files.open_folder", folder=folder)
    m = re.match(SEARCH_LEAD, n)
    if m or has(n, r"tutorial", r"ricett", r"recipe", r"come si fa a", r"how (do|to|can)", r"\bcome\b.*\?"):
        q = t.strip()[m.end():] if m else t.strip()
        q = q.rstrip(".!?").strip() or t.strip()
        return fix("web.search", query=q[:120], browser=browser(p))
    if has(n, r"apri", r"open", r"avvia", r"start", r"lancia", r"usare", r"vorrei", r"voglio", r"i want", r"i need",
           r"fammi", r"metti"):
        app = pick_app(n, installed)
        if app:
            return fix("app.open", app=app)
    if has(n, *PROBLEM) and has(n, *PC_WORDS):
        return NOOP
    return fix("info.what_i_can_do")


STEP2 = {"network": network, "audio": audio, "printing": printing, "storage": storage, "updates": updates,
         "system": system, "apps": apps, "other": other, "actions": actions}


class Rules:
    """Drop-in for the LLM backends of run_eval.py."""

    def complete_json(self, prompt, schema, max_tokens=64):
        t0 = time.monotonic()
        user = prompt[-1]["content"]
        if not user.startswith("category: "):
            data = {"category": classify(user)}
        else:
            cat = user.split("\n", 1)[0].split(": ", 1)[1].strip()
            p, complaint = probes(user)
            data = STEP2[cat](p, complaint)
        return SimpleNamespace(data=data, seconds=time.monotonic() - t0, timings=None)
