"""Render static information pages and account-specific AdSense verification files.

Edit site-config.json, then run python prepare_site.py. No advertising scripts
are installed by this command. Only upload public HTML, assets, and crawl files.
"""
import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
LINKS = [('index.html', 'Play'), ('how-to-play.html', 'How to play'),
         ('about.html', 'About'), ('privacy.html', 'Privacy'),
         ('contact.html', 'Contact'), ('terms.html', 'Terms & credits')]


def build():
    config = json.loads((ROOT / 'site-config.json').read_text(encoding='utf-8'))
    url = config['site_url'].strip().rstrip('/')
    publisher = config['adsense_publisher_id'].strip().removeprefix('ca-')
    email = config['contact_email'].strip()
    if url:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or '.' not in parsed.hostname
                or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port):
            raise ValueError('site_url must be the public HTTPS origin, without a path or port.')
    if publisher and not re.fullmatch(r'pub-\d{16}', publisher):
        raise ValueError('Use your real pub- ID with exactly 16 digits.')
    if email and not re.fullmatch(r'[^\s<>"@]+@[^\s<>"@]+\.[^\s<>"@]+', email):
        raise ValueError('Enter a valid public contact email.')
    operator = escape(config['operator_name'].strip())
    contact = (f'<a href="mailto:{escape(email, quote=True)}">{escape(email)}</a>'
               if email else 'Contact details have not yet been configured.')
    ready = bool(operator and email and config['hosting_privacy_details'].strip()
                 and config['privacy_reviewed'])
    draft = ('<p class="draft-note"><strong>Draft for site-owner review.</strong> '
             'Operator, contact and hosting details must be completed before publication.</p>')
    footer = '<footer class="site-footer"><nav aria-label="Site information">' + ''.join(
        f'<a href="{path}">{label}</a>' for path, label in LINKS) + '</nav></footer>'
    pages = {
        'about.html': ('About SuPoku', 'An independent Pokémon trivia puzzle with a paper-and-pencil feel.', '''
<p>SuPoku is a Pokémon trivia game built around a three-by-three grid. Each row and column has a clue. Your job is to find a Pokémon that belongs to both, using nine guesses to complete the board.</p>
<h2>A small puzzle with room to think</h2>
<p>The challenge is making connections across what you know: types, regions, moves, evolution, stats and forms. A familiar answer can get you started; remembering an unusual one can make a square especially satisfying. Each Pokémon can be used only once, so an answer that fits several squares is worth saving for the trickier intersection.</p>
<p>Daily mode offers a date-based puzzle. Random mode gives you another grid whenever you want to practice. Each square starts with a free retry, and one undo lets you reconsider a decision during the game.</p>
<h2>How the answers are chosen</h2>
<p>The game checks answers against its bundled Pokédex dataset, based on PokeAPI data. Categories are matched before a grid is shown so that each square has multiple possible answers. Forms are separate entries when their game data differs. The rules page explains several details that can affect an answer.</p>
<h2>An independent fan project</h2>
<p>SuPoku is not affiliated with or endorsed by Nintendo, Game Freak, Creatures, or The Pokémon Company. Pokémon names, characters and artwork belong to their respective rights holders. See <a href="terms.html">Terms &amp; credits</a> for data and artwork sources.</p>
<p><a href="how-to-play.html">Learn the rules</a> or <a href="index.html">start a puzzle</a>.</p>'''),
        'how-to-play.html': ('How to play', 'Rules, retries, undo, clue interpretation and rarity in SuPoku.', '''
<p>Fill the nine squares with Pokémon that match both the row clue and the column clue. You have nine guesses, and you cannot repeat a Pokémon already used on your grid.</p>
<h2>Your first square</h2>
<ol><li>Read a row clue on the left and a column clue above the board.</li><li>Tap their intersecting square. The dialog repeats the clues and shows the number of possible answers.</li><li>Search for a Pokémon by name. Check the exact form: a regional form can have different properties from the original.</li><li>Select an answer. A correct match fills the square and uses one guess.</li></ol>
<p>For example, a square asking for a Water-type Pokémon from Kanto can accept Squirtle. If you use Squirtle there, you must choose something else for every remaining square.</p>
<h2>Retries and your one undo</h2>
<p>Your first incorrect answer in each square is a free retry. It does not spend a guess. Further incorrect answers in that square do spend guesses. A small dot marks a square whose free retry has been used.</p>
<p>You get one undo for the whole grid. Tap a filled square to undo it, or open a square you have tried and choose “Undo this square.” Confirming clears the square and refunds the guesses spent there. It also restores that square’s free retry. Giving up forfeits the remaining undo.</p>
<h2>Reading the clues</h2>
<ul><li><strong>Region:</strong> regional forms belong to their own region. Alolan Meowth counts as Alola. Other entries use the region where their species debuted.</li><li><strong>Type matchups:</strong> weaknesses and resistances use the type chart. Immunity clues also consider supported immunity-granting abilities, including hidden abilities the Pokémon can have.</li><li><strong>Moves:</strong> “Can learn” uses the bundled learnset data. It is not a promise that a move is available in every individual game or competitive format.</li><li><strong>Evolution, stats and forms:</strong> clues refer to the selected entry in the dataset. Search for the specific form when the distinction matters.</li></ul>
<h2>What the colors mean</h2>
<p>When the shared answer service is available, correct answers receive a rarity color based on how often players are expected to choose the same answer for that category pair. Legendary is below 1%, Epic below 5%, Rare below 10%, Uncommon below 25%, and Common is 25% or more. These are answer-popularity labels, not the Pokémon’s in-game legendary status.</p>
<p>Every square starts with estimated pick rates, so rarity works even before anyone has played it. The estimate comes from a 2025 fan survey of favourite Pokémon: a well-loved answer is assumed to be picked more often than an obscure one, and forms or Pokémon with few votes are estimated from similar Pokémon. As players answer a square, their real picks move the percentages more and more, but the survey always keeps part of the say, so a handful of players cannot swing a square completely. Your answer is compared with the picks made before yours. The puzzle remains playable if rarity data is unavailable.</p>
<h2>Daily, Random and saving</h2>
<p>Daily builds a puzzle from the date and a new one arrives at midnight UTC; the countdown under your guesses shows when. Archive lets you replay any past daily grid for practice, and Random creates a fresh challenge. Guest, archive and random progress is saved in this browser, so you can reload or come back later and pick up where you left off. Signed-in daily games are saved to your account instead. When a grid ends, tap any square of the summary to see every valid answer and how often each was picked.</p>
<h2>A useful strategy</h2>
<p>Start with the most restrictive pair of clues. Then look for Pokémon that fit only one of your remaining squares, keeping versatile answers available until you need them. If an answer is rejected, check its form and the clue definitions before spending another guess.</p>
<p>If you find a data mismatch, use the <a href="contact.html">contact page</a> and include both clues and the exact Pokémon name.</p>'''),
        'privacy.html': ('Privacy & storage', 'How SuPoku uses browser storage, answer tallies and external image hosting.',
            ('' if ready else draft) + f'''
<p>Last updated: 7 September 2026.</p>
<h2>Who operates this site</h2><p>{operator or 'Site operator details are pending.'} Privacy questions: {contact}</p>
<h2>Playing without an account</h2>
<p>Guest play does not require an account. Search text is filtered in your browser against the downloaded Pokédex; it is not sent to a search service.</p>
<h2>Optional accounts, friends and daily scores</h2>
<p>If you register, we store your username, a salted password hash, account creation time, friends list and daily game history. Passwords are not stored in plain text. Your username and score statistics are public in leaderboards and friends lists. Your own friends list and detailed history require your login. Adding a friend is one-way and does not send them a message.</p>
<p>Signed-in daily guesses, retries, undo and final scores are saved on the server to resume play and calculate scores and streaks. Account records remain until you delete your account in the Account panel. Deletion also removes its sessions, friends relationships and leaderboard results. Hosting backups, if any, follow the operator’s retention policy, which is pending below.</p>
<p>A necessary HttpOnly session cookie named <code>supoku_session</code> keeps you signed in for up to 30 days. Signing out revokes that session. The server briefly tracks IP addresses in memory to limit repeated login attempts (15 minutes). No email address is collected for accounts; email password recovery is not configured.</p>
<p>When the frontend is hosted on GitHub Pages and the account service on Render, login instead uses a session token in this browser’s local storage, under <code>supoku:session:</code> followed by the API address. It keeps you signed in across tabs and visits and expires on the server after 30 days; signing out removes it and revokes the session. This avoids relying on third-party cookies. Do not share this token.</p>
<h2>Browser storage</h2>
<p>Your chosen light or dark theme is stored under <code>supoku:theme</code> until you clear this site’s browser storage or choose another theme. Before you choose, the site follows your device’s appearance preference.</p>
<p>The game stores your pixel-sprite preference in local storage under <code>supoku:pixelArt</code>. It can also read preferences left by earlier versions under <code>supokeku:pixelArt</code> and <code>pokegrid:pixelArt</code>. This preference remains until you clear the site’s browser storage or change it. Guest, archive and random puzzle progress is stored in local storage under keys starting <code>supoku:game:</code>, plus <code>supoku:current</code> for the grid you last played, so a reload resumes your board. It stays until you clear the site’s browser storage. Signed-in daily progress is saved to your account.</p>
<h2>Shared answer statistics</h2>
<p>When you submit a correct answer, the game sends its category pair and Pokémon identifier to this site’s answer service. Undoing a recorded answer sends a corresponding adjustment. The application stores aggregate counts by category pair and answer, rather than an account-based history. These counts support the rarity colors and remain until the operator resets them.</p>
<h2>Connection information and hosting</h2>
<p>Loading the site and using its answer service exposes normal connection information, including your IP address, to the hosting infrastructure. The supplied answer server logs API requests with an IP address, request path and time. Hosting providers may keep additional access or security logs.</p>
<p>{escape(config['hosting_privacy_details'].strip()) or 'Hosting provider, log retention and handling of privacy requests must be confirmed by the operator before this policy is finalized.'}</p>
<h2>External images</h2>
<p>Pokémon images are requested from the PokeAPI sprites repository through GitHub’s raw-content hosting. That service receives connection information when your browser requests an image. See <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub’s privacy statement</a>. Type icons and the paper texture are served by this site.</p>
<h2>Advertising</h2>
<p>This version does not load Google AdSense ad-serving code or analytics. If advertising is enabled, this policy must be updated to describe the deployed services and your available consent controls.</p>
<p>Google advertising can use cookies, web beacons, IP addresses and other identifiers to deliver, personalize and measure ads. Google and other third-party vendors may use cookies to serve ads based on earlier visits to this or other websites. Google’s advertising cookies can enable Google and its partners to personalize ads based on those visits. Read <a href="https://policies.google.com/technologies/partner-sites">how Google uses information from partner sites</a> and manage personalization in <a href="https://myadcenter.google.com/">My Ad Center</a>. These links describe Google’s services; no ads are enabled by this page.</p>
<h2>Contact and choices</h2>
<p>You can clear this site’s local storage using your browser’s site-data controls. For questions about connection records, information you send by email, or applicable data-access and deletion requests, contact: {contact}</p>
<p>If you email the operator, your email address and message are made available to the operator and their email provider to handle your inquiry. Do not send passwords, payment information or other sensitive details.</p>'''),
        'contact.html': ('Contact', 'Report a SuPoku puzzle issue or ask about privacy and content.',
            ('' if email else draft) + f'''
<p>For puzzle feedback, accessibility issues, privacy questions or rights-holder inquiries, contact {operator or 'the site operator'}.</p>
<p class="contact-address">{contact}</p>
<h2>Reporting a puzzle problem</h2>
<p>Please include the Daily puzzle date or say that you were playing Random, the row and column clues, the Pokémon and form you selected, and what happened. Your browser and device type can help with a display problem. A screenshot is optional; remove personal information before sending one.</p>
<h2>Artwork and content inquiries</h2>
<p>Identify the material and its location on the site, explain your concern, and provide a way to respond. SuPoku is an independent fan project; it cannot provide support for official Pokémon games or accounts.</p>
<p>See <a href="privacy.html">Privacy &amp; storage</a> for how the game handles information.</p>'''),
        'terms.html': ('Terms & credits', 'Use of SuPoku and acknowledgment of its data and artwork sources.', '''
<p>SuPoku is a free fan-made trivia puzzle. These notes explain its intended use and the sources behind it.</p>
<h2>Playing fairly</h2>
<p>Please use the game for personal puzzle play. Do not disrupt the service, automate requests to manipulate answer statistics, or attempt to access systems or data beyond the public game features.</p>
<h2>Game data and availability</h2>
<p>Answers are evaluated using the game’s dataset. Pokémon mechanics vary between games, and data errors or omissions are possible. Rarity is an estimate from a fan survey and submitted answers, not an official ranking. Features and data may change, and archive grids are regenerated from the current dataset, so an old date can differ slightly after a data update. Please report suspected errors through the <a href="contact.html">contact page</a>.</p>
<h2>Data and artwork credits</h2>
<ul><li>Pokédex data: <a href="https://github.com/PokeAPI/pokeapi">PokeAPI</a>.</li><li>Starting rarity estimates: the 2025 Favourite Pokémon survey results compiled by Sparklez Squad.</li><li>Pokémon sprites and artwork: <a href="https://github.com/PokeAPI/sprites">PokeAPI sprites repository</a>.</li><li>Locally mirrored type icons: the <a href="https://github.com/yousif720/typedle">typedle project</a>, as recorded in this project’s source documentation.</li><li>Scapholène typeface by Scapholène, used unchanged with its <a href="assets/fonts/LICENSE_Scapholene.txt">original license</a>.</li></ul>
<p>Pokémon and related names, characters and artwork belong to their respective rights holders, including Nintendo, Game Freak, Creatures and The Pokémon Company. SuPoku is not affiliated with or endorsed by those organizations. Source attribution does not transfer ownership or grant a license to reuse their material.</p>
<p>Questions about this site or its content can be sent using the <a href="contact.html">contact page</a>.</p>''')
    }
    def metadata(path):
        result = ''
        if url:
            result += f'<link rel="canonical" href="{escape(url, quote=True)}/{"" if path == "index.html" else path}">\n'
        if publisher:
            result += f'<meta name="google-adsense-account" content="ca-{publisher}">\n'
        return result
    for path, (title, description, body) in pages.items():
        robots = '<meta name="robots" content="noindex">' if (not ready and path == 'privacy.html') or (not email and path == 'contact.html') else ''
        html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · SuPoku</title>
<meta name="description" content="{escape(description, quote=True)}">
{metadata(path)}{robots}<script src="theme.js"></script><link rel="stylesheet" href="style.css"></head>
<body class="info-page"><header class="topbar"><a class="brand" href="index.html"><span class="ball" aria-hidden="true"></span> SuPoku</a><a class="pill" href="index.html">Back to puzzle</a></header>
<main class="document-page"><article><h1>{escape(title)}</h1>{body}</article></main>
{footer}<div class="theme-footer"><button class="ghost" type="button" data-theme-toggle aria-pressed="false">Dark theme</button></div></body></html>'''
        (ROOT / path).write_text(html, encoding='utf-8')
    index = (ROOT / 'index.html').read_text(encoding='utf-8')
    index = re.sub(r'<!-- SITE META START -->.*?<!-- SITE META END -->\s*', '', index, flags=re.S)
    index = index.replace('</head>', '<!-- SITE META START -->\n' + metadata('index.html') + '<!-- SITE META END -->\n</head>')
    index = re.sub(r'<!-- SITE FOOTER START -->.*?<!-- SITE FOOTER END -->\s*', '', index, flags=re.S)
    index = index.replace('</body>', '<!-- SITE FOOTER START -->\n' + footer + '\n<!-- SITE FOOTER END -->\n</body>')
    (ROOT / 'index.html').write_text(index, encoding='utf-8')
    robots = 'User-agent: *\nAllow: /\nDisallow: /api/\n'
    if url:
        robots += f'Sitemap: {url}/sitemap.xml\n'
        paths = ['index.html', *pages]
        entries = ''.join(f'<url><loc>{escape(url)}/{"" if path == "index.html" else path}</loc></url>\n'
                          for path in paths if not ((not ready and path == 'privacy.html') or (not email and path == 'contact.html')))
        (ROOT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + '</urlset>\n', encoding='utf-8')
    (ROOT / 'robots.txt').write_text(robots, encoding='utf-8')
    (ROOT / 'ads.txt').write_text(f'google.com, {publisher}, DIRECT, f08c47fec0942fa0\n' if publisher else '# No authorized advertising sellers configured. Add your publisher ID to site-config.json and run prepare_site.py.\n', encoding='utf-8')
    missing = [key for key, value in config.items() if not value]
    print('Generated static pages, footer, robots.txt and ads.txt.')
    print('Still needed: ' + ', '.join(missing) if missing else 'Configuration complete. Follow ADSENSE-SETUP.md before submitting.')
    if not url:
        print('Sitemap generation awaits the real public domain; no fake domain was published.')


if __name__ == '__main__':
    build()
