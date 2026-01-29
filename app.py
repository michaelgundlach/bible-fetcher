#!/usr/bin/env python3
from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def get_bible_passage(passage, version, include_verses=True):
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version={version}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        container = soup.find("div", class_="passage-content") or soup.find("div", class_="passage-text")

        if not container:
            return f"Error: Could not find text for version '{version}'."

        passage_pieces = []
        tags_to_find = re.compile(r'^h[34]$|^span$')

        for element in container.find_all(tags_to_find):

            # --- CASE A: It's a Header ---
            if element.name in ['h3', 'h4']:
                heading_text = element.get_text().strip()

                # FIX 1: Ignore "Cross references" and "Footnotes" sections
                if heading_text.lower() in ['cross references', 'footnotes', 'bibliography']:
                    continue

                if heading_text:
                    # FIX 2: Reduced newlines to just one before the header to tighten spacing
                    passage_pieces.append(f"\n\n<strong>{heading_text}</strong>\n")
                continue

            # --- CASE B: It's a Verse Span ---
            if element.find_parent(['h3', 'h4']):
                continue

            class_list = element.get('class', [])
            is_verse_text = any('text' in c for c in class_list)

            if is_verse_text:
                # Clean junk
                for junk in element.find_all(['sup', 'div'], class_=['footnote', 'crossreference', 'bibleref', 'footnotes']):
                    junk.decompose()

                if not include_verses:
                    for num in element.find_all(['span', 'strong', 'b'], class_=['versenum', 'chapternum', 'v-num']):
                        num.decompose()

                text = element.get_text().strip()

                if not include_verses:
                    text = re.sub(r'^\d+\s*', '', text)

                if text:
                    passage_pieces.append(text)

        full_text = " ".join(passage_pieces)

        # Cleanup: Ensure clean newlines without trailing spaces
        full_text = re.sub(r' \n', '\n', full_text)
        full_text = re.sub(r'\n ', '\n', full_text)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text) # Max 2 newlines (paragraph break)
        full_text = re.sub(r'[ ]{2,}', ' ', full_text)   # No double spaces

        return full_text.strip()

    except Exception as e:
        return f"An error occurred with version {version}: {e}"

# --- HTML Template ---
# FIX 3: Removed indentation inside the 'copy-target' div to prevent whitespace issues
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bible Passage Fetcher</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        .controls { display: flex; flex-wrap: wrap; gap: 15px; align-items: center; margin-bottom: 25px; background: #eee; padding: 15px; border-radius: 8px; }
        input[type="text"] { padding: 10px; border: 1px solid #ccc; border-radius: 4px; flex: 1; min-width: 180px; }
        button { padding: 10px 25px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; }
        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #ccc; cursor: not-allowed; }

        .result { background: #f8f9fa; padding: 25px; border-radius: 8px; margin-top: 20px; border-left: 5px solid #007bff; position: relative; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }

        /* Styles for the copied content */
        h3.version-title { margin-top: 0; margin-bottom: 10px; color: #007bff; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        .passage-content { white-space: pre-wrap; word-wrap: break-word; font-family: sans-serif; }

        .copy-btn { position: absolute; top: 15px; right: 15px; background: #6c757d; color: white; border: none; font-size: 12px; padding: 6px 12px; border-radius: 4px; cursor: pointer; }
        .copy-btn:hover { background: #5a6268; }

        #spinner { display: none; margin: 15px 0; font-weight: bold; color: #007bff; }
        .loader { border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 10px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        label { cursor: pointer; display: flex; align-items: center; gap: 5px; font-weight: 500; }
    </style>
</head>
<body>
    <h2>📖 Bible Passage Fetcher</h2>
    <form id="fetchForm" method="POST">
        <div class="controls">
            <input type="text" name="passage" placeholder="e.g. John 8:12-20" required value="{{ passage }}">
            <input type="text" name="versions" placeholder="e.g. KOERV NIV" required value="{{ versions_str }}">
            <label>
                <input type="checkbox" name="include_verses" {% if include_verses %}checked{% endif %}> Verse Numbers
            </label>
            <button type="submit" id="submitBtn">Fetch</button>
        </div>
    </form>

    <div id="spinner"><div class="loader"></div> Processing...</div>

    {% if results %}
        <div id="results-container">
            {% for v, text in results.items() %}
                <div class="result">
                    <div id="copy-target-{{ loop.index }}"><h3 class="version-title">{{ v }} - {{ passage }}</h3><div class="passage-content">{{ text | safe }}</div></div>

                    <button class="copy-btn" onclick="copyRichText('copy-target-{{ loop.index }}', this)">Copy</button>
                </div>
            {% endfor %}
        </div>
    {% endif %}

    <script>
        document.getElementById('fetchForm').onsubmit = function() {
            document.getElementById('spinner').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').innerText = 'Fetching...';
            var container = document.getElementById('results-container');
            if (container) container.style.opacity = '0.3';
        };

        async function copyRichText(elementId, btn) {
            const element = document.getElementById(elementId);

            // We strip leading/trailing whitespace from the inner text to avoid top-gap
            const cleanHTML = '<div style="white-space: pre-wrap; font-family: sans-serif;">' + element.innerHTML.trim() + '</div>';
            const cleanText = element.innerText.trim();

            const blobHtml = new Blob([cleanHTML], { type: 'text/html' });
            const blobText = new Blob([cleanText], { type: 'text/plain' });

            try {
                await navigator.clipboard.write([
                    new ClipboardItem({
                        'text/html': blobHtml,
                        'text/plain': blobText
                    })
                ]);

                var originalText = btn.innerText;
                btn.innerText = "Copied!";
                btn.style.backgroundColor = "#28a745";
                setTimeout(function() {
                    btn.innerText = originalText;
                    btn.style.backgroundColor = "#6c757d";
                }, 2000);
            } catch (err) {
                console.error('Failed to copy: ', err);
                btn.innerText = "Error";
                btn.style.backgroundColor = "#dc3545";
            }
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def home():
    results = {}
    passage = ""
    versions_str = ""
    include_verses = True

    if request.method == 'POST':
        passage = request.form.get('passage')
        versions_str = request.form.get('versions')
        include_verses = True if request.form.get('include_verses') else False

        version_list = [v.upper() for v in re.split(r'[,\s]+', versions_str) if v]

        for v in version_list:
            results[v] = get_bible_passage(passage, v, include_verses)

    return render_template_string(HTML_TEMPLATE, results=results, passage=passage, versions_str=versions_str, include_verses=include_verses)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
