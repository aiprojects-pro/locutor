"""Normalización de texto en español para TTS (pipeline ordenado, config YAML).

Orden de aplicación:
  1. Abreviaturas (con punto): "Sr." -> "señor".
  2. Palabras/abreviaturas (sin punto): "etc" -> "etcétera".
  3. Moneda: "200€" -> "doscientos euros", "1,50€" -> "un euro con cincuenta céntimos".
  4. Porcentajes: "12,5%" -> "doce coma cinco por ciento".
  5. Números: "1.991,50" -> "mil novecientos noventa y uno coma cincuenta".
  6. Puntuación: paréntesis -> comas, etc.

Convención numérica española: '.' separa miles, ',' separa decimales.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from num2words import num2words

# Un número en formato español: miles con '.' y decimales con ','.
#   1.234.567,89  | 1234  | 5  | 0,5
_NUM = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"


def _es(n: int) -> str:
    return num2words(n, lang="es")


def _apocope_uno(phrase: str) -> str:
    """Apócope de 'uno' ante sustantivo masculino: uno->un, veintiuno->veintiún,
    treinta y uno->treinta y un."""
    if phrase == "uno":
        return "un"
    if phrase.endswith("veintiuno"):
        return phrase[: -len("veintiuno")] + "veintiún"
    if phrase.endswith(" y uno"):
        return phrase[: -len(" y uno")] + " y un"
    return phrase


def _read_decimal(dec: str) -> str:
    """Lee la parte decimal como número entero, con ceros a la izquierda
    leídos uno a uno como 'cero'.  '50'->'cincuenta'  '0050'->'cero cero cincuenta'."""
    leading = len(dec) - len(dec.lstrip("0"))
    rest = dec.lstrip("0")
    parts = ["cero"] * leading
    if rest:
        parts.append(_es(int(rest)))
    elif leading == 0:
        parts.append("cero")
    return " ".join(parts)


def number_to_words(num_str: str) -> str:
    """Convierte un número español (sin signo) a palabras."""
    if "," in num_str:
        int_part, dec_part = num_str.split(",", 1)
    else:
        int_part, dec_part = num_str, ""
    int_val = int(int_part.replace(".", "") or "0")
    words = _es(int_val)
    if dec_part:
        words += " coma " + _read_decimal(dec_part)
    return words


class TextNormalizer:
    def __init__(self, rules: dict):
        self.abbreviations: dict[str, str] = rules.get("abbreviations", {}) or {}
        self.word_replacements: dict[str, str] = rules.get("word_replacements", {}) or {}
        punct = rules.get("punctuation", {}) or {}
        self.parentheses_to_commas = bool(punct.get("parentheses_to_commas", True))
        self.collapse_repeated = bool(punct.get("collapse_repeated", True))
        num = rules.get("numbers", {}) or {}
        self.cur_symbol = num.get("currency_symbol", "€")
        self.cur_sing = num.get("currency_singular", "euro")
        self.cur_plur = num.get("currency_plural", "euros")
        self.cents_sing = num.get("cents_singular", "céntimo")
        self.cents_plur = num.get("cents_plural", "céntimos")

        # Abreviaturas ordenadas de más larga a más corta para evitar solapes.
        self._abbr_items = sorted(
            self.abbreviations.items(), key=lambda kv: len(kv[0]), reverse=True
        )

        sym = re.escape(self.cur_symbol)
        # Moneda: símbolo antes o después, con signo opcional. El signo debe ir
        # pegado al número; (?<!\d) evita tratar el guion de un rango ("5-10")
        # como negativo. No se consume el espacio anterior (se preserva).
        self._cur_re = re.compile(
            rf"(?<!\d)(-?)(?:{sym}\s*(?P<a>{_NUM})|(?P<b>{_NUM})\s*{sym})"
        )
        self._pct_re = re.compile(rf"(?<!\d)(-?)({_NUM})\s*%")
        self._num_re = re.compile(rf"(?<!\d)(-?)({_NUM})")

    # --- pasos del pipeline ---------------------------------------------

    def _apply_abbreviations(self, text: str) -> str:
        for key, value in self._abbr_items:
            # No exigir frontera tras el punto/barra; sí evitar pegado por delante.
            pattern = re.compile(r"(?<![\wÁÉÍÓÚÜÑáéíóúüñ])" + re.escape(key))
            text = pattern.sub(value, text)
        return text

    def _apply_word_replacements(self, text: str) -> str:
        for key, value in self.word_replacements.items():
            pattern = re.compile(rf"\b{re.escape(key)}\b", re.IGNORECASE)
            text = pattern.sub(value, text)
        return text

    def _currency_repl(self, m: re.Match) -> str:
        sign = "menos " if m.group(1) == "-" else ""
        num_str = m.group("a") or m.group("b")
        int_part, _, dec_part = num_str.partition(",")
        units = int(int_part.replace(".", "") or "0")
        if units == 1:
            unit_phrase = f"un {self.cur_sing}"
        else:
            unit_phrase = f"{_apocope_uno(_es(units))} {self.cur_plur}"
        out = unit_phrase
        if dec_part:
            cents = int((dec_part + "00")[:2])  # céntimos = 2 decimales
            if cents == 1:
                out += f" con un {self.cents_sing}"
            elif cents > 0:
                out += f" con {_apocope_uno(_es(cents))} {self.cents_plur}"
        return sign + out

    def _percent_repl(self, m: re.Match) -> str:
        sign = "menos " if m.group(1) == "-" else ""
        return sign + number_to_words(m.group(2)) + " por ciento"

    def _number_repl(self, m: re.Match) -> str:
        sign = "menos " if m.group(1) == "-" else ""
        return sign + number_to_words(m.group(2))

    def _apply_punctuation(self, text: str) -> str:
        if self.parentheses_to_commas:
            text = text.replace("(", ", ").replace(")", ", ")
            text = text.replace("[", ", ").replace("]", ", ")
        if self.collapse_repeated:
            text = re.sub(r"([!?¡¿])\1+", r"\1", text)
            text = re.sub(r",\s*,+", ", ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    # --- API pública ----------------------------------------------------

    def normalize(self, text: str) -> str:
        text = self._apply_abbreviations(text)
        text = self._apply_word_replacements(text)
        text = self._cur_re.sub(self._currency_repl, text)
        text = self._pct_re.sub(self._percent_repl, text)
        text = self._num_re.sub(self._number_repl, text)
        text = self._apply_punctuation(text)
        return text


def load_normalizer(config_path: str | Path) -> TextNormalizer:
    path = Path(config_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            rules = yaml.safe_load(fh) or {}
    else:
        rules = {}
    return TextNormalizer(rules)
