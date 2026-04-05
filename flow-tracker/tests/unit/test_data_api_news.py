"""Tests for ResearchDataAPI.get_stock_news — Google News RSS + yfinance."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from flowtracker.research.data_api import ResearchDataAPI


# --- Sample fixtures ---

GOOGLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Infosys Acquires Optimum Healthcare IT for $465M</title>
      <link>https://example.com/article1</link>
      <pubDate>Sat, 01 Mar 2026 10:00:00 GMT</pubDate>
      <source url="https://mint.com">Mint</source>
    </item>
    <item>
      <title>SEBI Imposes Penalty on Infosys Director for Insider Trading</title>
      <link>https://example.com/article2</link>
      <pubDate>Thu, 20 Feb 2026 08:30:00 GMT</pubDate>
      <source url="https://et.com">Economic Times</source>
    </item>
    <item>
      <title>Stocks to Watch Today: Infosys, TCS, Wipro in Focus</title>
      <link>https://example.com/article3</link>
      <pubDate>Wed, 19 Feb 2026 06:00:00 GMT</pubDate>
      <source url="https://zeebiz.com">Zee Business</source>
    </item>
    <item>
      <title>5 Stocks to Buy for Long Term Including Infosys</title>
      <link>https://example.com/article4</link>
      <pubDate>Tue, 18 Feb 2026 07:00:00 GMT</pubDate>
      <source url="https://moneycontrol.com">Moneycontrol</source>
    </item>
    <item>
      <title>Infosys Board Approves Special Dividend of Rs 8 Per Share</title>
      <link>https://example.com/article5</link>
      <pubDate>Mon, 17 Feb 2026 09:00:00 GMT</pubDate>
      <source url="https://bstandard.com">Business Standard</source>
    </item>
  </channel>
</rss>"""

YFINANCE_NEWS = [
    {
        "content": {
            "title": "Infosys Acquires Optimum Healthcare IT for Up to $465M",
            "summary": "Infosys announced acquisition of Optimum Healthcare IT...",
            "pubDate": "2026-03-01T11:41:18Z",
            "provider": {"displayName": "Insider Monkey"},
            "canonicalUrl": {"url": "https://yahoo.com/article1"},
        }
    },
    {
        "content": {
            "title": "Infosys Q3 Results: Revenue Up 5% YoY",
            "summary": "Infosys reported strong Q3 numbers...",
            "pubDate": "2026-02-15T09:00:00Z",
            "provider": {"displayName": "Yahoo Finance"},
            "canonicalUrl": {"url": "https://yahoo.com/article2"},
        }
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_response(content: str) -> MagicMock:
    """Create a mock httpx response with given XML content."""
    resp = MagicMock()
    resp.content = content.encode()
    resp.raise_for_status = MagicMock()
    return resp


def _mock_yfinance_ticker(news: list[dict]) -> MagicMock:
    """Create a mock yfinance.Ticker with given news."""
    ticker_cls = MagicMock()
    ticker_instance = MagicMock()
    ticker_instance.news = news
    ticker_cls.return_value = ticker_instance
    return ticker_cls


# ---------------------------------------------------------------------------
# Tests: get_stock_news end-to-end
# ---------------------------------------------------------------------------

_COMMON_PATCHES = [
    patch("flowtracker.research.data_api.FlowStore"),
    patch.object(
        ResearchDataAPI, "get_company_info",
        return_value={"symbol": "INFY", "company_name": "Infosys Ltd", "industry": "IT"},
    ),
]


@pytest.fixture
def news_api():
    """ResearchDataAPI with FlowStore and get_company_info mocked out."""
    with _COMMON_PATCHES[0], _COMMON_PATCHES[1]:
        api = ResearchDataAPI()
        yield api
        api.close()


class TestGetStockNews:
    """Integration-style tests calling get_stock_news with mocked HTTP."""

    def test_returns_structured_list(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", return_value=_mock_httpx_response(GOOGLE_RSS_XML)),
            patch("yfinance.Ticker", _mock_yfinance_ticker(YFINANCE_NEWS)),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        assert isinstance(results, list)
        assert len(results) > 0
        expected_keys = {"title", "source", "date", "url", "summary", "provider"}
        for item in results:
            assert expected_keys.issubset(item.keys()), f"Missing keys in {item}"
            assert item["provider"] in ("google_rss", "yfinance")

    def test_noise_filtering(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", return_value=_mock_httpx_response(GOOGLE_RSS_XML)),
            patch("yfinance.Ticker", _mock_yfinance_ticker([])),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        titles = [r["title"] for r in results]

        # Noise should be filtered out
        assert "Stocks to Watch Today: Infosys, TCS, Wipro in Focus" not in titles
        assert "5 Stocks to Buy for Long Term Including Infosys" not in titles

        # Real news should be kept
        assert "Infosys Acquires Optimum Healthcare IT for $465M" in titles
        assert "SEBI Imposes Penalty on Infosys Director for Insider Trading" in titles
        assert "Infosys Board Approves Special Dividend of Rs 8 Per Share" in titles

    def test_deduplication(self, news_api):
        """Google RSS and yfinance both have the acquisition article — dedup to 1."""
        with (
            patch("flowtracker.research.data_api.httpx.get", return_value=_mock_httpx_response(GOOGLE_RSS_XML)),
            patch("yfinance.Ticker", _mock_yfinance_ticker(YFINANCE_NEWS)),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        acquisition_articles = [
            r for r in results
            if "acquires" in r["title"].lower() and "optimum" in r["title"].lower()
        ]
        assert len(acquisition_articles) == 1, (
            f"Expected 1 acquisition article after dedup, got {len(acquisition_articles)}: "
            f"{[a['title'] for a in acquisition_articles]}"
        )

    def test_date_sorting(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", return_value=_mock_httpx_response(GOOGLE_RSS_XML)),
            patch("yfinance.Ticker", _mock_yfinance_ticker(YFINANCE_NEWS)),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        dates = [r["date"] for r in results if r.get("date")]
        assert dates == sorted(dates, reverse=True), "Results should be sorted by date descending"

    def test_graceful_on_google_failure(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", side_effect=Exception("Connection refused")),
            patch("yfinance.Ticker", _mock_yfinance_ticker(YFINANCE_NEWS)),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        assert isinstance(results, list)
        assert len(results) > 0
        # All results should come from yfinance
        assert all(r["provider"] == "yfinance" for r in results)

    def test_graceful_on_yfinance_failure(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", return_value=_mock_httpx_response(GOOGLE_RSS_XML)),
            patch("yfinance.Ticker", side_effect=Exception("yfinance error")),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        assert isinstance(results, list)
        assert len(results) > 0
        # All results should come from google_rss
        assert all(r["provider"] == "google_rss" for r in results)

    def test_both_fail_returns_empty(self, news_api):
        with (
            patch("flowtracker.research.data_api.httpx.get", side_effect=Exception("Connection refused")),
            patch("yfinance.Ticker", side_effect=Exception("yfinance error")),
        ):
            results = news_api.get_stock_news("INFY", days=90)

        assert isinstance(results, list)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: _is_news_noise (static / class-level)
# ---------------------------------------------------------------------------

class TestIsNewsNoise:
    """Direct tests for the _is_news_noise filter method."""

    @pytest.fixture
    def api(self):
        with _COMMON_PATCHES[0], _COMMON_PATCHES[1]:
            a = ResearchDataAPI()
            yield a
            a.close()

    @pytest.mark.parametrize("title", [
        "Stocks to Watch Today: TCS, Infosys, Wipro",
        "Top 5 Stocks to Buy for Long Term",
        "Infosys Share Price Today: Trading at Rs 1800",
        "Best Stocks for 2026 Portfolio Picks",
        "Stock Market Today: Nifty Closes Higher",
        "Multibagger Alert: This IT Stock Could Double",
        "Penny Stocks Under Rs 50 to Watch",
        "3 Stocks for Short Term Target 20% Gain",
        "Top Picks for Intraday Trading",
        "Infosys, TCS Among Stocks in Focus Today",
        "5 Shares to Buy This Week",
    ])
    def test_noise_detected(self, api, title):
        assert api._is_news_noise(title), f"Expected noise: {title!r}"

    @pytest.mark.parametrize("title", [
        "Infosys Acquires Optimum Healthcare IT for $465M",
        "SEBI Imposes Penalty on Infosys Director for Insider Trading",
        "Infosys Board Approves Special Dividend of Rs 8 Per Share",
        "Infosys Q3 Results: Revenue Up 5% YoY, Margin Expansion",
        "Infosys CEO Salil Parekh Resigns, Successor Named",
        "RBI Keeps Repo Rate Unchanged at 6.5%",
    ])
    def test_real_news_passes(self, api, title):
        assert not api._is_news_noise(title), f"False positive noise: {title!r}"


# ---------------------------------------------------------------------------
# Tests: _deduplicate_news (static method)
# ---------------------------------------------------------------------------

class TestDeduplicateNews:
    """Direct tests for the _deduplicate_news static method."""

    def test_removes_near_duplicates(self):
        articles = [
            {"title": "Infosys Acquires Optimum Healthcare IT for $465M", "provider": "google_rss"},
            {"title": "Infosys Acquires Optimum Healthcare IT for Up to $465M", "provider": "yfinance"},
        ]
        result = ResearchDataAPI._deduplicate_news(articles)
        assert len(result) == 1
        # First one wins
        assert result[0]["provider"] == "google_rss"

    def test_keeps_distinct_articles(self):
        articles = [
            {"title": "Infosys Acquires Optimum Healthcare IT for $465M", "provider": "google_rss"},
            {"title": "SEBI Imposes Penalty on Infosys Director", "provider": "google_rss"},
            {"title": "Infosys Q3 Results: Revenue Up 5% YoY", "provider": "yfinance"},
        ]
        result = ResearchDataAPI._deduplicate_news(articles)
        assert len(result) == 3

    def test_empty_input(self):
        assert ResearchDataAPI._deduplicate_news([]) == []

    def test_single_article(self):
        articles = [{"title": "One Article", "provider": "google_rss"}]
        result = ResearchDataAPI._deduplicate_news(articles)
        assert len(result) == 1

    def test_empty_title_skipped(self):
        articles = [
            {"title": "", "provider": "google_rss"},
            {"title": "Real Article Here", "provider": "google_rss"},
        ]
        result = ResearchDataAPI._deduplicate_news(articles)
        assert len(result) == 1
        assert result[0]["title"] == "Real Article Here"
