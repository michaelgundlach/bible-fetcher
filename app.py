#!/usr/bin/env python3
from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup, NavigableString
import re

app = Flask(__name__)

# --- REGEX PATTERNS ---
# Matches closed quotes: “...” or "..." or 「...」
# Also matches "Open-ended" quotes at the end of a string (for verse breaks)
QUOTE_PATTERN = re.compile(r'([“"「][^”"」]*(?:[”"」]|$))')

def analyze_ceb_for_red_letters(passage):
    """
    Fetches CEB to map the 'Red Letter Structure' of each verse.
    Returns a dict: { verse_num: {'type': 'FULL' | 'MASK', 'mask': [bool, bool...]} }
    """
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version=CEB"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    red_map = {}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return red_map

        soup = BeautifulSoup(response.text, 'html.parser')
        container = soup.find("div", class_="passage-content") or soup.find("div", class_="passage-text")
        if not container: return red_map

        # Iterate through verse wrappers
        for verse_span in container.find_all('span', class_='text'):

            # 1. Identify Verse Number
            v_num_tag = verse_span.find(class_=['versenum', 'chapternum', 'v-num'])
            if not v_num_tag: continue
            verse_num = v_num_tag.get_text().strip()

            # 2. Clean up for analysis
            temp_span = BeautifulSoup(str(verse_span), 'html.parser')
            for junk in temp_span.find_all(class_=['footnote', 'crossreference']):
                junk.decompose()

            full_text_content = temp_span.get_text().replace(verse_num, "").strip()
            if not full_text_content: continue

            # 3. Check for "FULL" Red (Ratio Strategy)
            # This handles verses like John 14:1 where Jesus speaks the whole time without quotes.
            woj_text = "".join([w.get_text() for w in temp_span.find_all(class_='woj')])
            if len(woj_text) / len(full_text_content) > 0.9:
                red_map[verse_num] = {'type': 'FULL'}
                continue

            # 4. Check for "MASK" Red (Quote Sequence Strategy)
            # We find all quotes in the CEB text and check if they overlap with 'woj' tags.
            # This handles Verse 19: Quote 1 (Black), Quote 2 (Red).

            # Find quotes in the plain text
            quotes = [m.group(0) for m in QUOTE_PATTERN.finditer(full_text_content)]
            if not quotes: continue

            mask = []
            # For each quote found in text, check if it exists inside the WOJ html
            # This is a loose heuristic: if the quote string appears inside the WOJ block.
            # (A strict DOM overlap check is harder, but this usually works for unique quotes)
            for q in quotes:
                # Clean punctuation for better matching
                clean_q = q.strip('“"「”"」,.?!')
                if not clean_q:
                    mask.append(False)
                    continue

                if clean_q in woj_text:
                    mask.append(True)
                else:
                    mask.append(False)

            red_map[verse_num] = {'type': 'MASK', 'mask': mask}

    except Exception:
        pass

    return red_map

def get_bible_passage(passage, version, include_verses=True, red_letter_map=None, red_letter_enabled=True):
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version={version}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    result_data = {"text": "", "ref": passage.strip()}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for footer in soup.find_all('div', class_=['footnotes', 'crossrefs', 'publisher-info-bottom']):
            footer.decompose()

        ref_div = soup.find("div", class_="dropdown-display-text")
        if ref_div: result_data["ref"] = ref_div.get_text().strip()

        container = soup.find("div", class_="passage-content") or soup.find("div", class_="passage-text")
        if not container:
            result_data["text"] = f"Error: Could not find text for version '{version}'."
            return result_data

        passage_pieces = []
        tags_to_find = re.compile(r'^h[34]$|^span$')

        current_verse_num = None

        for element in container.find_all(tags_to_find):

            # --- CASE A: Header (Insert Paragraph Break) ---
            if element.name in ['h3', 'h4']:
                passage_pieces.append("\n\n")
                continue

            # --- CASE B: Verse Block ---
            if element.find_parent(['h3', 'h4']): continue

            class_list = element.get('class', [])
            if any('text' in c for c in class_list):

                # Cleanup junk
                for junk in element.find_all(['sup', 'div'], class_=['footnote', 'crossreference', 'bibleref', 'footnotes']):
                    junk.decompose()

                # --- 1. Separate Verse Number from Text ---
                # We extract the number tag so we can process the text string safely without mangling HTML attributes.
                v_tag = element.find(['span', 'strong', 'b', 'sup'], class_=['versenum', 'chapternum', 'v-num'])
                v_tag_html = ""

                if v_tag:
                    # Update current verse tracker
                    current_verse_num = v_tag.get_text().strip()

                    if include_verses:
                        # Style the number
                        classes = v_tag.get('class', [])
                        style = "color: #999; font-size: 0.75em; font-weight: bold; margin-right: 3px;"
                        if 'chapternum' in classes:
                            style = "color: #999; font-size: 1.5em; font-weight: bold; margin-right: 5px;"

                        # Save the styled HTML for later reconstruction
                        v_tag_html = f'<span style="{style}">{current_verse_num}</span>'

                    # Remove the tag from the tree so we get only text remainder
                    v_tag.decompose()

                # --- 2. Process the Remaining Text ---
                # Check for NATIVE red letters (e.g. if user asked for CEB directly)
                has_native_red = False
                if red_letter_enabled:
                    for woj in element.find_all(class_='woj'):
                        woj['style'] = "color: #cc0000;"
                        has_native_red = True

                # Get clean text (after removing verse num)
                # We preserve inner tags (like native woj) by decoding contents
                text_content = element.decode_contents().strip()

                # If there's content left...
                if text_content:

                    # --- 3. Apply Heuristic Red Lettering ---
                    # Only if enabled, no native red exists, and we have a map for this verse
                    if red_letter_enabled and not has_native_red and red_letter_map and current_verse_num in red_letter_map:

                        rule = red_letter_map[current_verse_num]

                        if rule['type'] == 'FULL':
                            # Logic: The whole verse is Jesus (e.g. John 14:1)
                            text_content = f'<span style="color: #cc0000;">{text_content}</span>'

                        elif rule['type'] == 'MASK':
                            # Logic: Apply Boolean Mask to sequence of quotes
                            mask = rule['mask']
                            quote_counter = 0

                            def replace_quote_with_logic(match):
                                nonlocal quote_counter
                                # Determine if this specific quote index should be red
                                is_red = False
                                if quote_counter < len(mask):
                                    is_red = mask[quote_counter]
                                quote_counter += 1

                                if is_red:
                                    return f'<span style="color: #cc0000;">{match.group(0)}</span>'
                                return match.group(0)

                            # Run Regex on the text content
                            text_content = QUOTE_PATTERN.sub(replace_quote_with_logic, text_content)

                    # Reassemble: Verse Number + Processed Text
                    passage_pieces.append(v_tag_html + text_content)

        full_text = " ".join(passage_pieces)

        # Whitespace Cleanup
        full_text = re.sub(r' \n', '\n', full_text)
        full_text = re.sub(r'\n ', '\n', full_text)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        full_text = re.sub(r'[ ]{2,}', ' ', full_text)

        result_data["text"] = full_text.strip()
        return result_data

    except Exception as e:
        result_data["text"] = f"An error occurred with version {version}: {e}"
        return result_data

# --- HTML Template ---
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
        h3.version-title { margin-top: 0; margin-bottom: 5px; color: #007bff; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
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
            <input type="text" name="passage" placeholder="e.g. John 8:12, Mark 2" required value="{{ passage }}">
            <input type="text" name="versions" placeholder="e.g. KOERV NIV" required value="{{ versions_str }}">
            <div style="display:flex; flex-direction:column; gap:5px;">
                <label><input type="checkbox" name="include_verses" {% if include_verses %}checked{% endif %}> Verse Numbers</label>
                <label><input type="checkbox" name="red_letter" {% if red_letter %}checked{% endif %}> Jesus's words in red</label>
            </div>
            <button type="submit" id="submitBtn">Fetch</button>
        </div>
    </form>
    <div id="spinner"><div class="loader"></div> Processing...</div>
    {% if results %}
        <div id="results-container">
            {% for v_block in results %}
                <div class="result">
                    <div id="copy-target-{{ loop.index }}">{% for item in v_block.passages %}<h3 class="version-title">{{ v_block.name }} - {{ item.ref }}</h3><div class="passage-content">{{ item.text | safe }}</div>{% if not loop.last %}<br><br>{% endif %}{% endfor %}</div>
                    <button class="copy-btn" onclick="copyRichText('copy-target-{{ loop.index }}', this)">Copy All {{ v_block.name }}</button>
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
            const cleanHTML = '<div style="white-space: pre-wrap; font-family: sans-serif;">' + element.innerHTML.trim() + '</div>';
            const cleanText = element.innerText.trim();
            const blobHtml = new Blob([cleanHTML], { type: 'text/html' });
            const blobText = new Blob([cleanText], { type: 'text/plain' });
            try {
                await navigator.clipboard.write([ new ClipboardItem({ 'text/html': blobHtml, 'text/plain': blobText }) ]);
                var originalText = btn.innerText;
                btn.innerText = "Copied!";
                btn.style.backgroundColor = "#28a745";
                setTimeout(function() { btn.innerText = originalText; btn.style.backgroundColor = "#6c757d"; }, 2000);
            } catch (err) { console.error('Failed to copy: ', err); btn.innerText = "Error"; btn.style.backgroundColor = "#dc3545"; }
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def home():
    results = []
    passage = ""
    versions_str = ""
    include_verses = True
    red_letter = True

    if request.method == 'POST':
        passage = request.form.get('passage')
        versions_str = request.form.get('versions')
        include_verses = True if request.form.get('include_verses') else False
        red_letter = True if request.form.get('red_letter') else False

        version_list = [v.upper() for v in re.split(r'[,\s]+', versions_str) if v]
        passage_list = [p.strip() for p in passage.split(',') if p.strip()]

        for v in version_list:
            version_block = {'name': v, 'passages': []}
            for p in passage_list:
                ceb_map = analyze_ceb_for_red_letters(p) if red_letter else None
                data = get_bible_passage(p, v, include_verses, ceb_map, red_letter)
                version_block['passages'].append(data)
            results.append(version_block)

    return render_template_string(HTML_TEMPLATE, results=results, passage=passage, versions_str=versions_str, include_verses=include_verses, red_letter=red_letter)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
