#!/usr/bin/env python3
"""
A Markdown to PDF converter for macOS that handles:
- Mermaid diagrams (rendered as SVG or PNG)
- Code blocks
- Math (via MathJax)
- Automatic attempt to normalize inline numbered lists (so Pandoc treats them as lists)

Usage:
    ./md2pdf.py input.md [output.pdf] [--png]

Requires:
- Google Chrome (for headless PDF generation)
- Pandoc
- Mermaid CLI (mmdc)
"""

import os
import re
import sys
import subprocess
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Tuple, List, Dict
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default path to Google Chrome (adjust if needed)
DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def generate_output_filename(input_file: str) -> str:
    """Generate an output PDF filename based on the input Markdown file."""
    input_path = Path(input_file)
    base_path = input_path.parent
    base_name = input_path.stem
    pdf_path = base_path / f"{base_name}.pdf"
    counter = 0
    while pdf_path.exists():
        counter += 1
        pdf_path = base_path / f"{base_name}_{counter:03d}.pdf"
    return str(pdf_path)


def normalize_lists(content: str) -> str:
    """
    Attempt to convert inline numbered lists (like "sections: 1. Key Concepts, 2. Agent...")
    into real lists recognized by Pandoc. We do two main things:
    
    1. Insert a blank line after a colon if it's followed by a numbered item
       (e.g., ": 1. Key" becomes ":\n\n1. Key").
    2. Force each numbered item onto its own line if it appears inline
       (e.g., "2. Agent Framework:" -> "\n2. Agent Framework:").

    This is a heuristic approach and may need fine-tuning for your content.
    """
    # 1) If there's a colon followed by a numbered item, insert a blank line.
    content = re.sub(r':\s*(\d+\.\s+)', r':\n\n\1', content)

    # 2) Force every numbered item to start on a new line if it doesn't already.
    #    (Any occurrence of e.g. " 2. Something" becomes "\n2. Something".)
    content = re.sub(r'([^\n])(\d+\.\s+)', r'\1\n\2', content)

    return content


def extract_mermaid_diagrams(markdown_content: str, output_format: str = 'html', image_ext: str = "svg") -> Tuple[str, List[Tuple[str, str]]]:
    """
    Extract Mermaid diagrams from the Markdown content.
    Replace them with placeholders:
      - For HTML output, insert an HTML <div> with an <img> tag referencing an image
        file with the given extension (SVG by default).
    Returns the new content and a list of tuples (diagram_id, diagram_content).
    """
    pattern = r"```mermaid\n(.*?)\n```"
    diagrams = []

    def replace_diagram(match):
        diagram_content = match.group(1)
        diagram_id = f"diagram_{len(diagrams)}"
        diagrams.append((diagram_id, diagram_content))
        if output_format == 'html':
            # Insert an <img> referencing diagram_id.<ext>, e.g. diagram_0.svg
            return (
                f'\n<div style="text-align:center;">\n'
                f'  <img src="{diagram_id}.{image_ext}" alt="{diagram_id}" style="max-width:80%;">\n'
                f'  <p>{diagram_id.replace("_", " ").title()}</p>\n'
                f'</div>\n'
            )
        return match.group(0)

    logger.info("Extracting Mermaid diagrams")
    new_content = re.sub(pattern, replace_diagram, markdown_content, flags=re.DOTALL)
    return new_content, diagrams


def extract_document_info(content: str) -> Dict[str, str]:
    """Extract document metadata from the Markdown content."""
    logger.info("Extracting document information")
    title_pattern = r'^#\s+(.+)$'
    title_match = re.search(title_pattern, content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Document"

    author_pattern = r'\*\*Author\*\*:\s*(.+)$'
    email_pattern = r'\*\*Email\*\*:\s*(.+)$'
    author_match = re.search(author_pattern, content, re.MULTILINE)
    email_match = re.search(email_pattern, content, re.MULTILINE)
    author = author_match.group(1).strip() if author_match else ""
    email = email_match.group(1).strip() if email_match else ""

    abstract_pattern = r'##\s*Abstract\s*\n+([^#]+)'
    abstract_match = re.search(abstract_pattern, content, re.MULTILINE)
    abstract = abstract_match.group(1).strip() if abstract_match else ""

    # Remove metadata lines from content.
    clean_content = content
    if author:
        clean_content = re.sub(author_pattern, '', clean_content, count=1, flags=re.MULTILINE)
    if email:
        clean_content = re.sub(email_pattern, '', clean_content, count=1, flags=re.MULTILINE)

    return {
        'title': title,
        'author': author,
        'email': email,
        'abstract': abstract,
        'clean_content': clean_content
    }


def render_mermaid_diagram(content: str, output_file: str) -> None:
    """
    Render a Mermaid diagram to an image file using the mmdc command.
    The output_file extension determines the image format (SVG or PNG).
    """
    logger.info(f"Rendering diagram to {output_file}")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as temp:
        temp.write(content)
        temp_path = temp.name
    try:
        subprocess.run([
            'mmdc',
            '-i', temp_path,
            '-o', output_file,
            '-b', 'transparent',
            '-w', '800',
            '-H', '600'
        ], check=True, capture_output=True, text=True)
        logger.info(f"Successfully rendered diagram to {output_file}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error rendering diagram: {e.stdout}\n{e.stderr}")
        raise
    finally:
        os.unlink(temp_path)


def process_code_blocks(content: str, output_format: str = 'html') -> str:
    """
    Process fenced code blocks.
    For HTML output, leave them unchanged so that Pandoc can handle them.
    """
    if output_format == 'html':
        logger.info("Leaving code blocks unchanged for HTML/MathJax")
        return content
    return content


def get_chrome_path() -> str:
    """Return the path to the Google Chrome executable."""
    return os.environ.get("CHROME_PATH", DEFAULT_CHROME_PATH)


def convert_to_pdf_mathjax(markdown_file: str, output_pdf: str, image_ext: str = "svg") -> None:
    """
    Convert Markdown to PDF using MathJax.
    This conversion path uses Pandoc to produce HTML (with --mathjax) and then
    uses headless Google Chrome to convert the HTML to PDF.
    The image_ext parameter determines the format for Mermaid diagrams (svg by default).
    """
    logger.info(f"Beginning MathJax conversion of '{markdown_file}' to '{output_pdf}'")
    with open(markdown_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract doc info but keep the main text in clean_content
    doc_info = extract_document_info(content)
    content = doc_info['clean_content']

    # 1) Attempt to fix inline lists so Pandoc recognizes them
    content = normalize_lists(content)

    # 2) Extract Mermaid diagrams and replace them with placeholders
    content, diagrams = extract_mermaid_diagrams(content, output_format='html', image_ext=image_ext)

    # 3) Code blocks: leave them alone for Pandoc
    content = process_code_blocks(content, output_format='html')

    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"Using temporary directory: {temp_dir}")

        # Write out the processed Markdown
        temp_md = os.path.join(temp_dir, "processed.md")
        with open(temp_md, 'w', encoding='utf-8') as f:
            f.write(content)

        # Render each Mermaid diagram to an image file (SVG or PNG)
        for diagram_id, diagram_content in diagrams:
            output_img = os.path.join(temp_dir, f"{diagram_id}.{image_ext}")
            try:
                render_mermaid_diagram(diagram_content, output_img)
            except Exception as e:
                logger.error(f"Failed to render diagram {diagram_id}: {str(e)}")

        # Convert the processed Markdown to HTML (with MathJax) via Pandoc
        temp_html = os.path.join(temp_dir, "output.html")
        pandoc_args = [
            'pandoc',
            temp_md,
            '--to', 'html5',
            '--mathjax',
            '-o', temp_html,
            '--standalone'
        ]
        logger.info("Running Pandoc conversion to HTML (MathJax path)")
        try:
            subprocess.run(
                pandoc_args,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"HTML conversion failed: {e.stdout}\n{e.stderr}")
            raise RuntimeError(f"HTML conversion failed with exit code {e.returncode}") from e

        # Finally, run headless Chrome to convert HTML -> PDF
        chrome_path = get_chrome_path()
        chrome_args = [
            chrome_path,
            '--headless',
            '--disable-gpu',
            f'--print-to-pdf={output_pdf}',
            temp_html
        ]
        logger.info("Running headless Chrome to convert HTML to PDF")
        try:
            subprocess.run(
                chrome_args,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Successfully created PDF: {output_pdf}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Chrome PDF conversion failed: {e.stdout}\n{e.stderr}")
            logger.error("Failed command: " + " ".join(chrome_args))
            raise RuntimeError(f"Chrome PDF conversion failed with exit code {e.returncode}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to PDF using MathJax. "
                    "By default, Mermaid diagrams are rendered as SVG. "
                    "Use --png to render them as PNG."
    )
    parser.add_argument("input_file", help="Input Markdown file")
    parser.add_argument("output_file", nargs="?", help="Output PDF file (optional)")
    parser.add_argument("--png", action="store_true", help="Render Mermaid diagrams as PNG instead of SVG")
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file if args.output_file else generate_output_filename(input_file)
    image_ext = "png" if args.png else "svg"

    try:
        convert_to_pdf_mathjax(input_file, output_file, image_ext=image_ext)
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
