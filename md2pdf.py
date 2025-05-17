#!/usr/bin/env python3
"""
A Markdown to PDF converter for macOS that handles:
- Mermaid diagrams (rendered as SVG or PNG)
- Code blocks
- Math (via MathJax)
- Automatic attempt to normalize inline numbered lists (so Pandoc treats them as lists)
- Optional larger font size for Arabic text with --arabic <fontsize>
- Visible table grid lines in the PDF output
- Optional diagram size control with --diagram-width and --diagram-height

Usage:
    ./md2pdf.py input.md [output.pdf] [--png] [--arabic <fontsize>] [--diagram-width <pixels>] [--diagram-height <pixels>]

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

# Default diagram dimensions (reduced from original 800x600)
DEFAULT_DIAGRAM_WIDTH = 400
DEFAULT_DIAGRAM_HEIGHT = 300

# CSS to add table grid lines and basic styling
TABLE_CSS = """
<style>
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
    }
    th, td {
        border: 1px solid black;
        padding: 8px;
        text-align: left;
        vertical-align: top;
    }
    th {
        background-color: #f2f2f2;
    }
</style>
"""


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
    Convert inline numbered lists after a colon into proper lists, skipping headings.
    """
    lines = content.split('\n')
    processed_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            # Leave heading lines unchanged
            processed_lines.append(line)
        else:
            # Apply list normalization only to non-heading lines
            line = re.sub(r':\s*(\d+\.\s+)', r':\n\n\1', line)
            processed_lines.append(line)
    return '\n'.join(processed_lines)


def process_arabic_text(content: str, arabic_font_size: int = None) -> str:
    """
    Detect Arabic text and wrap it in a <span> with a custom font size if specified.
    Arabic Unicode range: \u0600-\u06FF
    """
    if not arabic_font_size:
        return content

    logger.info(f"Processing Arabic text with font size {arabic_font_size}px")

    arabic_pattern = r'[\u0600-\u06FF]+(?:\s*[\u0600-\u06FF]+)*'

    def wrap_arabic(match):
        arabic_text = match.group(0)
        return f'<span style="font-size:{arabic_font_size}px; font-family:Arial, sans-serif; direction:rtl;">{arabic_text}</span>'

    lines = content.split('\n')
    in_code_block = False
    processed_lines = []

    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            processed_lines.append(line)
            continue
        if not in_code_block:
            line = re.sub(arabic_pattern, wrap_arabic, line)
        processed_lines.append(line)

    return '\n'.join(processed_lines)


def extract_mermaid_diagrams(markdown_content: str, output_format: str = 'html', image_ext: str = "svg") -> Tuple[str, List[Tuple[str, str]]]:
    """
    Extract Mermaid diagrams from the Markdown content.
    Replace them with placeholders for HTML output.
    """
    pattern = r"```mermaid\n(.*?)\n```"
    diagrams = []

    def replace_diagram(match):
        diagram_content = match.group(1)
        diagram_id = f"diagram_{len(diagrams)}"
        diagrams.append((diagram_id, diagram_content))
        if output_format == 'html':
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


def render_mermaid_diagram(content: str, output_file: str, width: int = DEFAULT_DIAGRAM_WIDTH, height: int = DEFAULT_DIAGRAM_HEIGHT) -> None:
    """
    Render a Mermaid diagram to an image file using the mmdc command.
    """
    logger.info(f"Rendering diagram to {output_file} (size: {width}x{height})")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as temp:
        temp.write(content)
        temp_path = temp.name
    try:
        subprocess.run([
            'mmdc',
            '-i', temp_path,
            '-o', output_file,
            '-b', 'transparent',
            '-w', str(width),
            '-H', str(height)
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


def convert_to_pdf_mathjax(markdown_file: str, output_pdf: str, image_ext: str = "svg", 
                          arabic_font_size: int = None, diagram_width: int = DEFAULT_DIAGRAM_WIDTH, 
                          diagram_height: int = DEFAULT_DIAGRAM_HEIGHT) -> None:
    """
    Convert Markdown to PDF using MathJax.
    Optionally apply a larger font size to Arabic text and add table grid lines.
    """
    logger.info(f"Beginning MathJax conversion of '{markdown_file}' to '{output_pdf}'")
    logger.info(f"Using diagram size: {diagram_width}x{diagram_height}")
    
    with open(markdown_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract doc info but keep the main text in clean_content
    doc_info = extract_document_info(content)
    content = doc_info['clean_content']

    # 1) Attempt to fix inline lists so Pandoc recognizes them
    content = normalize_lists(content)

    # 2) Process Arabic text if a font size is specified
    content = process_arabic_text(content, arabic_font_size)

    # 3) Extract Mermaid diagrams and replace them with placeholders
    content, diagrams = extract_mermaid_diagrams(content, output_format='html', image_ext=image_ext)

    # 4) Code blocks: leave them alone for Pandoc
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
                render_mermaid_diagram(diagram_content, output_img, diagram_width, diagram_height)
            except Exception as e:
                logger.error(f"Failed to render diagram {diagram_id}: {str(e)}")

        # Convert the processed Markdown to HTML (with MathJax) via Pandoc
        temp_html_raw = os.path.join(temp_dir, "output_raw.html")
        pandoc_args = [
            'pandoc',
            temp_md,
            '--to', 'html5',
            '--mathjax',
            '-o', temp_html_raw,
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

        # Read the raw HTML and inject the table CSS
        with open(temp_html_raw, 'r', encoding='utf-8') as f:
            html_content = f.read()
        temp_html = os.path.join(temp_dir, "output.html")
        with open(temp_html, 'w', encoding='utf-8') as f:
            # Inject the CSS just before the </head> tag
            html_content = html_content.replace('</head>', TABLE_CSS + '</head>')
            f.write(html_content)

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
                    "Use --png to render them as PNG. "
                    "Use --arabic <fontsize> to set a larger font size for Arabic text. "
                    "Tables will have visible grid lines in the PDF."
    )
    parser.add_argument("input_file", help="Input Markdown file")
    parser.add_argument("output_file", nargs="?", help="Output PDF file (optional)")
    parser.add_argument("--png", action="store_true", help="Render Mermaid diagrams as PNG instead of SVG")
    parser.add_argument("--arabic", type=int, help="Set font size (in pixels) for Arabic text")
    parser.add_argument("--diagram-width", type=int, default=DEFAULT_DIAGRAM_WIDTH, 
                       help=f"Width of rendered Mermaid diagrams in pixels (default: {DEFAULT_DIAGRAM_WIDTH})")
    parser.add_argument("--diagram-height", type=int, default=DEFAULT_DIAGRAM_HEIGHT, 
                       help=f"Height of rendered Mermaid diagrams in pixels (default: {DEFAULT_DIAGRAM_HEIGHT})")
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file if args.output_file else generate_output_filename(input_file)
    image_ext = "png" if args.png else "svg"
    arabic_font_size = args.arabic
    diagram_width = args.diagram_width
    diagram_height = args.diagram_height

    if arabic_font_size and arabic_font_size <= 0:
        logger.error("Arabic font size must be a positive integer")
        sys.exit(1)
        
    if diagram_width <= 0 or diagram_height <= 0:
        logger.error("Diagram width and height must be positive integers")
        sys.exit(1)

    try:
        convert_to_pdf_mathjax(
            input_file, 
            output_file, 
            image_ext=image_ext, 
            arabic_font_size=arabic_font_size,
            diagram_width=diagram_width,
            diagram_height=diagram_height
        )
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()