# Great Britain and Netherlands collectors

Run from the repository root with Python and `lxml` installed. The default observation date is today in UTC. The optional `--cache` stores the exact source bytes fetched during a run. Use a separate cache directory for each observation date. Use `--as-of YYYY-MM-DD` only to replay an edition using inputs saved on that same date.

```sh
python collectors/ukgc.py --output sources/ukgc.json
python collectors/ksa.py --output sources/ksa.json
```

Both commands write JSON to stdout when no output path is given. An empty response, parse failure or failed receipt check prevents replacement of the previous output.

## Gambling Commission

The collector reads the businesses and licence-activities CSVs linked from the [operator downloads](https://www.gamblingcommission.gov.uk/public-register/businesses/download), then opens each decision in the [full regulatory actions index](https://www.gamblingcommission.gov.uk/public-register/regulatory-actions/full). It identifies business operating licences separately from personal employee licences. Operating accounts include companies, charities, clubs, partnerships and sole traders. Multiple activities on one licence, with the same status, type and dates, appear together. An active observation carries the collection date and its separately reported activity start date. Historical activity dates remain available.

An indexed decision's case key is its Commission decision ID. Selected historical regulator releases are listed in `ukgc-reviewed.json` with receipt URLs, individual operator amounts and publication dates. A regulatory settlement can qualify as a separate outcome in the operator history. Its payment is distinct from an imposed fine. The financial-penalty flag requires the recorded sanction to include a financial penalty. The parser records an amount when the decision explicitly assigns an unambiguous penalty, including an expressly reduced final amount. It leaves ambiguous figures blank. A newly encountered reference to appeal in an indexed operating decision triggers review before publication.

The 365-day calculation uses the exact account IDs with an active activity on the observation date. The numerator counts distinct members of that group with a dated decision in the retained full register during that interval. The separate action count counts distinct decision/account pairs within that same group and interval. The two figures can differ. This is a measure of published decisions among today's active accounts. A population-wide annual enforcement rate would also require historical entrants, departures and case coverage.

The more specific `operator_licence` flag requires a listed consumer-facing permission for betting, casino, bingo, society lottery or a public gaming centre on the same licence row. Software, equipment supply, hosting and external lottery management alone cannot establish that the business accepts players. Unrecognised activity types default to false. The all-account denominator above still includes both business-to-business and consumer-facing operating accounts.

## Kansspelautoriteit

The official [Kansspelwijzer directory](https://kansspelautoriteit.nl/kansspelwijzer) links the [provider feed](https://kansspelautoriteit.nl/api/gambling-providers). The collector takes every provider row, retaining the holder, public record ID, licence number, activity, brands, term and detail link. The observation date records a licence's appearance in that directory. A row is active when the observation falls inside its published term, treating its closing date as exclusive.

`ksa-reviewed.json` contains a named selection of [regulator decisions](https://kansspelautoriteit.nl/sanctiebesluiten) and court outcomes. Multiple stages share a case ID. Each public receipt has a SHA-256 digest of the whitespace-normalized text in its main article. A source change stops publication until the operative amount, objections and appeal disposition have been checked, the affected rows updated and the digest renewed. For an additional case, include its public decision page in `receipts`, then add each dated stage to `actions`. When the effective status is uncertain, preserve the receipt and mark the stage ineligible for derived findings. The selection cannot supply a rate for the Netherlands register.

For example, the [Dutch Council of State ruling on RLC 1 B.V. and RLC 2 B.V.](https://www.raadvanstate.nl/uitspraken/@162141/202406508-1-a3/) records the two 17 February 2020 revocations, sets aside the 2022 objection decision on 25 November 2026, and directs KSA to decide again. The original decision and the remand are visible as parts of the same docket. The ruling supplies no confirmed start date for a licence-removal interval.

For the consumer-operator comparison, a listed online game, lottery, traditional betting or casino permission qualifies. Machine-operation permissions can be held by an equipment owner who rents machines to a separate venue. Those permissions and entries without a stated activity remain in the register, with the consumer-operator flag false. See the [KSA explanation of local venue permits](https://kansspelautoriteit.nl/aanwezigheidsvergunning).
