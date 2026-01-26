#!/usr/bin/env python3
from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# --- Your Existing Logic ---
def get_bible_passage(passage, version):
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version={version}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        verses = soup.find_all("span", class_=re.compile(r"text\s+.*"))
        if not verses: return f"Error: Could not find text for '{version}'."

        passage_pieces = []
        for v in verses:
            for junk in v.find_all(['sup', 'div', 'span'], class_=['footnote', 'crossreference', 'versenum', 'chapternum']):
                junk.decompose()
            text = v.get_text().strip()
            if text: passage_pieces.append(text)

        full_text = " ".join(passage_pieces)
        return re.sub(r'\s+', ' ', full_text).strip()
    except Exception as e:
        return f"Error: {e}"

# --- Simple HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bible Passage Fetcher</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }
        input[type="text"] { width: 300px; padding: 8px; }
        button { padding: 8px 16px; cursor: pointer; }
        .result { background: #f4f4f4; padding: 20px; border-radius: 8px; margin-top: 20px; }
        h3 { border-bottom: 2px solid #ddd; padding-bottom: 5px; }
    </style>
</head>
<body>
    <h2>📖 Bible Passage Fetcher</h2>
    <form method="POST">
        <input type="text" name="passage" placeholder="e.g. John 8:12-20" required value="{{ passage }}">
        <input type="text" name="versions" placeholder="e.g. KOERV, NIV, NASB" required value="{{ versions_str }}">
        <button type="submit">Fetch</button>
    </form>

    {% if results %}
        {% for v, text in results.items() %}
            <div class="result">
                <h3>{{ v }}</h3>
                <p>{{ text }}</p>
            </div>
        {% endfor %}
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def home():
    results = {}
    passage = ""
    versions_str = ""
    if request.method == 'POST':
        passage = request.form.get('passage')
        versions_str = request.form.get('versions')
        version_list = [v.strip().upper() for v in versions_str.split(',')]

        for v in version_list:
            results[v] = get_bible_passage(passage, v)

    return render_template_string(HTML_TEMPLATE, results=results, passage=passage, versions_str=versions_str)

if __name__ == '__main__':
    # '0.0.0.0' makes it accessible to other devices on your network
    app.run(host='0.0.0.0', port=5000)
