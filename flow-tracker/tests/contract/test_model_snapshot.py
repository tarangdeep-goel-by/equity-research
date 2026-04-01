"""Contract tests: Pydantic model field regression via syrupy snapshots.

Ensures model field names don't change unexpectedly. Detects accidental
renames or removals of fields that downstream code depends on.
"""

from __future__ import annotations

import pytest


class TestModelFieldsSnapshot:
    def test_all_model_fields_snapshot(self, snapshot):
        """All tracked model field sets must match the recorded snapshot."""
        from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
        from flowtracker.fund_models import (
            AnnualFinancials,
            QuarterlyResult,
            ScreenerRatios,
            ValuationSnapshot,
        )
        from flowtracker.holding_models import ShareholdingRecord, PromoterPledge
        from flowtracker.bhavcopy_models import DailyStockData
        from flowtracker.commodity_models import CommodityPrice, GoldETFNav
        from flowtracker.macro_models import MacroSnapshot
        from flowtracker.insider_models import InsiderTransaction
        from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
        from flowtracker.fmp_models import (
            FMPDcfValue,
            FMPKeyMetrics,
            FMPFinancialGrowth,
            FMPAnalystGrade,
            FMPPriceTarget,
            FMPTechnicalIndicator,
        )
        from flowtracker.portfolio_models import PortfolioHolding
        from flowtracker.alert_models import Alert
        from flowtracker.screener_models import FactorScore, StockScore
        from flowtracker.mf_models import MFMonthlyFlow, MFAUMSummary, MFDailyFlow
        from flowtracker.mfportfolio_models import MFSchemeHolding

        models = {
            "DailyFlow": sorted(DailyFlow.model_fields.keys()),
            "DailyFlowPair": sorted(DailyFlowPair.model_fields.keys()),
            "StreakInfo": sorted(StreakInfo.model_fields.keys()),
            "QuarterlyResult": sorted(QuarterlyResult.model_fields.keys()),
            "ScreenerRatios": sorted(ScreenerRatios.model_fields.keys()),
            "ValuationSnapshot": sorted(ValuationSnapshot.model_fields.keys()),
            "AnnualFinancials": sorted(AnnualFinancials.model_fields.keys()),
            "ShareholdingRecord": sorted(ShareholdingRecord.model_fields.keys()),
            "PromoterPledge": sorted(PromoterPledge.model_fields.keys()),
            "DailyStockData": sorted(DailyStockData.model_fields.keys()),
            "CommodityPrice": sorted(CommodityPrice.model_fields.keys()),
            "GoldETFNav": sorted(GoldETFNav.model_fields.keys()),
            "MacroSnapshot": sorted(MacroSnapshot.model_fields.keys()),
            "InsiderTransaction": sorted(InsiderTransaction.model_fields.keys()),
            "ConsensusEstimate": sorted(ConsensusEstimate.model_fields.keys()),
            "EarningsSurprise": sorted(EarningsSurprise.model_fields.keys()),
            "FMPDcfValue": sorted(FMPDcfValue.model_fields.keys()),
            "FMPKeyMetrics": sorted(FMPKeyMetrics.model_fields.keys()),
            "FMPFinancialGrowth": sorted(FMPFinancialGrowth.model_fields.keys()),
            "FMPAnalystGrade": sorted(FMPAnalystGrade.model_fields.keys()),
            "FMPPriceTarget": sorted(FMPPriceTarget.model_fields.keys()),
            "FMPTechnicalIndicator": sorted(FMPTechnicalIndicator.model_fields.keys()),
            "PortfolioHolding": sorted(PortfolioHolding.model_fields.keys()),
            "Alert": sorted(Alert.model_fields.keys()),
            "FactorScore": sorted(FactorScore.model_fields.keys()),
            "StockScore": sorted(StockScore.model_fields.keys()),
            "MFMonthlyFlow": sorted(MFMonthlyFlow.model_fields.keys()),
            "MFAUMSummary": sorted(MFAUMSummary.model_fields.keys()),
            "MFDailyFlow": sorted(MFDailyFlow.model_fields.keys()),
            "MFSchemeHolding": sorted(MFSchemeHolding.model_fields.keys()),
        }
        assert models == snapshot

    def test_model_count_regression(self):
        """Sanity check: we track a reasonable number of models."""
        from flowtracker import models, fund_models, fmp_models, alert_models
        from pydantic import BaseModel

        # Count BaseModel subclasses in key modules
        count = 0
        for mod in (models, fund_models, fmp_models, alert_models):
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                    count += 1
        assert count >= 10, f"Expected at least 10 tracked models, got {count}"
