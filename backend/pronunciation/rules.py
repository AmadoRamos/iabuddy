"""Errores de pronunciación típicos de un hispanohablante (DISENO §7.4), con su explicación en español.

Los símbolos son los de eSpeak `en-us`, que son los del vocabulario del modelo.
"""

# fonema correcto → [(lo que suena en su lugar, explicación)]
SWAPS: dict[str, list[tuple[str, str]]] = {
    "ɪ": [("iː", "Suena como la «i» larga (ship → sheep). La /ɪ/ es corta y relajada, entre «i» y «e».")],
    "iː": [("ɪ", "Suena como la /ɪ/ corta (sheep → ship). Alarga la «i» y estira los labios.")],
    "æ": [("a", "Suena como la «a» española (cat → cot). La /æ/ se abre más: baja la mandíbula y estira los labios."),
          ("ʌ", "Suena como /ʌ/ (cat → cut). La /æ/ se abre más: baja la mandíbula y estira los labios.")],
    "ʌ": [("a", "Suena como la «a» española. La /ʌ/ es más corta y relajada, con la boca menos abierta.")],
    "ʊ": [("uː", "Suena como la «u» larga (full → fool). La /ʊ/ es corta y relajada.")],
    "uː": [("ʊ", "Suena como la /ʊ/ corta (fool → full). Alarga la «u» y redondea los labios.")],
    "θ": [("t", "Suena como «t» (three → tree). Pon la punta de la lengua entre los dientes y sopla."),
          ("s", "Suena como «s» (think → sink). Pon la punta de la lengua entre los dientes y sopla."),
          ("f", "Suena como «f» (three → free). Pon la punta de la lengua entre los dientes, no el labio.")],
    "ð": [("d", "Suena como «d» (they → day). Pon la lengua entre los dientes y deja vibrar la voz.")],
    "v": [("b", "Suena como «b» (very → berry). En inglés son distintas: apoya los dientes de arriba en el labio de abajo.")],
    "ʃ": [("tʃ", "Suena como «ch» (share → chair). Sin golpe: el aire sale seguido, como al pedir silencio.")],
    "tʃ": [("ʃ", "Suena como /ʃ/ (chair → share). Empieza con un golpe de lengua, como la «ch» española.")],
    "j": [("dʒ", "Suena como /dʒ/ (yet → jet). Es más suave, como una «i» muy breve, sin tocar el paladar.")],
    "dʒ": [("j", "Suena como «y» suave (jet → yet). Empieza con la lengua tocando el paladar.")],
    "z": [("s", "Suena como «s» (zoo → sue). La /z/ hace vibrar la garganta, como un zumbido.")],
    "ŋ": [("n", "Suena como «n» (thing → thin). Termina con la parte de atrás de la lengua en el paladar, sin soltar «g».")],
}
EPENTHESIS = ("La «e» de más al principio (speak → espeak): en inglés se empieza directamente con la «s», "
              "alargándola un poco.")
ED_ENDING = ("La terminación «-ed» suena como una sílaba de más (walked → walk-ed). Aquí es solo un sonido "
             "/t/ o /d/: no se pronuncia la «e».")
SILENT = {"t", "d"}
# Un nativo también las reduce (to → /tə/, and → /ən/, did you → /dɪdʒu/): sus vocales, /z/ y /j/ no dicen
# nada. Sus consonantes sí (the → /də/ es un error de verdad). Calibrado con Kokoro como voz nativa.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "at", "in", "on", "for", "from", "with", "as", "if", "than",
    "that", "this", "these", "those", "there", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "our", "their", "is", "am", "are", "was", "were", "be", "been", "do",
    "does", "did", "have", "has", "had", "can", "could", "will", "would", "shall", "should", "must", "not",
    "i'm", "i've", "i'll", "i'd", "you're", "it's", "we're", "they're", "ve", "m", "s", "t", "d", "ll", "re",
}
WEAK = {"ɪ", "iː", "æ", "ʌ", "ʊ", "uː", "z", "j", "ŋ"}


# Se escriben igual pero suenan distinto según la frase (I live / a live concert), y eSpeak no sabe gramática:
# vale la que mejor encaje con tu audio. Mejor dejar pasar un error que acusarte de uno que no cometiste.
HOMOGRAPHS = {
    "live": "l ɪ v|l aɪ v", "lives": "l ɪ v z|l aɪ v z", "read": "ɹ iː d|ɹ ɛ d", "lead": "l iː d|l ɛ d",
    "close": "k l oʊ s|k l oʊ z", "closed": "k l oʊ z d|k l oʊ s t", "use": "j uː s|j uː z", "used": "j uː z d|j uː s t",
    "record": "ɹ ɛ k ɚ d|ɹ ᵻ k ɔːɹ d", "project": "p ɹ ɑː dʒ ɛ k t|p ɹ ə dʒ ɛ k t",
    "present": "p ɹ ɛ z ə n t|p ɹ ᵻ z ɛ n t", "address": "æ d ɹ ɛ s|ə d ɹ ɛ s", "wind": "w ɪ n d|w aɪ n d",
    "tear": "t ɛɹ|t ɪɹ", "object": "ɑː b dʒ ɛ k t|ə b dʒ ɛ k t", "content": "k ɑː n t ɛ n t|k ə n t ɛ n t",
    "produce": "p ɹ ə d uː s|p ɹ oʊ d uː s", "does": "d ʌ z|d oʊ z",
}


def pronunciations(word: str, phones: tuple[str, ...]) -> list[tuple[str, ...]]:
    """La de eSpeak y las demás formas válidas de esa palabra."""
    others = [tuple(o.split()) for o in HOMOGRAPHS.get(word.lower(), "").split("|") if o]
    return [phones, *(o for o in others if o != phones)]


def is_function_word(word: str) -> bool:
    return word.lower().replace("’", "'") in FUNCTION_WORDS


def variants(word: str, phones: tuple[str, ...]) -> list[dict]:
    """Cada forma de decir mal la palabra: {"phones", "phone" (correcto), "heard" (lo que suena), "tip"}."""
    out = []
    weak = is_function_word(word)
    for i, phone in enumerate(phones):
        for heard, tip in () if weak and phone in WEAK else SWAPS.get(phone, ()):
            out.append({"phones": (*phones[:i], heard, *phones[i + 1:]), "phone": phone, "heard": heard, "tip": tip})
    if len(phones) > 1 and phones[0] == "s" and phones[1] in {"k", "p", "t", "m", "n", "l", "w"}:
        for vowel in ("ɛ", "e"):  # el modelo oye tu «e-» sobre todo como /e/
            out.append({"phones": (vowel, *phones), "phone": "s-", "heard": "es-", "tip": EPENTHESIS})
    # -ed mudo: walked /wɔːkt/ → *walk-ed. Si ya suena como sílaba (wanted), no hay error que buscar
    if word.lower().endswith("ed") and phones[-1] in SILENT and (len(phones) < 2 or phones[-2] not in {"ᵻ", "ɪ", "ə"}):
        out.append({"phones": (*phones[:-1], "ɪ", "d"), "phone": "-ed", "heard": "-ɪd", "tip": ED_ENDING})
    return out
