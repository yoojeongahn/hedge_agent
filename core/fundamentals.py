# core/fundamentals.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class QuarterlyPoint:
    label: str          # "2024Q3", "2024Q2", ...
    revenue: float | None
    operating_profit: float | None


@dataclass
class FundamentalsData:
    code: str
    name: str
    market: str
    per: float | None
    pbr: float | None
    roe: float | None               # %
    debt_ratio: float | None        # %
    operating_margin: float | None  # %
    revenue_growth_yoy: float | None  # %
    quarterly: list[QuarterlyPoint] = field(default_factory=list)


def fetch_fundamentals(code: str, name: str, market: str) -> FundamentalsData:
    if market == "US":
        return _fetch_us(code, name)
    return _fetch_kr(code, name)


def _fetch_us(code: str, name: str) -> FundamentalsData:
    try:
        ticker = yf.Ticker(code)
        info = ticker.info
    except Exception as e:
        logger.warning("US 기본정보 조회 실패 %s: %s", code, e)
        info = {}

    def _pct(val: float | None) -> float | None:
        return round(val * 100, 2) if val is not None else None

    quarterly = []
    try:
        qf = ticker.quarterly_financials
        if not qf.empty:
            for col in list(qf.columns)[:4]:
                label = f"{col.year}Q{(col.month - 1) // 3 + 1}"
                try:
                    rev_row = [r for r in qf.index if "revenue" in str(r).lower() or "total rev" in str(r).lower()]
                    op_row = [r for r in qf.index if "operating" in str(r).lower() and "income" in str(r).lower()]
                    rev = float(qf.loc[rev_row[0], col]) / 1e8 if rev_row else None
                    op = float(qf.loc[op_row[0], col]) / 1e8 if op_row else None
                    quarterly.append(QuarterlyPoint(label=label, revenue=rev, operating_profit=op))
                except Exception:
                    quarterly.append(QuarterlyPoint(label=label, revenue=None, operating_profit=None))
    except Exception as e:
        logger.warning("US 분기 데이터 조회 실패 %s: %s", code, e)

    return FundamentalsData(
        code=code, name=name, market="US",
        per=info.get("trailingPE"),
        pbr=info.get("priceToBook"),
        roe=_pct(info.get("returnOnEquity")),
        debt_ratio=info.get("debtToEquity"),
        operating_margin=_pct(info.get("operatingMargins")),
        revenue_growth_yoy=_pct(info.get("revenueGrowth")),
        quarterly=quarterly,
    )


def _fetch_kr(code: str, name: str) -> FundamentalsData:
    """KR 재무: pykrx(PER/PBR) + dart-fss(ROE/부채비율/분기). dart-fss 실패 시 부분 반환."""
    per, pbr = _fetch_kr_ratios(code)
    roe, debt_ratio, op_margin, rev_growth, quarterly = _fetch_kr_dart(code)

    return FundamentalsData(
        code=code, name=name, market="KR",
        per=per, pbr=pbr,
        roe=roe, debt_ratio=debt_ratio,
        operating_margin=op_margin,
        revenue_growth_yoy=rev_growth,
        quarterly=quarterly,
    )


def _fetch_kr_ratios(code: str) -> tuple[float | None, float | None]:
    try:
        from pykrx import stock as pykrx_stock
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        df = pykrx_stock.get_market_fundamental(today, today, code)
        if df.empty:
            return None, None
        per = float(df["PER"].iloc[-1]) if "PER" in df.columns else None
        pbr = float(df["PBR"].iloc[-1]) if "PBR" in df.columns else None
        return (None if per == 0 else per), (None if pbr == 0 else pbr)
    except Exception as e:
        logger.warning("KR PER/PBR 조회 실패 %s: %s", code, e)
        return None, None


def _fetch_kr_dart(
    code: str,
) -> tuple[float | None, float | None, float | None, float | None, list[QuarterlyPoint]]:
    """dart-fss로 ROE, 부채비율, 영업이익률, 매출성장률, 분기 데이터 반환."""
    dart_key = os.getenv("DART_API_KEY")
    if not dart_key:
        logger.warning("DART_API_KEY 미설정 — KR 재무 상세 스킵")
        return None, None, None, None, []
    try:
        import dart_fss as dart
        from datetime import datetime, timedelta
        dart.set_api_key(api_key=dart_key)
        corp_list = dart.get_corp_list()
        corps = corp_list.find_by_stock_code(code)
        if not corps:
            logger.warning("DART 기업 코드 조회 실패: %s", code)
            return None, None, None, None, []
        corp_code = corps[0].corp_code

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=550)).strftime("%Y%m%d")
        try:
            fs = dart.fs.extract(corp_code=corp_code, bgn_de=start, end_de=end, fs_tp="CFS")
        except Exception as e:
            logger.warning("DART fs.extract 실패 (CFS) %s: %s — OFS 시도", code, e)
            try:
                fs = dart.fs.extract(corp_code=corp_code, bgn_de=start, end_de=end, fs_tp="OFS")
            except Exception as e2:
                logger.warning("DART fs.extract 실패 (OFS) %s: %s", code, e2)
                return None, None, None, None, []

        if not fs:
            return None, None, None, None, []

        try:
            is_df = fs.show("IS")
        except Exception:
            is_df = None
        try:
            bs_df = fs.show("BS")
        except Exception:
            bs_df = None

        roe = _kr_calc_roe(is_df, bs_df)
        debt_ratio = _kr_calc_debt_ratio(bs_df)
        op_margin, rev_growth = _kr_calc_margins(is_df)
        quarterly = _kr_quarterly(corp_code, dart)

        return roe, debt_ratio, op_margin, rev_growth, quarterly
    except Exception as e:
        logger.warning("DART 재무 조회 실패 %s: %s", code, e)
        return None, None, None, None, []


def _kr_find_row(df, keywords: list[str]) -> float | None:
    """DataFrame에서 키워드가 포함된 첫 행의 최신 값 반환."""
    if df is None or df.empty:
        return None
    for kw in keywords:
        try:
            mask = df.index.str.contains(kw, case=False, na=False)
            if mask.any():
                row = df[mask].iloc[0]
                for col in reversed(row.index.tolist()):
                    try:
                        val = float(str(row[col]).replace(",", ""))
                        if val != 0:
                            return val
                    except (ValueError, TypeError):
                        continue
        except Exception:
            continue
    return None


def _kr_calc_roe(is_df, bs_df) -> float | None:
    try:
        net_income = _kr_find_row(is_df, ["당기순이익"])
        equity = _kr_find_row(bs_df, ["자본총계", "자본 총계"])
        if net_income and equity and equity != 0:
            return round(net_income / equity * 100, 2)
    except Exception:
        pass
    return None


def _kr_calc_debt_ratio(bs_df) -> float | None:
    try:
        liabilities = _kr_find_row(bs_df, ["부채총계", "부채 총계"])
        equity = _kr_find_row(bs_df, ["자본총계", "자본 총계"])
        if liabilities and equity and equity != 0:
            return round(liabilities / equity * 100, 2)
    except Exception:
        pass
    return None


def _kr_calc_margins(is_df) -> tuple[float | None, float | None]:
    try:
        revenue_vals = []
        for kw in ["매출액", "수익(매출액)"]:
            if is_df is None or is_df.empty:
                break
            mask = is_df.index.str.contains(kw, case=False, na=False)
            if mask.any():
                row = is_df[mask].iloc[0]
                vals = []
                for col in row.index:
                    try:
                        v = float(str(row[col]).replace(",", ""))
                        if v > 0:
                            vals.append(v)
                    except (ValueError, TypeError):
                        pass
                if len(vals) >= 2:
                    revenue_vals = vals
                    break

        op_income = _kr_find_row(is_df, ["영업이익"])

        op_margin = None
        if op_income and revenue_vals:
            latest_rev = revenue_vals[0]
            if latest_rev != 0:
                op_margin = round(op_income / latest_rev * 100, 2)

        rev_growth = None
        if len(revenue_vals) >= 2 and revenue_vals[1] != 0:
            rev_growth = round((revenue_vals[0] - revenue_vals[1]) / revenue_vals[1] * 100, 2)

        return op_margin, rev_growth
    except Exception:
        return None, None


def _kr_quarterly(corp_code: str, dart) -> list[QuarterlyPoint]:
    """최근 4분기 매출 + 영업이익."""
    from datetime import datetime, timedelta
    quarters = []
    now = datetime.now()
    for i in range(4):
        try:
            end_dt = now - timedelta(days=i * 90)
            start_dt = end_dt - timedelta(days=95)
            try:
                fs = dart.fs.extract(
                    corp_code=corp_code,
                    bgn_de=start_dt.strftime("%Y%m%d"),
                    end_de=end_dt.strftime("%Y%m%d"),
                    fs_tp="CFS",
                )
            except Exception:
                fs = None
            if not fs:
                continue
            try:
                is_df = fs.show("IS")
            except Exception:
                continue
            label = f"{end_dt.year}Q{(end_dt.month - 1) // 3 + 1}"
            rev = _kr_find_row(is_df, ["매출액", "수익(매출액)"])
            op = _kr_find_row(is_df, ["영업이익"])
            rev_bn = round(rev / 1e8, 0) if rev else None
            op_bn = round(op / 1e8, 0) if op else None
            quarters.append(QuarterlyPoint(label=label, revenue=rev_bn, operating_profit=op_bn))
        except Exception as e:
            logger.warning("분기 데이터 조회 실패 %d분기 전: %s", i, e)
    return list(reversed(quarters))
