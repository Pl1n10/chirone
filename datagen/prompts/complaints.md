You are generating training data for a tiny model that helps non-technical
people fix their old Linux PCs. Write {n} different messages that a person
could type (or dictate) to ask for help.

The person: {persona}
What actually happens on their computer (they do NOT know the cause): {symptom}

Rules:
- Italian only. Vary length from 3 words to 3 sentences.
- Describe only what they see, hear or feel. Never name the technical cause,
  never use words like DNS, NetworkManager, CUPS, PipeWire, dpkg, apt,
  processo, servizio, driver, cache, unless the persona would plausibly
  have read them on screen.
- Some messages should be vague or slightly misleading, like real people.
- Typos, missing punctuation and dialect are welcome when they fit the persona.
- Do not number them and do not add explanations.

Answer with a JSON array of {n} strings and nothing else.
