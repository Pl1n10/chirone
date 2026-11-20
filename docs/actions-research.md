# Everyday actions: what older and non-technical users actually do

Why the `actions` category contains what it contains. Research done on
2026-11-08; Eurostat figures pulled from the Eurostat API (datasets updated
2026-04-17). Percentages are of **all persons** in the age band, not only of
internet users.

## Evidence

**Eurostat, ages 65–74, % of all persons, last 3 months (`isoc_ci_ac_i`)**

| Activity | EU 2024 | IT 2024 | EU 2025 | IT 2025 |
|---|---|---|---|---|
| Calls, video calls or instant messaging | 61.5 | 61.0 | 66.6 | 66.5 |
| Email | 56.1 | 45.6 | 58.2 | 49.6 |
| Finding information about goods and services | 53.8 | 37.0 | 51.0 | 39.2 |
| Reading online news | 49.0 | 38.1 | 51.9 | 40.2 |
| Seeking health information | 44.9 | 41.8 | 46.8 | 46.8 |
| Internet banking | 44.8 | 34.0 | 48.0 | 36.7 |
| Streaming TV or video | 44.2 | 40.4 | n/a | n/a |
| Booking a medical appointment online | 28.2 | 21.8 | n/a | n/a |
| Music or web radio | 26.1 | 22.3 | n/a | n/a |

**Public services, ages 65–74, last 12 months, 2024 (`isoc_ciegi_ac`):** used a
public-authority website or app: EU 50.0%, IT 38.7%; downloaded or printed
official forms: EU 25.0%, IT 19.8%; booked an appointment: EU 21.9%, IT 19.7%.

**What older adults ask out loud.** In-home study with Echo Dot, 15 older
adults, 2,552 logged requests (Mahmood et al., 2024): 44.3% functional
(reminders, weather, timers), 29.5% entertainment; most frequent single
requests: questions (414), music (324), reminders (251), radio (232), weather
(205), timers (174). A 2026 Nest Hub study with 20 older adults (Grigorovich
et al.) ranks music first, then reminders/timers, then weather.

**Other sources.** ISTAT 2024: 68.1% of Italians aged 65–74 and 31.4% of
those over 75 used the internet. Age UK (2026), partially excluded over-65s:
email 62%, shopping 52%, calls/video calls 48%; course participants ask to
learn video calls, sending photos and managing appointments online. Italian
digital-facilitation points (Rome 2025, Piedmont) report SPID/CIE activation,
INPS, health records, booking visits and downloading medical reports as the
most common requests (no national counts found).

## What Chirone does with it

Every action is a closed-catalogue entry run as an argv at user level; the
model picks the action and fills validated parameters, never a command.

| Action | Covers | Status |
|---|---|---|
| `app.open {installed app}` | everything a program does | done |
| `web.search {query}` | information, health, news | done |
| `web.open_site {site}` (vetted list) | email, news, health records, public services, weather, video calls | planned |
| `files.open_folder {folder}` | photos, documents, downloads | planned |
| `audio.volume {up, down, mute}` | video, radio, video calls | planned |
| `reminder.set {minutes, text}` | reminders and timers | planned |
| open / print the latest download (confirmation) | medical reports, official forms | planned |
| radio, text size | music, accessibility | later |

**Deliberately excluded:** sending email or messages and placing calls (acting
in the person's name, irreversible, exploitable by scams); banking, payments,
logging in with SPID/CIE (credentials, money, the typical target of fraud
against older people); opening any URL the person dictates or reads in an
email (phishing); deleting files (irreversible, and a sub-1B model easily
confuses "that photo"); installing software (root; stays in the repair flow);
filling in official forms or giving medical advice (out of reach for a small
model, and a legal responsibility).

## For the proposal

> Based on Eurostat 2024 data, the most common online activities of Europeans
> aged 65–74 are calls and messaging (61%), email (56%), finding information
> (54%), reading news (49%), seeking health information (45%) and internet
> banking (45%); half of them (50%) used a public-authority website in the
> previous year, and a quarter downloaded or printed official forms.

> Rather than letting a small model compose commands, Chirone maps these needs
> onto a closed catalogue of user-level actions — opening vetted official
> websites, opening and printing the document just downloaded, setting a
> reminder — none of which sends messages, handles credentials or moves money.

> Field studies of voice assistants with older adults confirm the priorities:
> functional requests such as reminders, timers and weather made up 44% of
> 2,552 logged queries, and entertainment a further 30% (Mahmood et al., 2024).

## Sources

- Eurostat `isoc_ci_ac_i`: https://ec.europa.eu/eurostat/databrowser/view/isoc_ci_ac_i/default/table
- Eurostat `isoc_ciegi_ac`: https://ec.europa.eu/eurostat/databrowser/view/isoc_ciegi_ac/default/table
- Eurostat, People online in 2024: https://ec.europa.eu/eurostat/web/products-eurostat-news/w/ddn-20241217-1
- ISTAT, Cittadini e ICT 2024: https://www.istat.it/wp-content/uploads/2025/04/REPORT_CITTADINI-E-ICT_2024.pdf
- Age UK, Digital Done Right (2026): https://www.ageuk.org.uk/siteassets/documents/reports-and-publications/reports-and-briefings/active-communities/digital-done-right-report
- Mahmood, Wang, Huang (2024): https://arxiv.org/html/2403.02421v3
- Grigorovich et al., Gerontechnology (2026): https://journal.gerontechnology.org/currentIssueContent.aspx?aid=4794
- Mondo Digitale, facilitation notes (Nov 2025): https://mondodigitale.org/sites/default/files/allegati/progetti/2025/Nota-Novembre-Facilitazione-2025.pdf
- Regione Piemonte, digital facilitation points: https://www.regione.piemonte.it/web/node/18239

The figures were collected by an automated research pass; check the Eurostat
numbers against the databrowser before quoting them in the proposal.
