# Shareholding Leaf Taxonomy + Accurate DII

**Branch:** `chore/dii-derive-split` · **Status:** approved, executing (2026-05-26)

## Problem
DII was being derived as MF+Insurance+AIF — a lossy subset that undercounts the true
NSE `InstitutionsDomestic` total by the pension/banks/NBFC/etc. portion (up to −3.6pp on
large-cap financials). Root cause: the flat `shareholding` table only kept 3 of ~9
domestic-institution leaves; the rest sat in `shareholding_breakdown` (recent quarters only)
or were dropped. Also, PSU stocks don't sum to 100 (IOC=80%) because govt/PSU cross-holdings
(`ShareholdingByCompaniesOrBodiesCorporateWhereCentralOrStateGovernmentIsPromoter`) aren't mapped.

## Design — store leaves, derive aggregate (reconciled)
Flat `shareholding` holds a complete, non-overlapping leaf set summing to 100:
`Promoter · FII · [MF Insurance AIF Banks Pension NBFC VC SovereignDomestic OtherDII] · Government · Public · Other`
- DII = derived sum of the bracketed domestic leaves (now complete → == XBRL `InstitutionsDomestic`).
- `OtherDII` = `InstitutionsDomestic − Σleaves` (parse-time remainder) → derived DII == parent exactly, even on old filings.
- `Government` = PSU/govt cross-holding chunk. `Other` = 100 − Σtop-level (safety remainder).
- FII and Public stay single buckets (their leaves remain in `shareholding_breakdown`).
- Verified: Promoter+FII+DII+Government+Public = 100.00–100.01 across PSU/private/bank types.

## Task graph
- Critical path (parser, sequential): #5 key-normalization → #6 capture leaves+Government → #7 reconciled remainders → #8 parser tests
- Parallel after parser: #9 expand DII derivation (DII_COMPONENTS + CTE + alert) ‖ #10 surface new categories → #11 tests+fixtures+fallout
- Converge: #12 backfill universe + reconciliation report

## Goals (success criteria)
- **G1** Σ(top-level) = 100 ± 0.5 for every (symbol, quarter)
- **G2** derived DII == XBRL InstitutionsDomestic ± 0.05, and == old stored DII (backup) ± 0.05 historically
- **G3** IOC/ONGC old quarters reconcile to 100 (today 80/90)
- **G4** `Other` remainder < 2% for ≥95% of stocks
- **G5** full suite green; MF/FII/Promoter analytics unchanged
- **G6** universe re-fetched; new categories present for available quarters

## Key facts from exploration
- XBRL spelling drift across years: `Goverments`→`Governments`, `...CatergoryOne`→`...CategoryOne`,
  `NBFCsRegisteredWithRbi`→`...RBI`, `MutualFundsOrUti`→`...UTI`. Normalize (alias table) so all periods parse.
- Parent keys to exclude from leaf rows: ShareholdingPattern, Indian, Foreign, PublicShareholding,
  Institutions, CentralGovernmentOrStateGovernment(S).
- `InstitutionsDomestic` present every period → authoritative DII for reconciliation.
- Backup DB with pre-migration stored DII: `~/.local/share/flowtracker/flows.db.bak-20260526-165106`.
