---
name: Deep Document Extraction
description: Extract structured tables, run OCR on scanned images, and parse complex PDF layouts.
---

# Deep Document Extraction Instructions

When asked to read a PDF, image, or heavily formatted document, simple text reading is insufficient.

## PDF Extraction
Use `pdfplumber` (install via `pip install pdfplumber` if needed) to extract text and tables with layout awareness. Write a Python script to do this.

## Image OCR
For images or scanned documents, use the `tesseract` engine via the `pytesseract` Python library. 
Ensure the image is pre-processed (converted to grayscale via OpenCV) before passing it to the OCR engine to improve accuracy.

Do not attempt to parse binary files by reading them as plain text.
