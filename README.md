# Bible Passage Fetcher & Red Letter Projector

## 📖 Overview
This is a Flask-based web application that fetches Bible passages from BibleGateway. Its primary, complex feature is **Cross-Translation Red Letter Projection**. 

Many foreign-language or non-standard translations on BibleGateway (like KOERV, JLB, CNVS) do not natively highlight the Words of Jesus (WOJ) in red. This application solves that by fetching the **CEB (Common English Bible)** translation in the background, analyzing its native red-letter tags (`<span class="woj">`), and mathematically "projecting" that red-letter mask onto the target translation using custom tokenization and structure matching.

## 🌐 Live Website & Continuous Deployment

### Continuous Deployment via Render GitHub App
This repository is configured with automated continuous deployment hosted on **Render** via the **Render GitHub App** integration. 

* **How Deployment Works:** 
  1. Local changes are pushed to GitHub (`git push origin main`).
  2. GitHub automatically notifies Render through the installed **Render GitHub App** (configured in GitHub Account Settings > Installed GitHub Apps).
   3. Render pulls the latest commit from `michaelgundlach/bible-fetcher`, runs `pip install -r requirements.txt`, and redeploys the service automatically to `https://bible-fetcher.onrender.com`.
* **No Manual Webhooks or Server Access Needed:** You will not find a standard repo-level Webhook URL in `Settings > Webhooks` on GitHub; the trigger is managed entirely at the account level via the Render GitHub App integration.

### Hosting Details
* **Hosting Provider:** Render
* **Live App Name:** `bible-fetcher`
* **Repository:** `https://github.com/michaelgundlach/bible-fetcher`
* **Build Command:** Render installs dependencies from `requirements.txt`
* **Start Command:** `gunicorn -w 4 -b 0.0.0.0:$PORT app:app`

---

## 🧠 Core Architecture & Context for Future LLMs
*Future AI agents: Read this carefully before modifying the parsing logic.*

The HTML structure of BibleGateway is highly inconsistent across translations. The projection logic relies on sequence-matching rather than direct text translation.

### 1. The Masking Algorithm
1. **Fetch CEB:** We fetch the CEB version of the requested passage.
2. **Normalize & Fuzzy Match:** We strip punctuation and whitespace. We compare logical text blocks against the known native `<span class="woj">` text to create a boolean mask (e.g., Verse 1: `[Narrative: False, Quote: True]`).
3. **Fetch Target:** We fetch the target translation (e.g., KOERV).
4. **Tokenize Target:** We use the same quote-splitting logic on the target text.
5. **Apply Mask:** We map the boolean mask from the CEB to the target's parsed blocks and inject `<span class="woj-text" style="color: #cc0000;">`.

### 2. The Tokenizer (`get_quote_blocks`)
We split text strings using a custom regex: `r'([“"「«”"」»])'`.
* **Smart Quotes:** We rely heavily on directional smart quotes (`“` vs `”`, `「` vs `」`) to track whether we are inside or outside a quote. 
* **Straight Quotes (`"`):** These toggle the state back and forth.
* **Implicit Open/Close:** The tokenizer intelligently handles verses that start in the middle of a speech (Implicit Open, where the first delimiter is a closer) or end in the middle of a speech (Implicit Close).
* *Crucial Bugfix:* Do NOT let an unclosed quote bleed red color into surrounding narrative text. The `is_implicit_verse` flag is used *only* when >90% of the entire verse is red (like John 15), not just when a single quote block lacks a closing punctuation mark.

### 3. HTML Parsing Quirks (Do Not Regress These!)
BibleGateway's HTML requires defensive, paranoid parsing.
* **Tag Attributes:** BeautifulSoup occasionally yields tags where `element.attrs is None`. The code includes explicit checks (`if not isinstance(element, Tag) or element.attrs is None: continue`) to prevent `NoneType` crashes.
* **Chapter & Verse Numbers:** Sometimes they appear side-by-side (`<span class="chapternum">9</span><sup class="versenum">1</sup>`), sometimes separated by text. The code specifically buffers `pending_chapter_html` so it can prepend it to the verse number ensuring proper styling.
* **Implicit Verse 1:** Translations like KOERV and JLB often omit the `<sup class="versenum">1</sup>` entirely if it's the start of a chapter (e.g., `<span class="chapternum">9</span> 예수께서...`). The code explicitly detects if we have text right after a chapter number but no verse ID, and safely forces `current_verse_num = "1"`.

---

## 📁 File Structure
* `app.py`: The main Flask application containing all routes, scraping logic, tokenization, and HTML injection.
* `bible.py`: Auxiliary scripts or legacy fetching logic.
* `requirements.txt`: Python dependencies (`Flask`, `requests`, `beautifulsoup4`, `gunicorn`).
* `venv/`: Standard Python virtual environment.

---

## 💻 Local Development
1. Activate the virtual environment: `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\activate` (Windows).
2. Install dependencies: `pip install -r requirements.txt`
3. Run the app: `python app.py`
4. Access the UI at: `http://localhost:5001` (or `http://0.0.0.0:5001`).

---

## 🚀 Deployment Workflow (Notes for LLMs)

### Updating the Live Site
1. Make code changes locally.
2. Test locally with `python app.py`.
3. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Describe your update"
   git push origin main
   ```
4. Render automatically detects the new commit on `main` and redeploys (no manual action needed).
5. Verify the change is live at `https://bible-fetcher.onrender.com` (note: free Render instances may take a minute to spin up after inactivity).

### Rollback
If a deploy breaks the site, use the Render Dashboard (`dashboard.render.com` > service `bible-fetcher` > **Events**/**Manual Deploy**) to redeploy a previous commit while you fix the issue locally.
