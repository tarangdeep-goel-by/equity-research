"""Pydantic models for FMP stable API responses."""

from __future__ import annotations

from pydantic import BaseModel


class CompanyProfile(BaseModel, extra="ignore"):
    symbol: str | None = None
    companyName: str | None = None
    price: float | None = None
    change: float | None = None
    changePercentage: float | None = None
    currency: str | None = None
    exchange: str | None = None
    industry: str | None = None
    sector: str | None = None
    country: str | None = None
    marketCap: float | None = None
    description: str | None = None
    ceo: str | None = None
    fullTimeEmployees: str | None = None
    ipoDate: str | None = None
    website: str | None = None
    beta: float | None = None
    averageVolume: float | None = None
    lastDividend: float | None = None
    range: str | None = None
    isEtf: bool | None = None
    isActivelyTrading: bool | None = None


class ScreenerResult(BaseModel, extra="ignore"):
    symbol: str | None = None
    companyName: str | None = None
    marketCap: float | None = None
    sector: str | None = None
    industry: str | None = None
    beta: float | None = None
    price: float | None = None
    lastAnnualDividend: float | None = None
    volume: int | None = None
    exchange: str | None = None
    country: str | None = None
    isEtf: bool | None = None
    isActivelyTrading: bool | None = None


class RatiosTTM(BaseModel, extra="ignore"):
    priceToEarningsRatio: float | None = None
    priceToEarningsGrowthRatio: float | None = None
    priceToBookRatio: float | None = None
    priceToSalesRatio: float | None = None
    priceToFreeCashFlowRatio: float | None = None
    dividendYield: float | None = None
    dividendYieldPercentage: float | None = None
    returnOnEquity: float | None = None
    returnOnAssets: float | None = None
    grossProfitMargin: float | None = None
    operatingProfitMargin: float | None = None
    netProfitMargin: float | None = None
    debtToEquityRatio: float | None = None
    currentRatio: float | None = None
    interestCoverageRatio: float | None = None
    earningsYield: float | None = None
    freeCashFlowPerShare: float | None = None


class KeyMetricsTTM(BaseModel, extra="ignore"):
    marketCap: float | None = None
    enterpriseValue: float | None = None
    revenuePerShare: float | None = None
    netIncomePerShare: float | None = None
    freeCashFlowPerShare: float | None = None
    bookValuePerShare: float | None = None
    returnOnInvestedCapital: float | None = None
    returnOnEquity: float | None = None
    returnOnAssets: float | None = None
    dividendYield: float | None = None
    evToSales: float | None = None
    evToFreeCashFlow: float | None = None
    evToEBITDA: float | None = None
    debtToEquity: float | None = None
    debtToAssets: float | None = None


class IncomeStatement(BaseModel, extra="ignore"):
    date: str | None = None
    period: str | None = None
    revenue: float | None = None
    costOfRevenue: float | None = None
    grossProfit: float | None = None
    operatingExpenses: float | None = None
    operatingIncome: float | None = None
    netIncome: float | None = None
    eps: float | None = None
    epsDiluted: float | None = None
    ebitda: float | None = None
    weightedAverageShsOut: float | None = None
    weightedAverageShsOutDil: float | None = None


class BalanceSheet(BaseModel, extra="ignore"):
    date: str | None = None
    period: str | None = None
    totalAssets: float | None = None
    totalCurrentAssets: float | None = None
    cashAndCashEquivalents: float | None = None
    totalLiabilities: float | None = None
    totalCurrentLiabilities: float | None = None
    longTermDebt: float | None = None
    totalDebt: float | None = None
    totalStockholdersEquity: float | None = None
    totalEquity: float | None = None
    netDebt: float | None = None
    goodwill: float | None = None
    intangibleAssets: float | None = None
    inventory: float | None = None
    netReceivables: float | None = None


class CashFlowStatement(BaseModel, extra="ignore"):
    date: str | None = None
    period: str | None = None
    operatingCashFlow: float | None = None
    capitalExpenditure: float | None = None
    freeCashFlow: float | None = None
    netCashProvidedByInvestingActivities: float | None = None
    netCashProvidedByFinancingActivities: float | None = None
    netChangeInCash: float | None = None
    commonDividendsPaid: float | None = None
    stockBasedCompensation: float | None = None
    depreciationAndAmortization: float | None = None


class MarketMover(BaseModel, extra="ignore"):
    symbol: str | None = None
    name: str | None = None
    change: float | None = None
    price: float | None = None
    changesPercentage: float | None = None
    exchange: str | None = None
