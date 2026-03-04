#!/usr/bin/env python3
"""
lekcija.py  –  Generisanje strukturiranih lekcija iz video-transkripata ili beleški.

═══════════════════════════════════════════════════════════════
 GĐDE SE POKREĆE
   Uvek iz korena projekta (folder gde se nalazi ovaj fajl):

       cd /Users/ssmiljanic/projekti/lekcija
       python3 lekcija.py <ulazni_fajl_ili_folder>

 ULAZNI FAJLOVI (.md ili .txt)
   Smesti fajlove koje hoćeš da obradiš u:

       input/shards/     ← transkriti razbijeni po delovima (najčešće)
       input/            ← ili direktno u input/

   Primer pokretanja na jednom fajlu:
       python3 lekcija.py "input/shards/deo 2-code review agent swarm.md"

   Primer pokretanja na celom folderu:
       python3 lekcija.py input/shards/

 IZLAZ
   Generisane lekcije se upisuju u:

       output/           ← .md fajlovi sa generisanim lekcijama

   Zatim pokreni export.py da dobiješ .docx:
       python3 export.py

 KONFIGURACIJA
   API ključ i model se čitaju iz .env fajla (GEMINI_API_KEY, LEKCIJA_MODEL).
═══════════════════════════════════════════════════════════════
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import google.generativeai as genai

from prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_USER_TEMPLATE,
    GENERATION_SYSTEM_PROMPT,
    GENERATION_USER_TEMPLATE,
    MERGE_SYSTEM_PROMPT,
    MERGE_USER_TEMPLATE,
)

DEFAULT_MODEL = "gemini-2.0-flash"
CHUNK_MAX_CHARS = 350_000


# --- Configuration ---


def load_env(path: str = ".env") -> None:
    """Load key=value pairs from .env file into environment."""
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


# --- Input Processing ---


def preprocess_text(text: str) -> str:
    """Clean up Obsidian-specific syntax and image references."""
    # Remove Obsidian and standard markdown image embeds
    text = re.sub(r"!\[\[.*?\]\]", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Convert Obsidian wiki-links [[Page]] or [[Page|alias]] to readable text
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # Clean up multiple blank lines left by removed images
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def detect_input_type(text: str) -> str:
    """Detect whether input is a transcript or personal notes."""
    lines = text.strip().split("\n")
    avg_line_len = sum(len(line) for line in lines) / max(len(lines), 1)

    has_headers = sum(1 for line in lines if line.startswith("#")) > 1
    has_bullets = sum(1 for line in lines if line.strip().startswith("- ")) > 3
    has_serbian = bool(re.search(r"[čćšžđČĆŠŽĐ]", text))
    has_image_refs = bool(re.search(r"!\[.*?\]|!\[\[.*?\]\]", text))
    has_timestamps = bool(re.search(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?", text))

    notes_score = sum([
        has_headers,
        has_bullets,
        has_image_refs,
        has_serbian and avg_line_len < 100,
    ])
    transcript_score = sum([
        has_timestamps,
        avg_line_len > 150,
        not has_headers,
    ])

    return "notes" if notes_score > transcript_score else "transcript"


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split text into chunks at paragraph boundaries with overlap."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [current_chunk[-1], para]
            current_len = len(current_chunk[0]) + len(para)
        else:
            current_chunk.append(para)
            current_len += len(para)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def read_input(filepath: str) -> str:
    """Read and preprocess input file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    if len(text.strip()) < 50:
        print("Warning: Input file is very short, output quality may be poor.", file=sys.stderr)

    return preprocess_text(text)


# --- API Calls ---


def call_llm(
    model_name: str,
    system: str,
    user: str,
    max_output_tokens: int = 8192,
    verbose: bool = False,
) -> str:
    """Call Gemini API and return text response."""
    model = genai.GenerativeModel(model_name, system_instruction=system)
    response = model.generate_content(
        user,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=max_output_tokens,
        ),
    )

    if verbose and response.usage_metadata:
        meta = response.usage_metadata
        print(f"  Tokens: {meta.prompt_token_count} in / {meta.candidates_token_count} out")

    return response.text


def parse_json_response(text: str) -> dict:
    """Extract and parse JSON from Claude's response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return json.loads(text)


def analyze(
    content: str,
    input_type: str,
    model: str,
    verbose: bool = False,
) -> dict:
    """Run Stage 1: Analyze content and produce lesson outline."""
    user_msg = ANALYSIS_USER_TEMPLATE.format(input_type=input_type, content=content)

    if verbose:
        print("Analyzing content...")

    raw = call_llm(model, ANALYSIS_SYSTEM_PROMPT, user_msg, max_output_tokens=8192, verbose=verbose)

    try:
        return parse_json_response(raw)
    except json.JSONDecodeError:
        if verbose:
            print("  JSON parse failed, retrying...")
        fix_msg = f"The following was supposed to be valid JSON but has errors. Fix it and return ONLY valid JSON:\n\n{raw}"
        raw2 = call_llm(model, "Fix the JSON. Return ONLY valid JSON.", fix_msg, max_output_tokens=8192, verbose=verbose)
        try:
            return parse_json_response(raw2)
        except json.JSONDecodeError:
            print(f"Error: Could not parse analysis response as JSON.\nRaw response:\n{raw}", file=sys.stderr)
            sys.exit(1)


def merge_analyses(
    analyses: list[dict],
    model: str,
    verbose: bool = False,
) -> dict:
    """Merge multiple chunk analyses into one unified outline."""
    analyses_text = "\n\n---\n\n".join(
        f"Chunk {i+1}:\n{json.dumps(a, indent=2, ensure_ascii=False)}"
        for i, a in enumerate(analyses)
    )
    user_msg = MERGE_USER_TEMPLATE.format(n=len(analyses), analyses=analyses_text)

    if verbose:
        print(f"Merging {len(analyses)} chunk analyses...")

    raw = call_llm(model, MERGE_SYSTEM_PROMPT, user_msg, max_output_tokens=8192, verbose=verbose)

    try:
        return parse_json_response(raw)
    except json.JSONDecodeError:
        print(f"Error: Could not parse merge response as JSON.\nRaw response:\n{raw}", file=sys.stderr)
        sys.exit(1)


def generate_lesson(
    lesson_outline: dict,
    content: str,
    model: str,
    verbose: bool = False,
) -> str:
    """Run Stage 2: Generate a full lesson from outline and source material."""
    outline_json = json.dumps(lesson_outline, indent=2, ensure_ascii=False)
    user_msg = GENERATION_USER_TEMPLATE.format(outline_json=outline_json, content=content)

    return call_llm(model, GENERATION_SYSTEM_PROMPT, user_msg, max_output_tokens=65536, verbose=verbose)


# --- Output ---


def write_lesson(output_dir: str, filename: str, content: str, source_file: str, topic: str) -> Path:
    """Write lesson markdown file with YAML frontmatter."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filepath = out_path / filename
    # Avoid overwriting existing files
    if filepath.exists():
        stem = filepath.stem
        suffix = filepath.suffix
        counter = 2
        while filepath.exists():
            filepath = out_path / f"{stem}-{counter}{suffix}"
            counter += 1

    frontmatter = f"""---
source: {Path(source_file).name}
generated: {date.today().isoformat()}
topic: {topic}
---

"""
    filepath.write_text(frontmatter + content, encoding="utf-8")
    return filepath


# --- Main Pipeline ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate structured lessons from video transcripts or notes."
    )
    parser.add_argument("input_path", help="Path to file (.md, .txt) or folder with .md files")
    parser.add_argument(
        "-t", "--type",
        choices=["transcript", "notes"],
        help="Override auto-detection of input type",
    )
    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "-m", "--model",
        help=f"Gemini model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Run only analysis stage, print outline and stop",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print intermediate steps and token usage",
    )

    args = parser.parse_args()

    # ── Konfiguracija ────────────────────────────────────────────
    # Učitaj .env iz korena projekta (GEMINI_API_KEY, LEKCIJA_MODEL)
    load_env()
    model = args.model or os.environ.get("LEKCIJA_MODEL", DEFAULT_MODEL)
    # Izlazni folder: default je ./output (ili LEKCIJA_OUTPUT_DIR iz .env)
    output_dir = args.output or os.environ.get("LEKCIJA_OUTPUT_DIR", "./output")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "Error: GEMINI_API_KEY not set.\n"
            "Set it in .env file or as environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Configure Gemini
    genai.configure(api_key=api_key)

    # ── Prikupljanje ulaznih fajlova ─────────────────────────────
    # Prosleđuješ putanju do fajla ILI do foldera (npr. input/shards/)
    input_path = Path(args.input_path)
    if input_path.is_dir():
        input_files = sorted(input_path.glob("*.md"))
        if not input_files:
            input_files = sorted(input_path.glob("*.txt"))
        if not input_files:
            print(f"Error: No .md or .txt files found in {input_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Pronađeno {len(input_files)} fajlova u {input_path}")
    elif input_path.is_file():
        input_files = [input_path]
    else:
        print(f"Error: Putanja ne postoji: {input_path}", file=sys.stderr)
        sys.exit(1)

    all_written = []
    for file_idx, input_file in enumerate(input_files):
        if len(input_files) > 1:
            print(f"\n{'='*60}")
            print(f"File {file_idx+1}/{len(input_files)}: {input_file.name}")
            print(f"{'='*60}")

        # Read input
        content = read_input(str(input_file))
        word_count = len(content.split())
        input_type = args.type or detect_input_type(content)

        print(f"Reading {input_file}... ({word_count:,} words)")
        print(f"Detected input type: {input_type}")

        # Stage 1: Analysis
        chunks = chunk_text(content)

        if len(chunks) == 1:
            outline = analyze(content, input_type, model, args.verbose)
        else:
            print(f"Input split into {len(chunks)} chunks")
            analyses = []
            for i, chunk in enumerate(chunks):
                if args.verbose:
                    print(f"  Analyzing chunk {i+1}/{len(chunks)}...")
                analysis = analyze(chunk, input_type, model, args.verbose)
                analyses.append(analysis)
            outline = merge_analyses(analyses, model, args.verbose)

        # Print outline summary
        lessons = outline.get("lessons", [])
        print(f"\n{len(lessons)} lesson(s) planned:")
        for i, lesson in enumerate(lessons, 1):
            sections = lesson.get("sections", [])
            print(f"  {i}. {lesson['filename']} ({len(sections)} sections)")
            if args.verbose:
                for section in sections:
                    print(f"     - {section['heading']}")

        if args.analyze_only:
            print(f"\nFull outline:\n{json.dumps(outline, indent=2, ensure_ascii=False)}")
            continue

        # Stage 2: Generation
        for i, lesson in enumerate(lessons, 1):
            print(f"\nGenerating lesson {i}/{len(lessons)}: {lesson['title']}...")
            markdown = generate_lesson(lesson, content, model, args.verbose)

            filepath = write_lesson(
                output_dir,
                lesson["filename"],
                markdown,
                str(input_file),
                lesson.get("title", outline.get("main_topic", "")),
            )
            all_written.append(filepath)

        # Small delay between files to respect free tier rate limits
        if len(input_files) > 1 and file_idx < len(input_files) - 1:
            import time
            time.sleep(5)

    # ── Rezime rezultata ─────────────────────────────────────────
    if all_written:
        print(f"\n✓ Gotovo. Lekcije su upisane u:")
        for f in all_written:
            print(f"  {f}")
        print(f"\nSledeći korak: python3 export.py   →  konvertuj u .docx (u docs/folder)")


if __name__ == "__main__":
    main()
