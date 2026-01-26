#!/usr/bin/env python3.10
import sys
import requests
from bs4 import BeautifulSoup
import re

def get_bible_passage(passage, version):
    # Standardize format for BibleGateway URL
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version={version}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Target all spans with class starting with 'text'
        verses = soup.find_all("span", class_=re.compile(r"text\s+.*"))

        if not verses:
            return f"Error: Could not find text for version '{version}'."

        passage_pieces = []
        for v in verses:
            # Clean out footnotes, cross-references, verse numbers, and chapter numbers
            for junk in v.find_all(['sup', 'div', 'span'], class_=['footnote', 'crossreference', 'versenum', 'chapternum']):
                junk.decompose()

            text = v.get_text().strip()
            if text:
                passage_pieces.append(text)

        full_text = " ".join(passage_pieces)

        # Cleanup: Remove leading numbers and collapse whitespace
        full_text = re.sub(r'^\d+\s+', '', full_text)
        return re.sub(r'\s+', ' ', full_text).strip()

    except Exception as e:
        return f"An error occurred with version {version}: {e}"

def main():
    if len(sys.argv) < 3:
        print("Usage: ./fetcher.py \"Passage Name\" VERSION1 VERSION2 ...")
        return

    passage = sys.argv[1]
    versions = sys.argv[2:]

    for v in versions:
        upper_v = v.upper()
        print(f"--- {passage} ({upper_v}) ---")
        text = get_bible_passage(passage, upper_v)
        print(text)
        print("-" * 40 + "\n")

if __name__ == "__main__":
    main()
