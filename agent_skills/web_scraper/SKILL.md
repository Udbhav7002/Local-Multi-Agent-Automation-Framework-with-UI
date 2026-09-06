---
name: Web Scraper
description: Scrape text content from URLs without launching a slow GUI browser.
---

# Web Scraper Instructions

When the user asks you to read an article, extract information from a URL, or summarize a web page, DO NOT use GUI automation or Safari unless explicitly asked to do so. GUI automation is too slow and unreliable for simple text reading.

Instead, use a Python script via `run_command` to fetch and parse the text directly.

## Standard Workflow

Run the following Python one-liner in the terminal to scrape and print the clean text of a website:

`python3 -c "import urllib.request, re; html=urllib.request.urlopen('[URL]').read().decode('utf-8'); text=re.sub('<[^<]+?>', '', html); print(text[:3000])"`

Replace `[URL]` with the target web address (e.g., `https://en.wikipedia.org/wiki/Artificial_intelligence`).

If the page requires JavaScript or blocks simple requests, ONLY THEN should you fall back to using the GUI `open_app Safari` method.
