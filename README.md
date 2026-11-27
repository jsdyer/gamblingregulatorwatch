# Gambling Regulator Watch

Explore public gambling licence and enforcement records by legal entity, trading name or authority. The opening record links a specific decision to its operator profile. Use **Compare regulators** to inspect the population, period and source behind a count. The operator and regulator directories also work with JavaScript disabled.

<!-- coolcode:guide -->
Search by legal entity or a source-listed trading name. A profile links each licence and published action to its issuing authority. Compare the coverage and dates before interpreting repeat cases or documented revocation intervals.
Look up an exact website in the Tobique and Malta warning lists. The result preserves each regulator’s date, source and listing category.
<!-- /coolcode:guide -->

BML Group Limited’s Malta licence profile links to its historical corporate-registry entry in ICIJ and to the [CoolCode Field Note on Canadian connections in offshore records](https://coolcode.ca/field-notes/reading-offshore-records/). Corporate-registry appearances are stored separately from enforcement data.

## Reading the evidence

- **Published actions** include suspensions, notices, settlements and revisions. A timeline may contain several stages of one matter. Distinct qualifying cases group eligible stages by authority, legal entity and case ID. Two cases may concern different conduct.
- **Later licence evidence** pairs an imposed foreign penalty with a dated operator licence or current register observation. Check the two authorities and original language. An observation alone establishes neither a renewal after the penalty nor uninterrupted operation. Parent companies, overlapping brands and similar names cannot establish identity by themselves.
- **Elapsed days** run between two documented events in the same matter. The tool distinguishes a suspension or notice date from the unknown first date of conduct. A notice-to-publication interval and an effective revocation interval have different endpoints.
- **Rates** use an explicit population and time window. For Great Britain the numerator comes from published operating-account decisions within the previous 365 days among accounts active on the snapshot date. Malta's annual figure divides the reported number of administrative penalties by the official year-end company count. Comparing these as national risk scores would mix different events, scopes and populations.
- **Coverage** varies. The Ontario directory covers contracted iGaming Ontario operators. The Australian federal communications regulator reports online gambling enforcement and publishes a list of wagering services licensed by states and territories. Many registers include suppliers. A missing case can reflect publication scope, selection, language, timing or retention.
- **Corrections and appeals** remain visible with their stage and date. A proposed sanction, a voluntarily surrendered licence and a quashed decision require different treatment. Foreign licensing and repeat case totals use explicit eligibility flags.

## Updates

GitHub Actions is configured for **Friday at 09:43 UTC**, with manual dispatch. Each register importer validates its data before replacing the saved source. The job tests the code, rebuilds the explorer, source-linked profiles and sitemap, and publishes the same edition to GitHub Pages. A push rebuilds the existing snapshots. A green code build alone gives no evidence of a new source download.

The release includes the source observation date, register scope and underlying decision dates. Each authority has an independent refresh result. A partial run can publish successful sources alongside the last valid records for failed sources, exposes that fact in the source status and raises a workflow failure after deployment. If every import fails, publication stops. Git history preserves committed editions. The separate notice index collects official publication links for Ontario, Kahnawà:ke and Malta. Newly seen links enter the review queue. Human-reviewed actions and identity proofs require review when publications or appeal outcomes change. The Australia index includes a manual source link.

| Authority | Automatic register coverage | Enforcement coverage |
| --- | --- | --- |
| Kahnawà:ke Gaming Commission | Public interactive permit-holder directory | Selected notices with documented procedural stages |
| Tobique Gaming Commission | Published B2B and B2C licence list with expiry | Named-entity cases only where supported by a decision |
| AGCO / Ontario | iGaming Ontario contracted operators and trading sites | Selected AGCO decisions, proposals and settlements |
| Kansspelautoriteit | Full public Kansspelwijzer permission feed | Reviewed Dutch cases and later decisions, including appeals |
| Gambling Commission, Great Britain | Operating licence and activity export | Public business action register and selected historical receipts |
| ACMA, Australia | Listed wagering trading entries and independently matched Northern Territory licences | Selected federal notices, paid penalties and undertakings |
| Malta Gaming Authority | Selected official licence verification seals | Reviewed decisions and annual report statistics |
| Curaçao Gaming Authority | Published online licence roster and selected licence certificates | Published online enforcement register |

## Build and run

From this directory, run:

```sh
python -m pip install -r collectors/requirements.txt
python -m unittest discover -s tests -v
node --test tests/*.test.mjs
python scripts/build.py
python -m http.server 8000 --directory dist
```

Open [the local explorer](http://localhost:8000/). To run the desktop and phone checks, install `tests/browser-requirements.txt`, run `python -m playwright install chromium`, and then `python tests/browser_smoke.py`. The offline build uses the included source snapshots. To perform real source downloads, run `python scripts/refresh.py`, inspect `sources/check.json`, and rebuild.

## Expand or customize

Regulator IDs live in `config/regulators.json`. Add the source definition, reviewed receipts and importer together. Use the exact legal name in each underlying document. Keep publication, observation, decision, effective and expiry dates separate. Store confirmed name variations with independent official receipts in `sources/identities.json`. Add a corroborated jurisdiction pair to `config/foreign-matches.json` with evidence from both authorities. Business names in search results are navigation aids.

Set `eligible` explicitly on an action after verifying its outcome. Reuse its `case_id` across all stages of a proceeding. Set `foreign_penalty` only on qualifying sanctions. Give a current licence observation its `date_basis`, any earlier official `status_as_of`, and its activity/scope. Supplier-only licences are excluded from an operating-licence finding. Include start and end dates for measured intervals only when the source supports both. Keep source-language receipts with every observation.

The build creates static paths under `records/` for the named entities. The child sitemap selects the directory, authority profiles and profiles with enforcement or cross-register evidence. Filter queries and alternate spellings use the same profile. The hub's root sitemap can discover new eligible results after its initial project registration.

Search terms and filters are processed in the browser. The live CoolCode deployment uses the shared aggregate tool counter. See the operator's source record to verify a specific question or report a correction through the site's issue link.

The Friday source refresh checks the official Malta and Tobique warning lists independently. On a failed download or layout change, the previous list retains its original check date. The search runs locally over those saved lists.
