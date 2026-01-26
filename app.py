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
# --- Updated HTML Template with Spinner ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bible Passage Fetcher</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        input[type="text"] { width: 250px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 10px; }
        button { padding: 10px 20px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; }
        button:hover { background-color: #0056b3; }
        .result { background: #f8f9fa; padding: 20px; border-radius: 8px; margin-top: 20px; border-left: 5px solid #007bff; }
        h3 { margin-top: 0; color: #007bff; border-bottom: 1px solid #eee; padding-bottom: 5px; }

        /* The Spinner CSS */
        #spinner { display: none; margin-top: 20px; }
        .loader {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            display: inline-block;
            vertical-align: middle;
            margin-right: 10px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <h2>📖 Bible Passage Fetcher</h2>
    <form id="fetchForm" method="POST">
        <input type="text" name="passage" placeholder="John 8:12-20" required value="{{ passage }}">
        <input type="text" name="versions" placeholder="KOERV, NIV, NASB" required value="{{ versions_str }}">
        <button type="submit" id="submitBtn">Fetch Passage</button>
    </form>

    <div id="spinner">
        <div class="loader"></div> <span>Searching BibleGateway...</span>
    </div>

    {% if results %}
        <div id="results-container">
            {% for v, text in results.items() %}
                <div class="result">
                    <h3>{{ v }}</h3>
                    <p>{{ text }}</p>
                </div>
            {% endfor %}
        </div>
    {% endif %}

    <script>
        // Show spinner and hide old results when clicking submit
        document.getElementById('fetchForm').onsubmit = function() {
            document.getElementById('spinner').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').innerText = 'Fetching...';
            var results = document.getElementById('results-container');
            if (results) results.style.opacity = '0.3';
        };
    </script>
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
