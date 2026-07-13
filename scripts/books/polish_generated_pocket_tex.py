#!/usr/bin/env python3
"""Polish generated exact/pocket TeX using source-verified book profiles."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADING_RE = re.compile(r"^\\(chapter|section|subsection|subsubsection)\{")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


BLACK_HOLE_HEADINGS = {
    "introduction": ("chapter", "Introduction"),
    "the-gathering-storm": ("part", "Part I: The Gathering Storm"),
    "the-first-shot": ("chapter", "1. The First Shot"),
    "the-dark-star": ("chapter", "2. The Dark Star"),
    "not-your-grandfathers-geometry": ("chapter", "3. Not Your Grandfather's Geometry"),
    "einstein-dont-tell-god-what-to-do": ("chapter", "4. Einstein, Don't Tell God What to Do"),
    "planck-invents-a-better-yardstick": ("chapter", "5. Planck Invents a Better Yardstick"),
    "in-a-broadway-bar": ("chapter", "6. In a Broadway Bar"),
    "energy-and-entropy": ("chapter", "7. Energy and Entropy"),
    "wheelers-boys-or-how-much-information-can-you-stuff-in-a-black-hole": (
        "chapter",
        "8. Wheeler's Boys, or How Much Information Can You Stuff in a Black Hole?",
    ),
    "black-light": ("chapter", "9. Black Light"),
    "surprise-attack": ("part", "Part II: Surprise Attack"),
    "how-stephen-lost-his-bits-and-didnt-know-where-to-find-them": (
        "chapter",
        "10. How Stephen Lost His Bits and Didn't Know Where to Find Them",
    ),
    "the-dutch-resistance": ("chapter", "11. The Dutch Resistance"),
    "who-cares": ("chapter", "12. Who Cares?"),
    "stalemate": ("chapter", "13. Stalemate"),
    "skirmish-at-aspen": ("chapter", "14. Skirmish at Aspen"),
    "counterattack": ("part", "Part III: Counterattack"),
    "the-battle-of-santa-barbara": ("chapter", "15. The Battle of Santa Barbara"),
    "wait-reverse-the-rewiring": ("chapter", "16. Wait! Reverse the Rewiring"),
    "ahab-in-cambridge": ("chapter", "17. Ahab in Cambridge"),
    "the-world-as-a-hologram": ("chapter", "18. The World as a Hologram"),
    "closing-the-ring": ("part", "Part IV: Closing the Ring"),
    "weapon-of-mass-deduction": ("chapter", "19. Weapon of Mass Deduction"),
    "alices-airplane-or-the-last-visible-propeller": (
        "chapter",
        "20. Alice's Airplane, or The Last Visible Propeller",
    ),
    "counting-black-holes": ("chapter", "21. Counting Black Holes"),
    "south-america-wins-the-war": ("chapter", "22. South America Wins the War"),
    "nuclear-physics-youre-kidding": ("chapter", "23. Nuclear Physics? You're Kidding!"),
    "humility": ("chapter", "24. Humility"),
    "epilogue": ("chapter", "Epilogue"),
    "acknowledgments": ("chapter", "Acknowledgments"),
    "glossary": ("chapter", "Glossary"),
}


BYZANTIUM_TITLES = [
    ("introduction-a-different-history-of-byzantium", "Introduction: A Different History of Byzantium"),
    ("the-city-of-constantine", "1. The City of Constantine"),
    ("constantinople-the-largest-city-in-christendom", "2. Constantinople, the Largest City in Christendom"),
    ("the-east-roman-empire", "3. The East Roman Empire"),
    ("greek-orthodoxy", "4. Greek Orthodoxy"),
    ("the-church-of-hagia-sophia", "5. The Church of Hagia Sophia"),
    ("the-ravenna-mosaics", "6. The Ravenna Mosaics"),
    ("roman-law", "7. Roman Law"),
    ("the-bulwark-against-islam", "8. The Bulwark Against Islam"),
    ("icons-a-new-christian-art-form", "9. Icons, a New Christian Art Form"),
    ("iconoclasm-and-icon-veneration", "10. Iconoclasm and Icon Veneration"),
    ("a-literate-and-articulate-society", "11. A Literate and Articulate Society"),
    ("saints-cyril-and-methodios-apostles-to-the-slavs", "12. Saints Cyril and Methodios, Apostles to the Slavs"),
    ("greek-fire", "13. Greek Fire"),
    ("the-byzantine-economy", "14. The Byzantine Economy"),
    ("eunuchs", "15. Eunuchs"),
    ("the-imperial-court", "16. The Imperial Court"),
    ("imperial-children-born-in-the-purple", "17. Imperial Children, Born in the Purple"),
    ("mount-athos", "18. Mount Athos"),
    ("venice-and-the-fork", "19. Venice and the Fork"),
    ("basil-ii-the-bulgar-slayer", "20. Basil II, The Bulgar-Slayer"),
    ("eleventh-century-crisis", "21. Eleventh-Century Crisis"),
    ("anna-komnene", "22. Anna Komnene"),
    ("a-cosmopolitan-society", "23. A Cosmopolitan Society"),
    ("the-fulcrum-of-the-crusades", "24. The Fulcrum of the Crusades"),
    ("the-towers-of-trebizond-arta-nicaea-and-thessalonike", "25. The Towers of Trebizond, Arta, Nicaea and Thessalonike"),
    ("rebels-and-patrons", "26. Rebels and Patrons"),
    ("better-the-turkish-turban-than-the-papal-tiara", "27. Better the Turkish Turban than the Papal Tiara"),
    ("the-siege-of-1453", "28. The Siege of 1453"),
    ("conclusion-the-greatness-and-legacy-of-byzantium", "Conclusion: The Greatness and Legacy of Byzantium"),
    ("further-reading", "Further Reading"),
    ("list-of-emperors-named-in-the-text", "List of Emperors Named in the Text"),
    ("chronology", "Chronology"),
    ("acknowledgements", "Acknowledgements"),
    ("index", "Index"),
]
BYZANTIUM_HEADINGS = {label: ("chapter", title) for label, title in BYZANTIUM_TITLES}
BYZANTIUM_HEADINGS.update(
    {
        "foundations-of-byzantium": ("part", "Part I: Foundations of Byzantium"),
        "the-transition-from-ancient-to-medieval": ("part", "Part II: The Transition from Ancient to Medieval"),
        "byzantium-becomes-a-medieval-state": ("part", "Part III: Byzantium Becomes a Medieval State"),
        "varieties-of-byzantium": ("part", "Part IV: Varieties of Byzantium"),
    }
)


BLACK_HOLE_REPLACEMENTS = {
    "111e electron": "The electron",
    "Special TI1eory": "Special Theory",
    "physidsts": "physicists",
    "particle p hysics": "particle physics",
    "infonn ation": "information",
    "l simply could find": "I simply could find",
    "Uirus Thorlacius": "Lárus Thorlacius",
    "occasionalJy": "occasionally",
    "String l11eory": "String Theory",
    "l11eory": "Theory",
    "1l1e": "The",
    "thougbt": "thought",
    "hadroos": "hadrons",
    "e lementary": "elementary",
    "l960s": "1960s",
    "a lphabets": "alphabets",
    "tin1es": "times",
    "'·excited smtcs•·": "‘excited states’",
    "tl1ey arc": "they are",
    "1 r \\textbf{l} had": "If I had",
    "pair o{[} positive": "pair of positive",
    "dpubling": "doubling",
    "1'11 walk": "I'll walk",
    "particJes": "particles",
    "(sec chapter 4)": "(see chapter 4)",
    "conclus.ion": "conclusion",
    "very weH": "very well",
    "pollution bas led": "pollution has led",
    "il is unthinkable": "it is unthinkable",
    (
        "I let Wijndicfjc (Win\\textasciitilde; lhcif), Bacchu\\textasciitilde{} liriosus.11 "
        "i\\textasciitilde:t ptextsubscript{Uil}itc can be foU11d nt:ar pub\\textasciitilde{} Fully "
        "equipped to open boltle\\textasciitilde{} and cans or aU kinds, it can be quite a nuisance "
        "if your wine cellar happens to be infecteU by it."
    ): (
        "Het Wijnflesje (Wine thief), Bacchus deliriosus. This parasite can be found near pubs. "
        "Fully equipped to open bottles and cans of all kinds, it can be quite a nuisance if your "
        "wine cellar happens to be infected by it."
    ),
}


def is_noise_heading(book_id: str, label: str, line: str) -> bool:
    if re.search(r"(?:^|-)section-?\d*$", label):
        return True
    if re.search(r"-\d+$", label):
        return True
    if book_id == "byzantium-herrin":
        return bool(
            re.match(
                r"^(?:byzantium|greekorthodoxy|contents|list-ofillustrations|"
                r"published-in-the-united-states|judith-herrin)$",
                label,
            )
        )
    if label in {"part", "part-ii", "part-iii", "part-iv"}:
        return True
    return bool(
        re.search(r"T H E|B L A C K|H 0 L E|COPYRIGHT|Copyright|WINNER OF", line)
        or label.startswith("copyright-")
        or label in {
            "the-black-hole-war",
            "leonard-susskind",
            "also-by-leonard-susskind",
            "size-of-atom-.0000000001-meters",
            "uv",
            "winner-of-the-los-angeles-times-book-prize-for-science-and-technology",
        }
    )


def polish_tex(book_id: str, tex_path: Path) -> dict[str, int]:
    headings = BLACK_HOLE_HEADINGS if book_id == "black-hole-war" else BYZANTIUM_HEADINGS
    replacements = BLACK_HOLE_REPLACEMENTS if book_id == "black-hole-war" else {}
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    text = text.replace(r"\setcounter{tocdepth}{2}", r"\setcounter{tocdepth}{0}")
    stats = {"promoted": 0, "starred": 0, "suppressed": 0, "replacements": 0}
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        heading_match = HEADING_RE.match(line)
        label_match = LABEL_RE.search(line)
        if not heading_match or not label_match:
            output.append(line)
            continue
        label = label_match.group(1)
        # Pandoc commonly wraps headings as ``\hypertarget{id}{%`` on the
        # preceding line and leaves the wrapper's closing brace after
        # ``\label{id}``. Preserve that suffix; standalone headings have only
        # a newline here.
        suffix = line[label_match.end() :]
        if label in headings:
            command, title = headings[label]
            output.append(f"\\{command}{{{title}}}\\label{{{label}}}{suffix}")
            stats["promoted"] += 1
        elif is_noise_heading(book_id, label, line):
            output.append(f"\\label{{{label}}}{suffix}")
            stats["suppressed"] += 1
        else:
            output.append(re.sub(r"^\\(?:chapter|section|subsection|subsubsection)", r"\\section*", line, count=1))
            stats["starred"] += 1
    text = "".join(output)
    # Repair backslashes occasionally dropped by post-generation agents. Left
    # untreated, these tokens are printed as body text and invalidate table
    # width calculations.
    text = re.sub(r"(?m)^hypersetup\{", r"\\hypersetup{", text)
    text = re.sub(r"(?m)^setstretch\{", r"\\setstretch{", text)
    text = text.replace(
        r">{raggedrightarraybackslash}",
        r">{\raggedright\arraybackslash}",
    )
    if book_id == "byzantium-herrin":
        # Marker occasionally emits index tables whose natural-width columns
        # exceed the pocket measure. Keep their source structure intact and
        # reduce only the table font by one step.
        text = text.replace(
            r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
            r"\begingroup\scriptsize\setlength{\tabcolsep}{2pt}\begin{longtable}",
        )
        vatican_url = (
            "http://www.vatican.va/holyfather/benedictxvi/speeches/2006/"
            "september/documents/hfben-xvispe20060912university-regensburgen.html"
        )
        text = re.sub(
            rf"\\href\{{{re.escape(vatican_url)}\}}\{{http://\}}.*?"
            rf"\\href\{{{re.escape(vatican_url)}\}}\{{university-regensburgen\.html\}}",
            rf"\\url{{{vatican_url}}}",
            text,
        )
    for old, new in replacements.items():
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            stats["replacements"] += count
    backup = tex_path.with_suffix(tex_path.suffix + ".before-structural-polish")
    if not backup.exists():
        shutil.copy2(tex_path, backup)
    tex_path.write_text(text, encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("book_id", choices=["byzantium-herrin", "black-hole-war"])
    args = parser.parse_args()
    for edition in ("exact", "pocket-large-font"):
        tex_path = ROOT / "build-pocket" / args.book_id / edition / "tex/book.tex"
        if not tex_path.exists():
            raise FileNotFoundError(tex_path)
        print(f"{edition}: {polish_tex(args.book_id, tex_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
