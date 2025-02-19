Below is a sample `README.md` for your tool:

---

```markdown
# md2pdf

`md2pdf` is a Markdown to PDF converter for macOS that handles Mermaid diagrams, code blocks, and math expressions using MathJax. It converts your Markdown file into an HTML file (with MathJax enabled) via Pandoc and then uses headless Google Chrome to "print" the HTML to a PDF. By default, Mermaid diagrams are rendered as SVG (vector graphics) for crisp quality when zooming; you can also opt to render them as PNG images with a command-line flag.

## Features

- **Markdown to PDF Conversion:** Converts Markdown files into high-quality PDFs.
- **MathJax Support:** Renders math expressions correctly when delimited with `$...$` or `$$...$$`.
- **Mermaid Diagrams:** Extracts Mermaid code blocks and renders them as images:
  - **Default:** Renders as SVG (vector) for infinite zoom quality.
  - **Optional:** Use the `--png` flag to render as PNG.
- **Code Blocks:** Leaves fenced code blocks unchanged so that Pandoc can process them.
- **Customizable:** Uses Pandoc with MathJax for HTML conversion and headless Chrome for PDF generation.

## Requirements

- **macOS**
- [Pandoc](https://pandoc.org/) installed and available in your `PATH`.
- [Google Chrome](https://www.google.com/chrome/) (or Chromium) installed.
- [Mermaid CLI (mmdc)](https://github.com/mermaid-js/mermaid-cli) installed and available in your `PATH`.
- Python 3.x

## Installation

1. **Clone or Download** the repository containing `md2pdf.py`.

2. **Make the script executable:**

   ```bash
   chmod +x md2pdf.py
   ```

3. **Ensure all dependencies are installed** (Pandoc, Google Chrome, mmdc).

## Usage

Run the script from the command line:

```bash
./md2pdf.py input.md [output.pdf] [--png]
```

- `input.md` - The input Markdown file.
- `output.pdf` - (Optional) The name/path of the output PDF file. If not provided, the output PDF will be named after the input file.
- `--png` - (Optional) Render Mermaid diagrams as PNG instead of the default SVG.

### Examples

- **Default SVG rendering (recommended for zooming):**

  ```bash
  ./md2pdf.py example.md
  ```

- **PNG rendering for Mermaid diagrams:**

  ```bash
  ./md2pdf.py example.md output.pdf --png
  ```

## How It Works

1. **Markdown Processing:**  
   The script reads your Markdown file and extracts document metadata (such as title, author, and abstract). It then searches for Mermaid diagrams and replaces them with HTML placeholders.

2. **Mermaid Rendering:**  
   Mermaid code blocks are rendered using `mmdc`. By default, images are rendered as SVG files. If the `--png` flag is provided, they are rendered as PNG images.

3. **HTML Conversion with MathJax:**  
   The processed Markdown is converted to an HTML file using Pandoc with the `--mathjax` option. This ensures that math expressions enclosed in `$...$` or `$$...$$` are rendered correctly.

4. **PDF Generation:**  
   Headless Google Chrome is used to print the HTML file to PDF. This results in a high-quality PDF that retains the sharpness of vector graphics (SVG) and renders math and code blocks correctly.

## Troubleshooting

- **Google Chrome not found:**  
  If Chrome is not installed in the default location, set the `CHROME_PATH` environment variable:

  ```bash
  export CHROME_PATH="/path/to/your/chrome"
  ```

- **Pandoc or mmdc errors:**  
  Ensure that Pandoc and mmdc are installed and available in your `PATH`.

## License

This project is released under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Thanks to the developers of Pandoc, MathJax, and Mermaid for their great tools that make this conversion possible.
```
