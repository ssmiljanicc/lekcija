#!/usr/bin/env python3
"""
synthesize.py - Analizira sve generisane lekcije i kreira sintezu:
- Redosled učenja / operacija
- Ključni koncepti i veze između lekcija
- Konkretan vodič za agentic development

Upotreba:
    python3 synthesize.py                        # sve iz output/
    python3 synthesize.py -o output/sinteza.md   # custom output
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import google.generativeai as genai


SYNTHESIS_SYSTEM_PROMPT = """\
Ti si ekspert za agentic software development i AI-asistovano programiranje.

Dobijaćeš skup lekcija iz kursa o razvoju softvera korišćenjem AI agenata \
(Kiro CLI, Claude Code, Ralph Loop, Shards, Archon i sl.).

Tvoj zadatak je da napišeš SINTEZU - jedan dokument koji:

1. **Definiše redosled učenja** - koje lekcije treba savladati pre kojih
2. **Mapira koncepte** - koji koncepti se ponavljaju, koji su fundamentalni, koji napredni
3. **Daje konkretan vodič za agentic development** - korak po korak, šta tačno da radiš \
   kad krećeš novi projekat sa AI agentima
4. **Identifikuje obrasce** - koji se workflow-ovi pojavljuju u više lekcija
5. **Daje preporuke** - šta je najefikasnije, koje alate kombinovati, čega da se čuvaš

## Format sinteze

Piši na srpskom, tehnički termini na engleskom.
Dokument treba da bude PRAKTIČAN i AKCIONI - čitalac treba da može odmah da primeni.
Koristi ### za podsekcije unutar ## sekcija.

## Obavezna struktura

# Sinteza: Agentic Development - Vodič kroz Lekcije

[Kratko (3-5 rečenica) o čemu je ovaj kurs]

---

## Pregled i Redosled Lekcija
[Tabela ili numerisana lista sa svim lekcijama u redosledu koji preporučuješ za učenje, \
sa jednom rečenicom zašto taj redosled]

## Mapa Ključnih Koncepta
[Vizualni opis veza između koncepata - šta je temelj, šta gradi na čemu]

## Fundamentalni Alati i Koncepti
[Pregled alata: Kiro CLI, Claude Code, Ralph Loop, Shards, Archon, Worktrees, PRD, PRP]

## Konkretan Vodič: Pokretanje Novog Projekta sa AI Agentima
[Korak po korak, AKCIONI vodič - šta tačno da radiš od nule]

## Najefikasniji Workflow-ovi iz Kursa
[Konkretni obrasci koji se pojavljuju u više lekcija]

## Čestih Grešaka i Kako ih Izbeći
[Anti-paterni i problemi koji su se pojavili u kursu]

## Sledeći Koraci
[Šta da istražuješ dalje posle ovog kursa]

---

## Ključni zaključci
[5-10 bullet poena - najbitniji uvidi iz celog kursa]
"""

SYNTHESIS_USER_TEMPLATE = """\
Evo {n} lekcija iz kursa o agentic development-u. Analiziraj ih i napiši sintezu.

{lessons_content}"""


def load_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def extract_lesson_summary(md_path: Path) -> str:
    """Extract title, summary paragraph, and section headings from a lesson."""
    text = md_path.read_text(encoding="utf-8")

    # Strip frontmatter
    text = re.sub(r"^---\n.*?\n---\n*", "", text, flags=re.DOTALL)

    lines = text.strip().split("\n")
    title = ""
    summary_lines = []
    headings = []
    in_summary = False
    found_separator = False

    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            in_summary = True
            continue
        if in_summary and not found_separator:
            if line.strip() == "---":
                found_separator = True
                in_summary = False
                continue
            if line.strip():
                summary_lines.append(line.strip())
        if line.startswith("## "):
            headings.append(line[3:].strip())

    summary = " ".join(summary_lines)
    return f"### {title}\n**Sekcije:** {', '.join(headings)}\n**Rezime:** {summary[:500]}{'...' if len(summary) > 500 else ''}"


def synthesize(lessons_dir: Path, output_path: Path, model_name: str, verbose: bool) -> None:
    # Collect and sort lesson files
    md_files = sorted(lessons_dir.glob("*.md"))
    if not md_files:
        print(f"Nema .md fajlova u {lessons_dir}", file=sys.stderr)
        sys.exit(1)

    # Skip files that are themselves syntheses
    md_files = [f for f in md_files if "sinteza" not in f.name and "synthesis" not in f.name]

    print(f"Pronađeno {len(md_files)} lekcija za analizu")

    # Build condensed content (use summaries to stay within context)
    lessons_content = ""
    for i, md in enumerate(md_files, 1):
        summary = extract_lesson_summary(md)
        lessons_content += f"\n---\n**Lekcija {i}: `{md.name}`**\n{summary}\n"
        if verbose:
            print(f"  Učitano: {md.name}")

    user_msg = SYNTHESIS_USER_TEMPLATE.format(n=len(md_files), lessons_content=lessons_content)

    print(f"\nGenerisanje sinteze (model: {model_name})...")
    model = genai.GenerativeModel(
        model_name,
        system_instruction=SYNTHESIS_SYSTEM_PROMPT,
    )
    response = model.generate_content(
        user_msg,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=16384,
        ),
    )

    if verbose and response.usage_metadata:
        meta = response.usage_metadata
        print(f"  Tokens: {meta.prompt_token_count} in / {meta.candidates_token_count} out")

    content = response.text

    # Write output with frontmatter
    frontmatter = f"""---
generated: {date.today().isoformat()}
type: synthesis
lessons_analyzed: {len(md_files)}
---

"""
    output_path.write_text(frontmatter + content, encoding="utf-8")
    print(f"\nSinteza sačuvana: {output_path}")
    print(f"Reči: {len(content.split()):,}")


def main():
    parser = argparse.ArgumentParser(
        description="Generiše sintezu i vodič iz skupa lekcija."
    )
    parser.add_argument(
        "lessons_dir",
        nargs="?",
        default="./output",
        help="Folder sa .md lekcijama (default: ./output)",
    )
    parser.add_argument(
        "-o", "--output",
        default="./output/sinteza-agentic-development.md",
        help="Output .md fajl (default: ./output/sinteza-agentic-development.md)",
    )
    parser.add_argument(
        "-m", "--model",
        default=os.environ.get("LEKCIJA_MODEL", "gemini-2.5-flash"),
        help="Gemini model (default: gemini-2.5-flash)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    load_env()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY nije podešen.", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key)

    synthesize(
        lessons_dir=Path(args.lessons_dir),
        output_path=Path(args.output),
        model_name=args.model,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
