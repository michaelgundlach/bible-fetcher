#!/usr/bin/env python3
from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup, Tag
import re
import traceback

app = Flask(__name__)

# --- REGEX PATTERNS ---
QUOTE_FINDER = re.compile(r'(?s)([“"「«])(.*?)(?:[”"」»]|$)')
NORMALIZER = re.compile(r'[\W_]+')

def normalize(text):
    return NORMALIZER.sub('', text).lower()

def get_quote_blocks(text):
    """
    Parses verse text into Quote Blocks.
    """
    blocks = []
    tokens = re.split(r'([“"「«”"」»])', text)

    current_text = ""
    in_quote = False

    for t in tokens:
        if t in ['”', '」', '»']: # Closers
            in_quote = True
            break
        if t in ['“', '「', '«']: # Openers
            in_quote = False
            break

    for token in tokens:
        if not token: continue

        if re.match(r'[“"「«”"」»]', token):
            if token in ['“', '「', '«']: # OPENER
                if not in_quote:
                    if current_text:
                        blocks.append({'text': current_text, 'is_quote': False, 'is_implicit': False})
                        current_text = ""
                    in_quote = True
                current_text += token

            elif token in ['”', '」', '»']: # CLOSER
                current_text += token
                if in_quote:
                    blocks.append({'text': current_text, 'is_quote': True, 'is_implicit': False})
                    current_text = ""
                    in_quote = False
            else:
                if not in_quote:
                    if current_text:
                        blocks.append({'text': current_text, 'is_quote': False, 'is_implicit': False})
                        current_text = ""
                    in_quote = True
                    current_text += token
                else:
                    current_text += token
                    blocks.append({'text': current_text, 'is_quote': True, 'is_implicit': False})
                    current_text = ""
                    in_quote = False
        else:
            current_text += token

    if current_text:
        blocks.append({'text': current_text, 'is_quote': in_quote, 'is_implicit': in_quote})

    return blocks

def analyze_ceb_for_red_letters(passage, debug_log):
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version=CEB"
    headers = {"User-Agent": "Mozilla/5.0"}

    red_mask_map = {}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return red_mask_map

        soup = BeautifulSoup(response.text, 'html.parser')
        container = soup.find("div", class_="passage-content") or soup.find("div", class_="passage-text")
        if not container: return red_mask_map

        verse_content_map = {}

        for verse_span in container.find_all('span', class_='text'):
            if not isinstance(verse_span, Tag) or verse_span.attrs is None: continue

            c_tag = verse_span.find(class_=['chapternum'])
            if c_tag: c_tag.decompose()

            v_num_tag = verse_span.find(class_=['versenum', 'v-num'])
            if v_num_tag:
                current_verse = v_num_tag.get_text().strip()
                v_num_tag.decompose()
            elif 'current_verse' not in locals():
                continue

            temp_span = BeautifulSoup(str(verse_span), 'html.parser')
            for junk in temp_span.find_all(class_=['footnote', 'crossreference']):
                junk.decompose()

            if current_verse not in verse_content_map:
                verse_content_map[current_verse] = {'full_text': "", 'woj_spans': []}

            verse_content_map[current_verse]['full_text'] += temp_span.get_text()
            woj_texts = [w.get_text() for w in temp_span.find_all(class_='woj')]
            verse_content_map[current_verse]['woj_spans'].extend(woj_texts)

        for v_num, data in verse_content_map.items():
            full_text = data['full_text'].strip()
            all_woj_text = "".join(data['woj_spans'])

            norm_woj = normalize(all_woj_text)
            norm_full = normalize(full_text)

            blocks = get_quote_blocks(full_text)
            quote_blocks = [b for b in blocks if b['is_quote']]

            is_implicit_red_verse = False
            if not quote_blocks and len(norm_full) > 0:
                ratio = len(norm_woj) / len(norm_full)
                if ratio > 0.9:
                    is_implicit_red_verse = True
                    quote_blocks = [{'text': full_text, 'is_quote': False, 'is_implicit': True}]

            mask_data = []
            debug_info = []

            for block in quote_blocks:
                is_red = False
                if is_implicit_red_verse:
                    is_red = True
                else:
                    norm_block = normalize(block['text'])
                    if norm_block and norm_block in norm_woj:
                        is_red = True

                mask_data.append({
                    'is_red': is_red,
                    'is_implicit': block.get('is_implicit', False)
                })
                d_txt = block['text'][:10].replace("\n","")
                debug_info.append(f"'{d_txt}':{is_red}")

            red_mask_map[v_num] = mask_data
            debug_log.append(f"[CEB {v_num}] Mask: {debug_info}")

    except Exception as e:
        debug_log.append(f"[CEB Error] {e}")
        pass

    return red_mask_map

def get_bible_passage(passage, version, include_verses=True, red_letter_map=None, debug_log=None):
    formatted_passage = passage.replace(" ", "+").replace(":", "%3A")
    url = f"https://www.biblegateway.com/passage/?search={formatted_passage}&version={version}"
    headers = {"User-Agent": "Mozilla/5.0"}

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
        verse_buffer = {}
        pending_chapter_html = ""

        # Pass 1: Aggregate
        for element in container.find_all(tags_to_find):
            if not isinstance(element, Tag) or element.attrs is None: continue

            if element.name in ['h3', 'h4']:
                passage_pieces.append({'type': 'header', 'content': "\n\n"})
                continue
            if element.find_parent(['h3', 'h4']): continue

            class_list = element.get('class', [])
            if any('text' in c for c in class_list):
                for junk in element.find_all(['sup', 'div'], class_=['footnote', 'crossreference', 'bibleref', 'footnotes']):
                    junk.decompose()

                v_tag_html = ""

                # Check for Chapter Num
                c_tag = element.find(['span', 'strong', 'b', 'sup'], class_=['chapternum'])
                if c_tag:
                    c_num = c_tag.get_text().strip()
                    if include_verses:
                        c_html = f'<span style="color: #999; font-size: 1.5em; font-weight: bold; margin-right: 5px;">{c_num}</span>'
                        pending_chapter_html += c_html
                    c_tag.decompose()

                # Check for Verse Num
                v_tag = element.find(['span', 'strong', 'b', 'sup'], class_=['versenum', 'v-num'])

                has_native_red = False
                for woj in element.find_all(class_='woj'):
                    woj['style'] = "color: #cc0000;"
                    woj['class'] = "woj-text"
                    woj['data-keep'] = "true"
                    has_native_red = True

                if v_tag:
                    current_verse_num = v_tag.get_text().strip()
                    if include_verses:
                        style = "color: #999; font-size: 0.75em; font-weight: bold; margin-right: 3px;"
                        v_num_html = f'<span style="{style}">{current_verse_num}</span>'
                        v_tag_html = pending_chapter_html + v_num_html
                        pending_chapter_html = ""
                    else:
                        v_tag_html = ""
                        pending_chapter_html = ""
                    v_tag.decompose()
                elif current_verse_num is None:
                    # Still None. If we have text content later, we'll check pending_chapter_html there.
                    pass
                else:
                    if pending_chapter_html:
                        v_tag_html = pending_chapter_html
                        pending_chapter_html = ""

                for tag in element.find_all(True):
                    if not tag.has_attr('data-keep'): tag.unwrap()

                text_content = element.decode_contents().strip()

                if text_content:
                    # --- FIX: Implicit Verse 1 Logic ---
                    if current_verse_num is None and pending_chapter_html:
                        # We have text, no verse num yet, but we just saw Chapter Num.
                        # Assume this is Verse 1.
                        current_verse_num = "1"
                        # Flush the pending chapter HTML as the tag for this verse
                        v_tag_html = pending_chapter_html
                        pending_chapter_html = ""

                    if current_verse_num not in verse_buffer:
                        verse_buffer[current_verse_num] = {
                            'html_content': "",
                            'has_native': False,
                            'v_tag_html': v_tag_html
                        }
                        if v_tag_html:
                            verse_buffer[current_verse_num]['v_tag_html'] = v_tag_html

                    verse_buffer[current_verse_num]['html_content'] += text_content
                    if has_native_red: verse_buffer[current_verse_num]['has_native'] = True

                    last_item_id = None
                    if passage_pieces:
                        if isinstance(passage_pieces[-1], dict):
                            last_item_id = passage_pieces[-1].get('id')

                    if not passage_pieces or last_item_id != current_verse_num:
                        passage_pieces.append({'type': 'verse', 'id': current_verse_num})

        # Pass 2: Process
        final_output = []
        processed_ids = set()

        for item in passage_pieces:
            if not isinstance(item, dict): continue

            if item['type'] == 'header':
                final_output.append(item['content'])
                continue

            v_num = item['id']
            # Safety check: skip if still None (intro text without chapter header)
            if v_num is None: continue

            if v_num in processed_ids: continue
            processed_ids.add(v_num)

            if v_num not in verse_buffer: continue
            data = verse_buffer[v_num]
            text_html = data['html_content']

            if not data['has_native'] and red_letter_map:
                mask = []

                if v_num in red_letter_map:
                    mask = red_letter_map[v_num]
                elif "-" in v_num:
                    try:
                        parts = v_num.split('-')
                        start = int(parts[0])
                        end = int(parts[1])
                        combined_mask = []
                        for i in range(start, end + 1):
                            s_num = str(i)
                            if s_num in red_letter_map:
                                combined_mask.extend(red_letter_map[s_num])
                        if combined_mask: mask = combined_mask
                    except ValueError: pass

                if mask:
                    clean_text = BeautifulSoup(text_html, 'html.parser').get_text()
                    all_blocks = get_quote_blocks(clean_text)
                    quote_blocks = [b for b in all_blocks if b['is_quote']]

                    if not quote_blocks and len(all_blocks) == 1:
                         if len(mask) == 1 and mask[0]['is_implicit']:
                             quote_blocks = all_blocks

                    if debug_log is not None:
                        t_dbg = [f"'{b['text'][:10]}...'" for b in quote_blocks]
                        debug_log.append(f"[{version} {v_num}] Quotes: {len(quote_blocks)} vs Mask: {len(mask)}")
                        debug_log.append(f"   -> Found: {t_dbg}")

                    valid_mapping = True
                    if len(quote_blocks) != len(mask):
                        valid_mapping = False
                    else:
                        for i in range(len(quote_blocks)):
                            if not mask[i]['is_implicit'] and quote_blocks[i]['is_implicit']:
                                valid_mapping = False
                                break

                    if valid_mapping:
                        tokens = re.split(r'([“"「«”"」»])', text_html)
                        new_html_parts = []
                        quote_idx = 0
                        in_quote = False

                        for t in tokens:
                            if t in ['”', '」', '»']: in_quote = True; break
                            if t in ['“', '「', '«']: in_quote = False; break

                        for token in tokens:
                            is_delimiter = re.match(r'[“"「«”"」»]', token)
                            if is_delimiter:
                                new_html_parts.append(token)
                                if token in ['“', '「', '«']:
                                    if not in_quote: in_quote = True
                                elif token in ['”', '」', '»']:
                                    if in_quote: in_quote = False; quote_idx += 1
                                else:
                                    if in_quote: in_quote = False; quote_idx += 1
                                    else: in_quote = True
                            else:
                                if in_quote:
                                    if quote_idx < len(mask) and mask[quote_idx]['is_red']:
                                        new_html_parts.append(f'<span class="woj-text" style="color: #cc0000;">{token}</span>')
                                    else:
                                        new_html_parts.append(token)
                                else:
                                    if quote_idx < len(mask) and mask[quote_idx]['is_red'] and mask[quote_idx]['is_implicit']:
                                         new_html_parts.append(f'<span class="woj-text" style="color: #cc0000;">{token}</span>')
                                    else:
                                         new_html_parts.append(token)
                        text_html = "".join(new_html_parts)

            final_output.append(data['v_tag_html'] + text_html)

        full_text = " ".join(final_output)
        full_text = re.sub(r' \n', '\n', full_text)
        full_text = re.sub(r'\n ', '\n', full_text)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        full_text = re.sub(r'[ ]{2,}', ' ', full_text)

        result_data["text"] = full_text.strip()
        return result_data

    except Exception as e:
        result_data["text"] = f"An error occurred with version {version}: {e}"
        if debug_log: debug_log.append(f"Error: {e} \n {traceback.format_exc()}")
        return result_data

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
        .result { background: #f8f9fa; padding: 25px; border-radius: 8px; margin-top: 20px; border-left: 5px solid #007bff; position: relative; }
        h3.version-title { margin-top: 0; margin-bottom: 5px; color: #007bff; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        .passage-content { white-space: pre-wrap; word-wrap: break-word; font-family: sans-serif; }
        .copy-btn { position: absolute; top: 15px; right: 15px; background: #6c757d; color: white; border: none; font-size: 12px; padding: 6px 12px; border-radius: 4px; cursor: pointer; }
        .hide-red-letters .woj-text { color: inherit !important; }
        .debug-box { margin-top: 30px; background: #333; color: #0f0; padding: 15px; font-family: monospace; font-size: 12px; border-radius: 5px; overflow-x: auto; white-space: pre; }
        label { cursor: pointer; display: flex; align-items: center; gap: 5px; font-weight: 500; }
        #spinner { display: none; margin: 15px 0; font-weight: bold; color: #007bff; }
    </style>
</head>
<body>
    <h2>📖 Bible Passage Fetcher</h2>
    <form id="fetchForm" method="POST">
        <div class="controls">
            <input type="text" name="passage" placeholder="e.g. John 8:12" required value="{{ passage }}">
            <input type="text" name="versions" placeholder="e.g. KOERV NIV" required value="{{ versions_str }}">
            <div style="display:flex; flex-direction:column; gap:5px;">
                <label><input type="checkbox" name="include_verses" {% if include_verses %}checked{% endif %}> Verse Numbers</label>
                <label><input type="checkbox" id="redLetterToggle" name="red_letter" {% if red_letter %}checked{% endif %}> Jesus's words in red</label>
            </div>
            <button type="submit" id="submitBtn">Fetch</button>
        </div>
    </form>
    <div id="spinner">Processing...</div>

    {% if results %}
        <div id="results-container" class="{% if not red_letter %}hide-red-letters{% endif %}">
            {% for v_block in results %}
                <div class="result">
                    <div id="copy-target-{{ loop.index }}">{% for item in v_block.passages %}<h3 class="version-title">{{ v_block.name }} - {{ item.ref }}</h3><div class="passage-content">{{ item.text | safe }}</div>{% if not loop.last %}<br><br>{% endif %}{% endfor %}</div>
                    <button class="copy-btn" onclick="copyRichText('copy-target-{{ loop.index }}', this)">Copy All {{ v_block.name }}</button>
                </div>
            {% endfor %}
        </div>
        <details>
            <summary><strong>Debug Log</strong></summary>
            <div class="debug-box">{% for log in debug_logs %}{{ log }}
{% endfor %}</div>
        </details>
    {% endif %}
    <script>
        document.getElementById('fetchForm').onsubmit = function() {
            document.getElementById('spinner').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').innerText = 'Fetching...';
        };
        var toggle = document.getElementById('redLetterToggle');
        var container = document.getElementById('results-container');
        if (toggle && container) {
            toggle.onchange = function() {
                container.classList.toggle('hide-red-letters', !this.checked);
            };
        }
        async function copyRichText(elementId, btn) {
            const element = document.getElementById(elementId);
            const isRedOn = document.getElementById('redLetterToggle').checked;
            let htmlData = element.innerHTML.trim();
            if (!isRedOn) {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = htmlData;
                wrapper.querySelectorAll('.woj-text').forEach(el => { el.style.color = 'inherit'; });
                htmlData = wrapper.innerHTML;
            }
            const cleanHTML = '<div style="white-space: pre-wrap; font-family: sans-serif;">' + htmlData + '</div>';
            const cleanText = element.innerText.trim();
            const blobHtml = new Blob([cleanHTML], { type: 'text/html' });
            const blobText = new Blob([cleanText], { type: 'text/plain' });
            try {
                await navigator.clipboard.write([ new ClipboardItem({ 'text/html': blobHtml, 'text/plain': blobText }) ]);
                var old = btn.innerText; btn.innerText = "Copied!"; setTimeout(() => btn.innerText = old, 2000);
            } catch (err) { console.error(err); btn.innerText = "Error"; }
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def home():
    results = []
    debug_logs = []
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
                ceb_map = analyze_ceb_for_red_letters(p, debug_logs)
                data = get_bible_passage(p, v, include_verses, ceb_map, debug_logs)
                version_block['passages'].append(data)
            results.append(version_block)

    return render_template_string(HTML_TEMPLATE, results=results, debug_logs=debug_logs, passage=passage, versions_str=versions_str, include_verses=include_verses, red_letter=red_letter)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
