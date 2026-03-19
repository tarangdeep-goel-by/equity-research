"""Pydantic models for fundamentals data."""

from __future__ import annotations

from pydantic import BaseModel


class QuarterlyResult(BaseModel):
    symbol: str
    quarter_end: str
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    eps: float | None = None
    eps_diluted: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None


class ValuationSnapshot(BaseModel):
    symbol: str
    date: str
    price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    roa: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    free_cash_flow: float | None = None


class LiveSnapshot(BaseModel):
    """Live data — never stored, fetched on demand."""
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    price: float | None = None
    market_cap: float | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    roa: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    free_cash_flow: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None


class AnnualEPS(BaseModel):
    """Annual EPS from Screener.in P&L — used for historical P/E computation."""
    symbol: str
    fiscal_year_end: str  # "2025-03-31"
    eps: float
    revenue: float | None = None
    net_income: float | None = None


class AnnualFinancials(BaseModel):
    """Full annual financials from Screener.in — P&L + Balance Sheet + Cash Flow."""
    symbol: str
    fiscal_year_end: str  # "2025-03-31"

    # P&L
    revenue: float | None = None
    employee_cost: float | None = None
    other_income: float | None = None
    depreciation: float | None = None
    interest: float | None = None
    profit_before_tax: float | None = None
    tax: float | None = None
    net_income: float | None = None
    eps: float | None = None
    dividend_amount: float | None = None

    # Balance Sheet
    equity_capital: float | None = None
    reserves: float | None = None
    borrowings: float | None = None
    other_liabilities: float | None = None
    total_assets: float | None = None
    net_block: float | None = None
    cwip: float | None = None
    investments: float | None = None
    other_assets: float | None = None
    receivables: float | None = None
    inventory: float | None = None
    cash_and_bank: float | None = None
    num_shares: float | None = None  # actual count

    # Cash Flow
    cfo: float | None = None  # cash from operations
    cfi: float | None = None  # cash from investing
    cff: float | None = None  # cash from financing
    net_cash_flow: float | None = None

    # Price (for historical P/E context)
    price: float | None = None

    # Derived (computed, not stored directly)
    @property
    def total_equity(self) -> float | None:
        if self.equity_capital is not None and self.reserves is not None:
            return self.equity_capital + self.reserves
        return None

    @property
    def roce(self) -> float | None:
        """ROCE = EBIT / Capital Employed. Capital Employed = Total Assets - Current Liabilities (approx: other_liabilities)."""
        if self.profit_before_tax is not None and self.interest is not None and self.total_assets is not None and self.other_liabilities is not None:
            ebit = self.profit_before_tax + self.interest
            capital_employed = self.total_assets - self.other_liabilities
            if capital_employed > 0:
                return ebit / capital_employed
        return None

    @property
    def roe(self) -> float | None:
        """ROE = Net Income / Total Equity."""
        equity = self.total_equity
        if self.net_income is not None and equity and equity > 0:
            return self.net_income / equity
        return None

    @property
    def debt_to_equity(self) -> float | None:
        equity = self.total_equity
        if self.borrowings is not None and equity and equity > 0:
            return self.borrowings / equity
        return None

    @property
    def interest_coverage(self) -> float | None:
        """Interest Coverage = EBIT / Interest."""
        if self.profit_before_tax is not None and self.interest is not None and self.interest > 0:
            ebit = self.profit_before_tax + self.interest
            return ebit / self.interest
        return None

    @property
    def cfo_to_net_income(self) -> float | None:
        """Cash conversion ratio = CFO / Net Income."""
        if self.cfo is not None and self.net_income and self.net_income > 0:
            return self.cfo / self.net_income
        return None

    @property
    def fcf(self) -> float | None:
        """Approximate FCF = CFO + CFI (investing is negative)."""
        if self.cfo is not None and self.cfi is not None:
            return self.cfo + self.cfi
        return None

    @property
    def debtor_days(self) -> float | None:
        """Debtor Days = Receivables / (Revenue / 365)."""
        if self.receivables is not None and self.revenue and self.revenue > 0:
            return self.receivables / (self.revenue / 365)
        return None

    @property
    def capex_pct_cfo(self) -> float | None:
        """Capex as % of CFO. Uses -CFI as proxy for capex (includes investments)."""
        if self.cfo is not None and self.cfi is not None and self.cfo > 0:
            return -self.cfi / self.cfo
        return None


class ValuationBand(BaseModel):
    """Computed from stored snapshots — not stored itself."""
    symbol: str
    metric: str
    min_val: float
    max_val: float
    median_val: float
    current_val: float
    percentile: float
    num_observations: int
    period_start: str
    period_end: str
