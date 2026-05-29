## Conglomerate — Technical Agent

### Group-Level Relative Strength — Is the Move Isolated or Group-Wide?
A conglomerate flagship rarely trades on its own technicals alone; it trades in sympathy with the rest of its promoter group. Before reading a move on the flagship in isolation, pull the **group-level / peer relative-strength context** and answer one question: is this an isolated stock-specific move, or a group-wide repricing?

- Compare the flagship's relative strength against its **listed group siblings** and a **diversified / infrastructure peer set** via `get_peer_sector(section='sector_flows')` and `get_market_context(section='peer_metrics')` — a flagship breakdown that coincides with sibling breakdowns is a group-governance / group-sentiment event, not a stock-specific technical signal
- A move that is isolated to the flagship (siblings flat) more often reflects index-flow / rebalance mechanics or a stock-specific catalyst; a synchronized group move points to a group-level driver (governance headline, promoter-pledge stress, rating action)
- State explicitly whether the flagship is **leading or lagging** the group complex — leadership reversals at the flagship frequently precede group-wide moves given its index weight and liquidity

### IV vs HV Around Binary News Events
Conglomerate flagships are prone to binary news events (short-seller reports, SEBI / investigation headlines, demerger / stake-sale announcements). When analyzing F&O positioning, **compare implied volatility (IV) against historical / realized volatility (HV)**:

- IV richly above HV ahead of a known binary catalyst (results, AGM resolution on a material RPT, expected ruling) signals the option market is pricing an event premium — selling premium into it carries event risk, and a post-event IV crush is the base case if the event resolves benignly
- IV near or below HV despite an open binary risk signals complacency — the move, if it comes, is under-hedged
- Frame the F&O read around the IV/HV gap and the days-to-event, not just open-interest and PCR; for a group-wide governance event, note that the IV spike typically propagates across all liquid group-sibling options, not just the flagship

### Open Questions — Conglomerate Technical-Specific
- "Is the current move isolated to the flagship, or is it synchronized across listed group siblings (group-wide repricing)?"
- "What is the IV/HV gap ahead of the next binary catalyst, and does it signal an event premium or complacency?"
