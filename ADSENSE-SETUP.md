# SuPoku AdSense preparation

The site has supporting pages and a publisher-file generator. **It is not approved or ready to serve ads yet.** Google reviews the whole site; adding legal pages, a sitemap or ads.txt does not establish eligibility. About, contact, rules and terms pages are useful supporting content, not a guaranteed Google checklist.

## Already included

- Linked, static About, How to Play, Privacy, Contact, and Terms/Credits pages that work without JavaScript.
- The supplied contact email, ybgamer44@gmail.com.
- A privacy draft grounded in this code's local-storage preference, aggregate answer submissions, server logging and GitHub image requests.
- `robots.txt`, homepage description and a JavaScript-disabled fallback.
- `ads.txt` with comments only until a real publisher ID is provided. It does **not** currently authorize an ad seller.
- `prepare_site.py`: generates the public pages, canonical URLs, sitemap and non-tracking AdSense verification meta tags when the real details are configured.
- No AdSense scripts, analytics, fake publisher IDs or homemade consent banner.

## Finish the site details

Edit `site-config.json`:

- `site_url`: your public HTTPS origin, without a trailing path (not localhost).
- `operator_name`: the actual person or organization responsible for this site.
- `contact_email`: already filled; use an address you monitor.
- `adsense_publisher_id`: the `pub-` ID from your account, with 16 digits. `ca-pub-` format is also accepted.
- `hosting_privacy_details`: factual public-facing information naming your host, the connection logs it retains, retention periods and how privacy requests are handled. Confirm the email provider's retention and handling too. Do not invent a retention period.
- `privacy_reviewed`: set to `true` only after reviewing the privacy page against your actual hosting, operator obligations and data practices. The generated page is a starting point, not a certification of legal compliance. Add applicable legal bases, rights, recipients, transfers and retention details based on your real circumstances.

Run `python prepare_site.py` after changes. The command prints missing fields. Re-running is safe: it replaces generated pages and its marked homepage blocks. Edit the page source text in this script if you need to revise it permanently.

Until privacy details are complete, the privacy page is visibly marked as a draft and has `noindex`. The script removes both when the configuration is complete. The contact page is live with the supplied email. Without a domain, no sitemap or canonical URL is fabricated. Once configured, the sitemap uses absolute URLs and excludes unfinished pages.

## Publish and submit for review

1. Obtain a domain and publish the site over HTTPS so the public and Google's crawlers can reach it without a login. Localhost cannot be submitted as the public site.
2. Deploy the public HTML pages, `style.css`, `app.js`, `theme.js`, `assets/`, `data/pokedex.json`, `robots.txt`, `ads.txt` and, once generated, `sitemap.xml`. Do not expose config/build files, source documentation, `.git`, server logs or the writable statistics store. `robots.txt` is not access control. The bundled Python server is a local development server; use a production host and a suitable backend if you want shared rarity statistics.
3. Confirm that the public homepage, every footer page and `/ads.txt` return successfully. Check the generated sitemap and canonical domain, and remove any staging password or crawler block. Configure normal 404 responses for missing pages.
4. Review the full site for original value, working navigation and policy compliance. The rules explain this game's specific behavior; extra generic pages or word counts do not guarantee approval.
5. Confirm you have the rights needed to commercially use all Pokémon artwork, names, icons and other third-party material. Attribution or a fan-project disclaimer is not permission. Resolve rights issues before monetizing.
6. Create an AdSense account if eligible (an account holder must be at least 18; Google's guardian route applies otherwise). Add the public domain under Sites.
7. Enter your real publisher ID in the config and rebuild. Use Google's **meta tag** verification option: the generator puts `google-adsense-account` in the HTML head without requesting ads. It also writes the Google seller record to `/ads.txt`. Confirm the exact values against your account.
8. Request site review in AdSense. Approval is Google's decision and is separate from ownership verification. There is no supported promise that these files will secure approval.

## Before turning on advertising

- Configure and publish Google's certified CMP through AdSense Privacy & messaging, or another Google-certified TCF CMP, for visitors in the EEA, UK and Switzerland. A custom accept/reject cookie box is not a substitute. Review other applicable regional privacy requirements and provide a working way to revisit consent choices.
- Determine whether the site or any portion is child-directed, and configure advertising appropriately. Do not infer this solely from the Pokémon theme or bypass the decision with a blanket age statement.
- Update the privacy page to describe actual active vendors, cookies/identifiers, uses and available consent controls; replace the current statement that advertising is disabled. Check Google's required privacy disclosures.
- Only then integrate account-provided ad code with the CMP. This preparation intentionally does not install or request ads.
- Keep ads clearly separated from the puzzle, search results, submit actions and other controls. Do not encourage ad clicks or place ads where taps intended for the game could hit them. Review Auto ads placements on phone and desktop before enabling them.
- Verify accept, reject and consent-reopening flows and inspect ad requests/cookies for each choice. Recheck the layout with real ad slots; this version does not reserve ad space.

## Primary references (checked 7 September 2026)

- [Eligibility](https://support.google.com/adsense/answer/9724?hl=en)
- [Connect and verify your site](https://support.google.com/adsense/answer/7584263?hl=en)
- [Site review and ads.txt](https://support.google.com/adsense/answer/12131223?hl=en)
- [Publisher policies, including privacy and intellectual property](https://support.google.com/adsense/answer/10502938?hl=en)
- [Cookies and privacy disclosures](https://support.google.com/adsense/answer/7549925?hl=en)
- [Certified CMP requirements](https://support.google.com/adsense/answer/13554116?hl=en)
