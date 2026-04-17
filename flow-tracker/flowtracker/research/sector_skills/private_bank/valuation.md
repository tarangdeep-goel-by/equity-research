## Private Bank — Valuation Agent

This file inherits the full BFSI valuation framing (see `bfsi/valuation.md` when merged — PR #20) on sub-type routing, P/ABV with Net NPA deduction, SOTP mechanics, Gordon-framework justified P/B with `g` carried through, and the "what fails" list for deposit-taking entities. Do not duplicate generic BFSI content. This file sharpens the private-bank specifics: primary-multiple calibration, HDFC-merger historical-band adjustments, explicit EV-metric exclusion from the snapshot, and SOTP-component sector multiples for the conglomerate large private banks.

### Primary Multiple — P/ABV, Cross-Checked by Justified P/B
The primary valuation multiple for a private bank is **Price-to-Adjusted-Book-Value**: `ABV per share = BVPS − (Net NPA ÷ shares outstanding)`; `P/ABV = CMP ÷ ABV per share`. For large private banks running NNPA 0.3-0.8%, the ABV deduction is 0.5-2% of BVPS; for mid-caps running NNPA 1.5-2.5%, the deduction is 3-5% of BVPS and materially changes the re-rating narrative. Always show the deduction explicitly — quoting P/B on reported BVPS without the Net NPA strip is the skip-step flagged in prior valuation evals.

Route the arithmetic through `calculate` with `shares_out`, `bvps`, and `net_npa_per_share` as named inputs. Compare current P/ABV to the 5Y band via `get_valuation(section='band', metric='pb')`, falling back to `get_chart_data(chart_type='pbv')` for deep-history context.

The cross-check is **P/B-ROE justified multiple** via the Gordon framework (next section).

### Justified P/B Math Must Carry `g`
The Gordon-framework justified P/B for a mature private-bank franchise is:

```
Justified P/B = (ROE − g) / (CoE − g)
```

where `g` is the sustainable long-run book-value growth rate. **Never drop `g` to zero** — that collapses the formula to ROE/CoE and produces a 50-70% under-estimate of fair P/B. Indian private-bank calibrations:

- Top-tier private bank (HDFCBANK, ICICIBANK): ROE 16-17%, CoE 12%, g 11% → Justified P/B = (16−11)/(12−11) = 5.0× (or with g=10% → 3.0×). Sensitivity to `g` is load-bearing — state the assumption.
- Mid-tier private bank (AXISBANK, KOTAKBANK): ROE 14-16%, CoE 12%, g 10% → Justified P/B = (14−10)/(12−10) = 2.0× to (16−10)/(12−10) = 3.0×.
- Mid-cap niche private bank (FEDERALBNK, CITYUNIONBANK, CSBBANK): ROE 12-14%, CoE 12-13%, g 9-10% → Justified P/B = (12−9)/(13−9) = 0.75× to (14−10)/(12−10) = 2.0×.
- IDFCFIRSTB (post-merger ROE ramping): ROE 10-12% trailing, forward 13-15%; route both trailing and forward-justified multiple separately.

Indian private-bank ROE typically sits 15-18%, CoE 12-13%, g 10-14% — the justified-range is therefore 1.8-3.5× on central assumptions. A 1 pp change in `g` moves the justified multiple by 30-50%, so the growth assumption is as load-bearing as the ROE/CoE inputs. Route `calculate` with `ROE`, `CoE`, and `g` as named inputs; pull CoE from `get_market_context(section='macro')` or the WACC helper.

### Strip EV-Based Metrics from Snapshot and Framework
EV/EBITDA, EV/Revenue, and EV/EBIT are **structurally invalid** for deposit-taking entities — deposits are raw material, not capital structure, so enterprise value is a meaningless construct. If the tools return these multiples in `get_fundamentals` or `get_valuation` output, caveat and skip. **Do not display them in the snapshot table of the report** — their presence implies they are informative, which is misleading for private-bank analysis. If a reader requires the absolute-number for reference, state them once in the Open Questions section with the explicit caveat "EV metrics are not applicable to deposit-taking entities — shown here only for completeness".

### HDFC-Merger Historical-Band Adjustments
For **HDFCBANK** specifically, the HDFC Ltd reverse-merger (effective 1 July 2023, FY24-Q1) issued approximately 37% new shares to HDFC Ltd shareholders and materially enlarged the book value, advances, borrowings, and loan-book mix. The pre-merger and post-merger per-share series are not directly comparable:

- Historical EPS, DPS, and BVPS per-share for pre-FY24-Q1 periods are on the pre-merger share count (~5.55 bn shares).
- Post-merger share count is approximately 7.6 bn — roughly 37% dilution on the per-share denominator.
- Historical-band comparisons of P/B or P/E using pre-merger per-share series and post-merger CMP produce inverted conclusions (looks much cheaper than reality).

Adjustment approach:
1. **Preferred** — use restated-historical-per-share series (HDFCBANK investor-relations discloses adjusted BVPS/EPS on post-merger share count for historical periods). Source via `get_fundamentals(section='annual_financials')` confirming restatement, or `get_company_context(section='concall_insights')` where management references the adjusted series.
2. **Fallback** — compute P/ABV on current-shares basis with an explicit merger-break caveat: state that 5Y/10Y P/B median is not directly comparable and cite the 2Y post-merger band as the cleaner reference. Route the restatement factor through `calculate` with `pre_merger_shares`, `new_shares_issued`, and `post_merger_shares` as named inputs; apply the factor to historical per-share series before computing banded statistics.

For HDFCBANK, the merger-break rule also applies to a lesser extent to CASA ratio (the merger brought in HDFC Ltd wholesale borrowings re-classifying as bank deposits — adjust the CASA base before citing pre-vs-post median).

### SOTP for Conglomerate Private Banks
For HDFCBANK, ICICIBANK, KOTAKBANK, and AXISBANK, SOTP is often the re-rating lever; empty-SOTP citations were flagged in prior valuation evals. Build the stack:

1. Call `get_valuation(section='sotp')` for the tool-computed view; cross-check against manual construction.
2. For each **listed subsidiary**: market cap × parent's stake % → per-share contribution to parent.
3. For each **unlisted subsidiary**, apply a sector multiple:
   - Listed AMC subsidiary (HDFC AMC, ICICI Pru AMC): 3-5% of AUM (premier names toward 4-5%).
   - Unlisted AMC (Kotak AMC, Axis AMC): 3-4% of AUM depending on equity-AUM share; apply a discount vs the listed peers given illiquidity.
   - Listed life insurer (HDFC Life, ICICI Pru Life): 1.5-3× embedded value (growth × VNB-margin premium) — cross-check via `get_peer_sector(section='benchmarks')`.
   - Unlisted life insurer (Kotak Life, Max Life 20% stake via AXISBANK): 1.5-2.5× VNB-based implied EV.
   - Listed general insurer (ICICI Lombard): 1.0-2.5× annual Gross Direct Premium Income.
   - Unlisted general insurer (HDFC ERGO): 1.0-2.0× GDPI depending on combined-ratio trajectory.
   - Unlisted NBFC (HDB Financial Services — IPO-bound FY26): 1.0-2.5× book, with the IPO-implied valuation as the cleanest anchor once disclosed.
   - Broking arm (ICICI Securities post-delisting, Kotak Securities unlisted): 10-15× PE on through-cycle active-client monetisation.
4. Apply **20-25% holding-company discount** to the aggregate sub-value.
5. Back out implied P/ABV on the **standalone** (ex-SOTP) bank: `standalone_bank_implied_value = current_mcap − subsidiary_SOTP_value`; compute standalone P/ABV using **standalone BVPS** (never consolidated).

### Peer-Premium / Discount Decomposition
If the bank trades at a P/ABV premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose into at most five drivers:

- **NIM spread** vs peer — 30-100 bps of sustained NIM advantage justifies 10-20% premium.
- **ROA delta** — 20-50 bps of ROA advantage justifies 15-25% premium.
- **Asset-quality delta** — GNPA / NNPA / credit-cost below peer median justifies 10-15% premium.
- **Liability franchise** — CASA 500-1000 bps above peer is a structural premium driver worth 15-25% in the band.
- **Fee-income ratio** — 500-1000 bps above peer fee-income ratio signals deeper cross-sell moat, worth 10-15%.

If (a) through (e) together do not account for more than half the observed premium, the multiple leans on re-rating rather than earnings-quality; flag as mean-reversion risk.

### What Fails for Private Banks — Name Explicitly
- **EV/EBITDA** — deposits are raw material, not capital structure; adding back interest expense destroys the signal.
- **EV/Revenue** — NII + fee income is already the "margin-adjusted top line"; scaling by EV double-counts.
- **DCF / FCFE** — CFO oscillates with deposit and loan flows, not earnings quality.
- **PE on a provisioning-tailwind year** — a bank with a large credit-cost recovery looks optically cheap on trailing PE while ROA is peaking; always normalise.
- **PE on a treasury-gains-heavy year** — bond-rally year pumps other income; normalise to through-cycle treasury.
- **Simple P/B without Net NPA deduction** — overstates the book value actually backing the equity claim.

### Data-shape Fallback for Asset Quality
When `get_quality_scores(section='bfsi')` returns missing GNPA, NNPA, PCR, CASA, or capital ratios, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_fundamentals(section='quarterly_financials')` for the line-items; (3) `get_company_context(section='filings')` for the most recent BSE disclosure. Cite the source quarter for every extracted number. Without Net NPA, P/ABV cannot be computed rigorously — escalate as an Open Question rather than default to reported P/B.

### Open Questions — Private-Bank Valuation-Specific
- "What Net NPA per share was used to compute ABV, and from which quarter's disclosure?"
- "For HDFCBANK: was the historical P/B band restated for the FY24-Q1 merger share issuance, or is the 5Y median still carrying pre-merger per-share inputs?"
- "For unlisted subsidiaries (HDB Financial Services, Kotak Life, Axis AMC, HDFC ERGO): what sector multiple was applied and what is the sensitivity of SOTP to that assumption?"
- "Does the current P/ABV premium to sector median reconcile with the NIM + ROA + asset-quality + CASA + fee-income decomposition, or is there a residual multiple gap that the bull-case is relying on?"
- "What `g` was carried through the justified-P/B math, and what is the sensitivity of the justified multiple to a 1-pp change in `g`?"
