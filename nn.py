# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import locale
import io
import base64
import re
from datetime import datetime, timedelta
import random
import numpy as np
import json
import smtplib
import ssl
from email.message import EmailMessage



# … the rest of your imports …


# 환경 설정
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['LANG'] = 'ko_KR.UTF-8'

try:
    locale.setlocale(locale.LC_ALL, 'ko_KR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Korean_Korea.utf8')
    except:
        pass

import streamlit as st
import pandas as pd
import requests
import zipfile
import xml.etree.ElementTree as ET
import feedparser

# 환경 변수 로드 (선택사항)
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# plotly 안전하게 import
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from bs4 import BeautifulSoup

# PDF 생성용 라이브러리
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image as RLImage, PageTemplate, Frame
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# 워드클라우드 라이브러리
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    WORDCLOUD_AVAILABLE = True
except ImportError:
    WORDCLOUD_AVAILABLE = False

# Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# 구글시트 연동 라이브러리 추가
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.oauth2 import service_account
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

st.set_page_config(page_title="SK에너지 경쟁사 분석 대시보드", page_icon="⚡", layout="wide")

# ==========================
# 설정 및 상수
# ==========================


# API 키 설정
DART_API_KEY = st.secrets.get("DART_API_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# 구글시트 설정 (수정됨)
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/16g1G89xoxyqF32YLMD8wGYLnQzjq2F_ew6G1AHH4bCA/edit?usp=sharing"
SHEET_ID = "16g1G89xoxyqF32YLMD8wGYLnQzjq2F_ew6G1AHH4bCA"


# SK 브랜드 컬러 테마
SK_COLORS = {
    'primary': '#E31E24',      # SK 레드
    'secondary': '#FF6B35',    # SK 오렌지
    'accent': '#004EA2',       # SK 블루
    'success': '#00A651',      # 성공 색상
    'warning': '#FF9500',      # 경고 색상
    'competitor': '#6C757D',   # 기본 경쟁사 색상 (회색)
    # 개별 경쟁사 파스텔 색상
    'competitor_1': '#AEC6CF', # 파스텔 블루
    'competitor_2': '#FFB6C1', # 파스텔 핑크
    'competitor_3': '#98FB98', # 파스텔 그린
    'competitor_4': '#F0E68C', # 파스텔 옐로우
    'competitor_5': '#DDA0DD', # 파스텔 퍼플
}

# 세션 상태 초기화
session_vars = [
    'analysis_results', 'comparison_metric', 'quarterly_data', 'financial_data',
    'news_data', 'financial_insight', 'news_insight', 'selected_companies',
    'manual_financial_data', 'selected_charts'  # 수동 업로드용 + 차트 선택 추가
]

for var in session_vars:
    if var not in st.session_state:
        st.session_state[var] = None

if 'comparison_metric' not in st.session_state:
    st.session_state.comparison_metric = "매출 대비 비율"

# ==========================
# 회사별 색상 할당 함수
# ==========================

def get_company_color(company_name, all_companies):
    """회사별 고유 색상 반환 (SK는 빨간색, 경쟁사는 파스텔 구분)"""
    if 'SK' in company_name:
        return SK_COLORS['primary']
    else:
        # 경쟁사들에게 서로 다른 파스텔 색상 할당
        competitor_colors = [
            SK_COLORS['competitor_1'], # 파스텔 블루
            SK_COLORS['competitor_2'], # 파스텔 핑크
            SK_COLORS['competitor_3'], # 파스텔 그린
            SK_COLORS['competitor_4'], # 파스텔 옐로우
            SK_COLORS['competitor_5']  # 파스텔 퍼플
        ]
        
        # SK가 아닌 회사들의 인덱스 계산
        non_sk_companies = [comp for comp in all_companies if 'SK' not in comp]
        try:
            index = non_sk_companies.index(company_name)
            return competitor_colors[index % len(competitor_colors)]
        except ValueError:
            return SK_COLORS['competitor']

# ==========================
# 프로그레스바 개선 함수
# ==========================

def collect_financial_data_with_progress(dart_collector, sk_processor, selected_companies, analysis_year):
    """프로그레스바가 있는 데이터 수집"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    dataframes = []
    total_companies = len(selected_companies)
    
    for idx, company in enumerate(selected_companies):
        progress = (idx + 1) / total_companies
        status_text.text(f"📊 {company} 데이터 수집 중... ({idx + 1}/{total_companies})")
        progress_bar.progress(progress)
        
        dart_df = dart_collector.get_company_financials_auto(company, analysis_year)
        if dart_df is not None and not dart_df.empty:
            processed_df = sk_processor.process_dart_data(dart_df, company)
            if processed_df is not None:
                dataframes.append(processed_df)
    
    status_text.text("✅ 모든 데이터 수집 완료!")
    progress_bar.progress(1.0)
    
    return dataframes

# ==========================
# 분기별 데이터 수집 클래스 (프로그레스바 개선)
# ==========================

class QuarterlyDataCollector:
    def __init__(self, dart_collector):
        self.dart_collector = dart_collector
        self.report_codes = {
            "Q1": "11013", # 1분기
            "Q2": "11012", # 반기 (1,2분기 누적)
            "Q3": "11014", # 3분기
            "Q4": "11011"  # 사업보고서 (연간)
        }

    def collect_quarterly_data(self, company_name, year=2024):
        """분기별 재무 데이터 수집 (프로그레스바 포함)"""
        quarterly_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_quarters = len(self.report_codes)
        
        for idx, (quarter, report_code) in enumerate(self.report_codes.items()):
            progress = (idx + 1) / total_quarters
            status_text.text(f"📊 {company_name} {quarter} 데이터 수집중... ({idx + 1}/{total_quarters})")
            progress_bar.progress(progress)
            
            corp_code = self.dart_collector.get_corp_code_enhanced(company_name)
            if not corp_code:
                continue
                
            df = self.dart_collector.get_financial_statement(corp_code, str(year), report_code)
            if not df.empty:
                # 주요 지표 추출
                quarterly_metrics = self._extract_key_metrics(df, quarter)
                if quarterly_metrics:
                    quarterly_metrics['회사'] = company_name
                    quarterly_metrics['연도'] = year
                    quarterly_results.append(quarterly_metrics)
        
        status_text.text(f"✅ {company_name} 분기별 데이터 수집 완료!")
        progress_bar.progress(1.0)
        
        return pd.DataFrame(quarterly_results) if quarterly_results else pd.DataFrame()

    def _extract_key_metrics(self, df, quarter):
        """주요 재무 지표 추출"""
        metrics = {'분기': quarter}
        
        # 매출액 추출
        revenue_keywords = ['매출액', 'revenue', 'sales']
        for keyword in revenue_keywords:
            revenue_rows = df[df['account_nm'].str.contains(keyword, case=False, na=False)]
            if not revenue_rows.empty:
                try:
                    amount = float(str(revenue_rows.iloc[0]['thstrm_amount']).replace(',', '').replace('-', '0'))
                    metrics['매출액'] = amount / 1_000_000_000_000  # 조원 단위
                    break
                except:
                    continue
        
        # 영업이익 추출
        operating_keywords = ['영업이익', 'operating']
        for keyword in operating_keywords:
            op_rows = df[df['account_nm'].str.contains(keyword, case=False, na=False)]
            if not op_rows.empty:
                try:
                    amount = float(str(op_rows.iloc[0]['thstrm_amount']).replace(',', '').replace('-', '0'))
                    metrics['영업이익'] = amount / 100_000_000  # 억원 단위
                    break
                except:
                    continue
        
        # 영업이익률 계산
        if '매출액' in metrics and '영업이익' in metrics and metrics['매출액'] > 0:
            metrics['영업이익률'] = (metrics['영업이익'] * 100) / (metrics['매출액'] * 10)  # % 단위
        
        return metrics if len(metrics) > 1 else None

# ==========================
# DART API 연동 클래스 (rcept_no 추가)
# ==========================

class DartAPICollector:
    def __init__(self, api_key):
        self.api_key = api_key
        # 출처 추적용 딕셔너리
        self.source_tracking = {}
        
        # 회사명 매핑 개선
# DartAPICollector 클래스의 __init__ 메서드에서 회사명 매핑 부분 수정
        self.company_name_mapping = {
            "SK에너지": [
                "SK에너지", "SK에너지주식회사", "에스케이에너지",
                "SK ENERGY", "SK Energy Co., Ltd."
            ],
            "GS칼텍스": [
                "GS칼텍스", "지에스칼텍스", "GS칼텍스주식회사", "지에스칼텍스주식회사"
            ],
            # HD현대오일뱅크 매핑 강화
            "HD현대오일뱅크": [
                "HD현대오일뱅크", "HD현대오일뱅크주식회사", 
                "현대오일뱅크", "현대오일뱅크주식회사",
                "HYUNDAI OILBANK", "Hyundai Oilbank Co., Ltd.",
                "267250"  # 종목코드 추가
            ],
            "현대오일뱅크": [
                "HD현대오일뱅크", "HD현대오일뱅크주식회사",
                "현대오일뱅크", "현대오일뱅크주식회사"
            ],
            "S-Oil": [
                "S-Oil", "S-Oil Corporation", "S-Oil Corp", "에쓰오일", "에스오일",
                "주식회사S-Oil", "S-OIL", "s-oil", "010950"
            ]
        }

        # STOCK_CODE_MAPPING도 업데이트
        STOCK_CODE_MAPPING = {
            "S-Oil": "010950",
            "GS칼텍스": "089590", 
            "HD현대오일뱅크": "267250",
            "현대오일뱅크": "267250",
            "SK에너지": "096770",
        }


    def get_corp_code_enhanced(self, company_name):
        """강화된 회사 고유번호 조회 (출력 간소화)"""
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={self.api_key}"
        search_names = self.company_name_mapping.get(company_name, [company_name])
        
        try:
            res = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_file = z.open(z.namelist()[0])
                tree = ET.parse(xml_file)
                root = tree.getroot()
            
            # 모든 회사 목록에서 매칭 시도
            all_companies = []
            for corp in root.findall("list"):
                corp_name_elem = corp.find("corp_name")
                corp_code_elem = corp.find("corp_code")
                stock_code_elem = corp.find("stock_code")
                
                if corp_name_elem is not None and corp_code_elem is not None:
                    all_companies.append({
                        'name': corp_name_elem.text,
                        'code': corp_code_elem.text,
                        'stock_code': stock_code_elem.text if stock_code_elem is not None else None
                    })
            
            # 여러 단계로 검색
            for search_name in search_names:
                # 1단계: 종목코드로 검색 (S-Oil 전용)
                if search_name.isdigit():
                    for company in all_companies:
                        if company['stock_code'] == search_name:
                            return company['code']
                
                # 2단계: 정확히 일치
                for company in all_companies:
                    if company['name'] == search_name:
                        return company['code']
                
                # 3단계: 포함 검색
                for company in all_companies:
                    if search_name in company['name'] or company['name'] in search_name:
                        return company['code']
                
                # 4단계: 대소문자 무시 검색
                for company in all_companies:
                    if search_name.lower() in company['name'].lower() or company['name'].lower() in search_name.lower():
                        return company['code']
            
            return None
            
        except Exception as e:
            st.error(f"회사 코드 조회 오류: {e}")
            return None

    def get_financial_statement(self, corp_code, bsns_year, reprt_code, fs_div="CFS"):
        """재무제표 조회"""
        url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div
        }
        
        try:
            res = requests.get(url, params=params).json()
            if res.get("status") == "000" and "list" in res:
                df = pd.DataFrame(res["list"])
                df["보고서구분"] = reprt_code
                return df
            else:
                return pd.DataFrame()
        except Exception as e:
            return pd.DataFrame()

    def get_company_financials_auto(self, company_name, bsns_year):
        """회사 재무제표 자동 수집 (출처 추적 포함)"""
        # 종목코드 직접 매핑
        STOCK_CODE_MAPPING = {
            "S-Oil": "010950",
            "GS칼텍스": "089590", 
            "HD현대오일뱅크": "267250",  # HD현대오일뱅크 추가
            "현대오일뱅크": "267250",    # 현대오일뱅크도 같은 코드
            "SK에너지": "096770",
        }
        
        # 1. 종목코드로 직접 시도
        if company_name in STOCK_CODE_MAPPING:
            stock_code = STOCK_CODE_MAPPING[company_name]
            corp_code = self.convert_stock_to_corp_code(stock_code)
            if corp_code:
                # 재무제표 직접 조회
                report_codes = ["11011", "11014", "11012"]
                for report_code in report_codes:
                    df = self.get_financial_statement(corp_code, bsns_year, report_code)
                    if not df.empty:
                        # rcept_no 생성 및 출처 정보 저장 (개선)
                        rcept_no = self._generate_rcept_no(corp_code, bsns_year, report_code)
                        self._save_source_info(company_name, corp_code, report_code, bsns_year, rcept_no)
                        return df
        
        # 2. 기존 검색 방식으로 폴백
        corp_code = self.get_corp_code_enhanced(company_name)
        if not corp_code:
            return None
        
        # 여러 보고서 타입 시도
        report_codes = ["11011", "11014", "11012"]
        for report_code in report_codes:
            df = self.get_financial_statement(corp_code, bsns_year, report_code)
            if not df.empty:
                # rcept_no 생성 및 출처 정보 저장 (개선)
                rcept_no = self._generate_rcept_no(corp_code, bsns_year, report_code)
                self._save_source_info(company_name, corp_code, report_code, bsns_year, rcept_no)
                return df
        
        return None

    def convert_stock_to_corp_code(self, stock_code):
        """종목코드를 DART 회사코드로 변환"""
        try:
            url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={self.api_key}"
            res = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_file = z.open(z.namelist()[0])
                tree = ET.parse(xml_file)
                root = tree.getroot()
            
            # 종목코드로 매칭
            for corp in root.findall("list"):
                stock_elem = corp.find("stock_code")
                corp_code_elem = corp.find("corp_code")
                
                if (stock_elem is not None and 
                    corp_code_elem is not None and 
                    stock_elem.text == stock_code):
                    return corp_code_elem.text
            
            return None
        except Exception as e:
            return None

    def _generate_rcept_no(self, corp_code, bsns_year, report_code):
        """rcept_no 생성 (실제 API에서 가져오기)"""
        try:
            # DART API의 공시목록 조회
            url = "https://opendart.fss.or.kr/api/list.json"
            params = {
                "crtfc_key": self.api_key,
                "corp_code": corp_code,
                "bgn_de": f"{bsns_year}0101",
                "end_de": f"{bsns_year}1231",
                "pblntf_ty": "A",  # 정기공시
                "corp_cls": "Y",   # 유가증권
                "page_no": 1,
                "page_count": 100
            }
            
            res = requests.get(url, params=params).json()
            if res.get("status") == "000" and "list" in res:
                # 해당 보고서 타입에 맞는 rcept_no 찾기
                report_keywords = {
                    "11011": ["사업보고서"],
                    "11014": ["분기보고서", "3분기"],
                    "11012": ["반기보고서"],
                    "11013": ["분기보고서", "1분기"]
                }
                
                keywords = report_keywords.get(report_code, [])
                for item in res["list"]:
                    report_nm = item.get("report_nm", "")
                    if any(keyword in report_nm for keyword in keywords):
                        return item.get("rcept_no")
            
            return f"{corp_code}_{bsns_year}_{report_code}"  # 기본값
        except:
            return f"{corp_code}_{bsns_year}_{report_code}"

    def _save_source_info(self, company_name, corp_code, report_code, bsns_year, rcept_no):
        """출처 정보 저장 (개선된 버전)"""
        report_type_map = {
            "11011": "사업보고서",
            "11014": "3분기보고서",
            "11012": "반기보고서",
            "11013": "1분기보고서"
        }
        
        self.source_tracking[company_name] = {
            'company_code': corp_code,
            'report_code': report_code,
            'report_type': report_type_map.get(report_code, "재무제표"),
            'year': bsns_year,
            'rcept_no': rcept_no,
            'dart_url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
            'direct_link': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}&reprtCode={report_code}"
        }

# ==========================
# SK 중심 재무데이터 프로세서
# ==========================
# ==========================
# 수동 XBRL 업로드용 재무데이터 프로세서 (완전 개선 버전)
# ==========================

class FinancialDataProcessor:
    # 더 포괄적한 XBRL 태그 매핑 (정규식 패턴)
    INCOME_STATEMENT_PATTERNS = {
        # XBRL 실제 태그명 매핑
        r'(ifrs-full:Revenue|revenue|sales|매출|수익|총매출|매출수익|operating.*revenue)(?!.*cost|원가|비용)': '매출액',
        r'(ifrs-full:CostOfSales|cost.*revenue|cost.*sales|cost.*goods|매출원가|원가|판매원가|제품매출원가)': '매출원가',
        
        # 이익 관련
        r'(ifrs-full:GrossProfit|gross.*profit|총이익|매출총이익|총수익)': '매출총이익',
        r'(dart:OperatingIncomeLoss|ifrs-full:OperatingIncomeLoss|operating.*income|operating.*profit|영업이익|영업손익|영업수익)(?!.*비용|expense)': '영업이익',
        r'(ifrs-full:ProfitLoss|net.*income|net.*profit|당기순이익|순이익|당기.*순손익|net.*earnings)(?!.*loss)': '당기순이익',
        
        # 비용 관련 (더 정확한 패턴)
        r'(dart:TotalSellingGeneralAdministrativeExpenses|selling.*expense|selling.*cost|판매비|판매비용|판매관리비)': '판관비',
        r'(selling.*expense|selling.*cost|판매비|판매비용|판매관련비용)': '판매비',
        r'(administrative.*expense|administrative.*cost|관리비|관리비용|일반관리비)': '관리비',
        r'(employee.*benefit|employee.*cost|wage|salary|인건비|급여|임금)': '인건비',
        r'(depreciation|amortization|감가상각|상각비|감가상각비)': '감가상각비',
        
        # 기타 항목
        r'(ifrs-full:FinanceCosts|interest.*expense|interest.*cost|이자비용|이자지급)': '이자비용',
        r'(financial.*cost|금융비용|금융원가)': '금융비용',
        r'(non.*operating.*income|영업외수익|기타수익)': '영업외수익',
        r'(non.*operating.*expense|영업외비용|기타비용)': '영업외비용'
    }
    
    def __init__(self):
        self.company_data = {}
        # 정규식 미리 컴파일 (성능 향상)
        self.compiled_patterns = {}
        for pattern, item in self.INCOME_STATEMENT_PATTERNS.items():
            self.compiled_patterns[re.compile(pattern, re.IGNORECASE)] = item

    def load_file(self, uploaded_file):
        """개선된 XBRL 파일 로드 (속도 최적화 + 오류 처리 강화)"""
        try:
            # 파일 크기 체크 (50MB 제한)
            file_size = uploaded_file.size if hasattr(uploaded_file, 'size') else 0
            if file_size > 50 * 1024 * 1024:
                st.error(f"❌ 파일이 너무 큽니다 ({file_size/(1024*1024):.1f}MB). 50MB 이하로 업로드해주세요.")
                return None
            
            # 파일 처음부터 읽기
            uploaded_file.seek(0)
            content = uploaded_file.read()
            
            # 빠른 인코딩 감지 및 디코딩
            content_str = self._fast_decode(content)
            if not content_str:
                st.error("❌ 파일 인코딩을 읽을 수 없습니다.")
                return None
            
            # XML 파싱 (더 안전한 방식)
            try:
                # lxml이 있으면 사용, 없으면 기본 xml 파서 사용
                soup = BeautifulSoup(content_str, 'lxml-xml')
                if not soup.find():  # 파싱 실패 시 기본 파서 사용
                    soup = BeautifulSoup(content_str, 'xml')
            except Exception:
                soup = BeautifulSoup(content_str, 'html.parser')  # 최후 수단
            
            # 회사명 추출 (더 빠르고 정확하게)
            company_name = self._extract_company_name_fast(soup, uploaded_file.name)
            
            # 재무 데이터 추출 (최적화된 버전)
            financial_data = self._extract_financial_items_optimized(soup)
            
            if not financial_data:
                st.warning(f"⚠️ {uploaded_file.name}에서 재무 항목을 찾을 수 없습니다.")
                st.info("💡 파일이 표준 XBRL 형식인지 확인해주세요.")
                return None
            
            # 표준 손익계산서 구조로 변환
            income_statement = self._create_income_statement(financial_data, company_name)
            return income_statement
            
        except Exception as e:
            st.error(f"❌ 파일 처리 중 오류: {str(e)}")
            st.info("💡 파일 형식을 확인하고 다시 시도해주세요.")
            return None

    def _fast_decode(self, content):
        """최적화된 인코딩 감지 및 디코딩"""
        # 가장 일반적인 인코딩부터 시도 (한국어 환경 최적화)
        encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'iso-8859-1', 'ascii']
        
        for encoding in encodings:
            try:
                decoded = content.decode(encoding)
                # 한글이 제대로 디코딩되었는지 간단히 체크
                if '매출' in decoded or 'revenue' in decoded.lower():
                    return decoded
                return decoded  # 한글이 없어도 성공한 디코딩은 반환
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # 모든 인코딩 실패 시 오류 무시하고 디코딩
        try:
            return content.decode('utf-8', errors='ignore')
        except:
            return None

    def _extract_company_name_fast(self, soup, filename):
        """최적화된 회사명 추출"""
        # 1단계: 표준 XBRL 태그에서 회사명 검색
        company_tags = [
            'EntityRegistrantName', 'CompanyName', 'entity', 'registrant',
            'ReportingEntityName', 'EntityName', 'CorporateName'
        ]
        
        for tag_name in company_tags:
            # 정확한 태그명으로 먼저 검색
            node = soup.find(tag_name)
            if node and node.string and len(node.string.strip()) > 1:
                return node.string.strip()
            
            # 부분 매칭으로 검색 (대소문자 무시)
            node = soup.find(lambda t: t.name and tag_name.lower() in t.name.lower())
            if node and node.string and len(node.string.strip()) > 1:
                return node.string.strip()
        
        # 2단계: 파일명에서 회사명 추출 (강화된 매핑)
        name = filename.split('.')[0].lower()
        name_mapping = {
            'sk': 'SK에너지',
            'skenergy': 'SK에너지',
            'gs': 'GS칼텍스',
            'gscaltex': 'GS칼텍스',
            'hd': 'HD현대오일뱅크',
            'hyundai': 'HD현대오일뱅크',
            'hdoil': 'HD현대오일뱅크',
            's-oil': 'S-Oil',
            'soil': 'S-Oil',
            'soilcorp': 'S-Oil'
        }
        
        for key, company in name_mapping.items():
            if key in name:
                return company
        
        # 3단계: 파일명 그대로 사용 (정리해서)
        clean_name = re.sub(r'[^A-Za-z가-힣0-9\s]', '', filename.split('.')[0])
        return clean_name if clean_name else "Unknown Company"

    def _extract_financial_items_optimized(self, soup):
        """최적화된 재무 항목 추출"""
        items = {}
        processed_count = 0
        
        # 숫자가 포함된 태그만 사전 필터링 (성능 향상)
        numeric_tags = []
        for tag in soup.find_all():
            if tag.string and re.search(r'\d', tag.string):
                numeric_tags.append(tag)
        
        if not numeric_tags:
            st.warning("📊 숫자 데이터가 포함된 태그를 찾을 수 없습니다.")
            return items
        
        # 진행 상황 표시
        st.info(f"🔍 {len(numeric_tags)}개의 숫자 태그 발견, 분석 중...")
        
        # 디버깅: 실제 추출된 데이터 로깅 (확장 가능한 형태로 변경)
        with st.expander("🔍 XBRL 파일에서 추출된 원시 데이터 (클릭하여 확장)", expanded=False):
            st.write("📊 주요 재무 데이터 원시값:")
            
            # 각 태그 분석
            for tag in numeric_tags:
                tag_text = tag.string.strip()
                
                # 숫자 추출 및 검증
                try:
                    # 괄호로 둘러싸인 음수 처리
                    if '(' in tag_text and ')' in tag_text:
                        number_str = re.sub(r'[^\d.]', '', tag_text.replace('(', '').replace(')', ''))
                        if number_str:
                            value = -float(number_str)
                        else:
                            continue
                    else:
                        # 일반적인 숫자 추출
                        number_str = re.sub(r'[^\d.-]', '', tag_text)
                        if number_str and number_str not in ['-', '.', '-.']:
                            value = float(number_str)
                        else:
                            continue
                    
                    # 주요 재무 항목 태그만 표시 (1억원 이상)
                    if abs(value) >= 100_000_000:  # 1억원 이상
                        # 주요 재무 항목 태그인지 확인
                        tag_name = tag.name.lower() if tag.name else ''
                        is_key_financial = any(keyword in tag_name for keyword in [
                            'revenue', 'cost', 'profit', 'income', 'expense', 'loss',
                            '매출', '원가', '이익', '수익', '비용', '손실'
                        ])
                        
                        if is_key_financial:
                            st.write(f"  💰 {value:,.0f}원 (태그: {tag.name})")
                        else:
                            st.write(f"  📊 {value:,.0f}원 (태그: {tag.name})")
                    
                    # XBRL 파일은 원 단위로 제공되므로 억원 단위로 변환
                    original_value = value
                    value = value / 100_000_000  # 원 → 억원 변환
                    
                    # 디버깅: 단위 변환 과정 로깅
                    st.write(f"🔍 단위 변환: {original_value:,.0f}원 → {value:,.2f}억원")
                    
                    # 너무 작은 값은 제외 (노이즈 제거)
                    if abs(value) < 0.01:  # 1백만원 미만 제외
                        st.write(f"🔍 노이즈 제거: {value:,.2f}억원 (1백만원 미만)")
                        continue
                        
                except (ValueError, TypeError):
                    continue
                
                # 태그 정보 구성 (태그명 + 속성)
                tag_info_parts = [tag.name.lower() if tag.name else '']
                if tag.attrs:
                    tag_info_parts.extend([str(v).lower() for v in tag.attrs.values()])
                tag_info = ' '.join(tag_info_parts)
                
                # 정규식 패턴 매칭
                for pattern, standard_item in self.compiled_patterns.items():
                    if pattern.search(tag_info):
                        # 같은 항목이 이미 있으면 더 큰 절댓값으로 업데이트
                        if standard_item not in items or abs(value) > abs(items[standard_item]):
                            items[standard_item] = value
                        processed_count += 1
                        break
        
        # 결과 요약 표시
        if items:
            st.success(f"✅ {len(items)}개 재무항목 추출 (총 {processed_count}개 태그 처리)")
            with st.expander("🔍 추출된 데이터 상세 보기", expanded=False):
                for key, value in items.items():
                    formatted_value = self._format_amount(value)
                    st.write(f"**{key}**: {formatted_value} (원시값: {value:,.2f}억원)")
        else:
            st.warning("⚠️ 표준 재무 항목을 찾을 수 없습니다.")
        
        return items

    def _create_income_statement(self, data, company_name):
        """표준 손익계산서 구조 생성"""
        # 표준 손익계산서 항목 순서
        standard_items = [
            '매출액', '매출원가', '매출총이익', '판매비', '관리비', '판관비',
            '인건비', '감가상각비', '영업이익', '영업외수익', '영업외비용',
            '금융비용', '이자비용', '당기순이익'
        ]
        
        # 파생 항목 계산 (누락된 항목 추정)
        calculated_items = self._calculate_derived_items(data)
        data.update(calculated_items)
        
        # 손익계산서 생성
        income_statement = []
        for item in standard_items:
            value = data.get(item, 0)
            if value != 0:  # 0이 아닌 값만 포함
                income_statement.append({
                    '구분': item,
                    company_name: self._format_amount(value),
                    f'{company_name}_원시값': value
                })
        
        # 비율 계산 및 추가
        ratios = self._calculate_ratios(data)
        for ratio_name, ratio_value in ratios.items():
            income_statement.append({
                '구분': ratio_name,
                company_name: f"{ratio_value:.2f}%",
                f'{company_name}_원시값': ratio_value
            })
        
        return pd.DataFrame(income_statement)

    def _calculate_derived_items(self, data):
        """파생 항목 계산"""
        calculated = {}
        
        if '매출액' in data and '매출원가' in data:
            calculated['매출총이익'] = data['매출액'] - data['매출원가']
        elif '매출액' in data and '매출총이익' not in data:
            calculated['매출총이익'] = data['매출액'] * 0.3
            calculated['매출원가'] = data['매출액'] - calculated['매출총이익']
            
        if '판매비' in data and '관리비' in data:
            calculated['판관비'] = data['판매비'] + data['관리비']
            
        # 당기순이익 정확한 계산
        if '영업이익' in data and '영업외수익' in data and '영업외비용' in data:
            calculated['당기순이익'] = data['영업이익'] + data['영업외수익'] - data['영업외비용']
        elif '영업이익' in data:
            calculated['당기순이익'] = data['영업이익']
            
        # 디버깅: 당기순이익 계산 로깅
        if '당기순이익' in calculated:
            st.write(f"🔍 당기순이익 계산:")
            st.write(f"  영업이익: {data.get('영업이익', 0):,.0f}억원")
            st.write(f"  영업외수익: {data.get('영업외수익', 0):,.0f}억원")
            st.write(f"  영업외비용: {data.get('영업외비용', 0):,.0f}억원")
            st.write(f"  계산결과: {calculated['당기순이익']:,.0f}억원")
            
        return calculated

    def _calculate_ratios(self, data):
        """주요 재무비율 계산"""
        ratios = {}
        매출액 = data.get('매출액', 0)
        
        if 매출액 <= 0:
            return ratios  # 매출액이 없으면 비율 계산 불가
        
        # 수익성 비율
        if '영업이익' in data:
            ratios['영업이익률(%)'] = round((data['영업이익'] / 매출액) * 100, 2)
        
        if '당기순이익' in data:
            ratios['순이익률(%)'] = round((data['당기순이익'] / 매출액) * 100, 2)
        
        if '매출총이익' in data:
            ratios['매출총이익률(%)'] = round((data['매출총이익'] / 매출액) * 100, 2)
        
        # 비용 비율
        if '매출원가' in data:
            ratios['매출원가율(%)'] = round((data['매출원가'] / 매출액) * 100, 2)
        
        if '판관비' in data:
            ratios['판관비율(%)'] = round((data['판관비'] / 매출액) * 100, 2)
        
        if '인건비' in data:
            ratios['인건비율(%)'] = round((data['인건비'] / 매출액) * 100, 2)
        
        return ratios

    def _format_amount(self, amount):
        """금액 포맷팅 (한국 단위 사용) - 억원 단위 기준"""
        if amount == 0:
            return "0원"
            
        abs_amount = abs(amount)
        sign = "▼ " if amount < 0 else ""
        
        # 디버깅: 입력값 로깅 (상세)
        st.write(f"🔍 _format_amount 입력값: {amount:,.2f}억원 (절댓값: {abs_amount:,.2f})")
        
        # amount는 이미 억원 단위로 변환된 값
        if abs_amount >= 1:  # 1억 이상
            result = f"{sign}{amount:.0f}억원"
            st.write(f"🔍 [단위] 억원 단위 변환 결과: {result} (억원 기준: {abs_amount:.0f})")
            return result
        elif abs_amount >= 0.01:  # 1백만 이상
            result = f"{sign}{amount*100:.0f}백만원"
            st.write(f"🔍 [단위] 백만원 단위 변환 결과: {result} (백만원 기준: {abs_amount*100:.0f})")
            return result
        else:
            result = f"{sign}{amount*100_000_000:,.0f}원"
            st.write(f"🔍 [단위] 원 단위 변환 결과: {result} (원 기준: {amount*100_000_000:,.0f})")
            return result

    def merge_company_data(self, dataframes):
        """여러 회사 데이터 병합 (안전한 병합)"""
        if not dataframes:
            return pd.DataFrame()
        
        if len(dataframes) == 1:
            return dataframes[0]
        
        # 기준이 되는 첫 번째 데이터프레임
        merged = dataframes[0].copy()
        
        # 나머지 데이터프레임들을 순차적으로 병합
        for df in dataframes[1:]:
            try:
                # 회사 컬럼만 추출 (구분, _원시값 컬럼 제외)
                company_cols = [col for col in df.columns 
                              if col != '구분' and not col.endswith('_원시값')]
                
                for company_col in company_cols:
                    # 구분을 인덱스로 하여 데이터 병합
                    company_data = df.set_index('구분')[company_col]
                    merged_temp = merged.set_index('구분')
                    merged_temp = merged_temp.join(company_data, how='outer')
                    merged = merged_temp.reset_index()
            except Exception as e:
                st.warning(f"⚠️ 데이터 병합 중 오류: {e}")
                continue
        
        # 결측치를 "-"로 채움
        merged = merged.fillna("-")
        
        return merged

    def create_comparison_report(self, merged_df):
        """경쟁사 비교 리포트 생성"""
        if merged_df is None or merged_df.empty:
            return "📋 비교할 데이터가 없습니다."
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("📊 XBRL 손익계산서 경쟁사 비교 분석")
        report_lines.append("=" * 80)
        
        # 기본 정보
        companies = [col for col in merged_df.columns 
                    if col != '구분' and not col.endswith('_원시값')]
        report_lines.append(f"📈 분석 대상 회사: {', '.join(companies)}")
        report_lines.append(f"📋 분석 항목 수: {len(merged_df)}개")
        report_lines.append("")
        
        # 주요 수익성 지표 하이라이트
        profit_rows = merged_df[merged_df['구분'].str.contains('이익률|비율', na=False)]
        
        if not profit_rows.empty:
            report_lines.append("🎯 주요 수익성 지표 비교")
            report_lines.append("-" * 50)
            
            for _, row in profit_rows.iterrows():
                구분 = row['구분']
                values = []
                for company in companies:
                    value = row.get(company, "-")
                    if value != "-":
                        values.append(f"{company}: {value}")
                
                if values:
                    report_lines.append(f"• {구분}")
                    report_lines.append(f"  {' | '.join(values)}")
            
            report_lines.append("")
        
        # 절댓값 데이터 요약
        absolute_rows = merged_df[~merged_df['구분'].str.contains('률|비율', na=False)]
        if not absolute_rows.empty:
            report_lines.append("💰 주요 절댓값 지표")
            report_lines.append("-" * 50)
            
            key_items = ['매출액', '영업이익', '당기순이익']
            for item in key_items:
                item_row = absolute_rows[absolute_rows['구분'] == item]
                if not item_row.empty:
                    values = []
                    for company in companies:
                        value = item_row.iloc[0].get(company, "-")
                        if value != "-":
                            values.append(f"{company}: {value}")
                    
                    if values:
                        report_lines.append(f"• {item}")
                        report_lines.append(f"  {' | '.join(values)}")
        
        report_lines.append("")
        report_lines.append("💡 이 분석은 업로드된 XBRL 파일을 기반으로 자동 생성되었습니다.")
        report_lines.append("📊 정확한 분석을 위해 원본 재무제표와 대조하여 확인하시기 바랍니다.")
        
        return "\n".join(report_lines)


# ==========================
# 수동 XBRL 업로드용 재무데이터 프로세서 (개선된 버전)
# ==========================

class SKFinancialDataProcessor:
    INCOME_STATEMENT_MAP = {
        'sales': '매출액',
        'revenue': '매출액',
        '매출액': '매출액',
        '수익(매출액)': '매출액',
        'costofgoodssold': '매출원가',
        'cogs': '매출원가',
        'costofrevenue': '매출원가',
        '매출원가': '매출원가',
        'operatingexpenses': '판관비',
        'sellingexpenses': '판매비',
        'administrativeexpenses': '관리비',
        '판매비와관리비': '판관비',
        '판관비': '판관비',
        'grossprofit': '매출총이익',
        '매출총이익': '매출총이익',
        'operatingincome': '영업이익',
        'operatingprofit': '영업이익',
        '영업이익': '영업이익',
        'netincome': '당기순이익',
        '당기순이익': '당기순이익',
    }
    
    def __init__(self):
        self.company_data = {}
        self.sk_company = "SK에너지"
        self.competitors = ["GS칼텍스", "HD현대오일뱅크", "S-Oil"]

    def process_dart_data(self, dart_df, company_name):
        """DART API에서 받은 DataFrame을 표준 손익계산서로 변환"""
        try:
            if dart_df.empty:
                st.warning(f"⚠️ {company_name}: DART에서 데이터를 가져오지 못했습니다.")
                return None

            # 디버깅: 원본 DART 데이터 로깅
            st.write(f"🔍 {company_name} 원본 DART 데이터 ({len(dart_df)}개 항목):")
            debug_df = dart_df[['account_nm', 'thstrm_amount']].head(10)
            st.dataframe(debug_df, use_container_width=True)

            financial_data = {}
            processed_count = 0
            
            for _, row in dart_df.iterrows():
                account_nm = row.get('account_nm', '')
                thstrm_amount = row.get('thstrm_amount', '0')
                
                # 빈 값 건너뛰기
                if not account_nm or not thstrm_amount:
                    continue
                        
                try:
                    # 마이너스 값 정확 처리
                    amount_str = str(thstrm_amount).replace(',', '')
                    if '(' in amount_str and ')' in amount_str:
                        # 괄호로 표시된 마이너스
                        amount_str = '-' + amount_str.replace('(', '').replace(')', '')
                    value = float(amount_str) if amount_str != '-' else 0
                    
                    # DART API는 천원 단위로 제공하므로 억원 단위로 변환
                    value = value / 100_000  # 천원 → 억원 변환
                    
                except (ValueError, TypeError):
                    continue

                # 계정과목 매핑
                mapped = False
                for key, mapped_name in self.INCOME_STATEMENT_MAP.items():
                    if key in account_nm or account_nm in key:
                        if mapped_name not in financial_data or abs(value) > abs(financial_data[mapped_name]):
                            financial_data[mapped_name] = value
                            mapped = True
                        break
                
                if mapped:
                    processed_count += 1

            # 디버깅: 매핑된 재무 데이터 로깅
            st.write(f"📊 {company_name} 매핑된 재무 데이터 ({processed_count}개 처리):")
            for key, value in financial_data.items():
                st.write(f"  {key}: {value:,.0f}억원")

            # 데이터 검증
            if not financial_data:
                st.error(f"❌ {company_name}: 매핑된 재무 데이터가 없습니다.")
                return None

            return self._create_income_statement(financial_data, company_name)
            
        except Exception as e:
            st.error(f"DART 데이터 처리 오류: {e}")
            return None

    def _create_income_statement(self, data, company_name):
        """표준 손익계산서 구조 생성"""
        standard_items = [
            '매출액', '매출원가', '매출총이익', '판매비', '관리비', '판관비',
            '인건비', '감가상각비', '영업이익', '영업외수익', '영업외비용',
            '금융비용', '이자비용', '당기순이익'
        ]
        
        calculated_items = self._calculate_derived_items(data)
        data.update(calculated_items)
        
        income_statement = []
        for item in standard_items:
            value = data.get(item, 0)
            if value != 0:
                if item in ['영업이익', '당기순이익']:
                    formatted_value = self._format_amount_with_loss_indicator(value)
                else:
                    formatted_value = self._format_amount_profit(value)
                
                income_statement.append({
                    '구분': item,
                    company_name: formatted_value,
                    f'{company_name}_원시값': value
                })
        
        ratios = self._calculate_enhanced_ratios(data)
        for ratio_name, ratio_value in ratios.items():
            if ratio_name == '매출 1조원당 영업이익(억원)':
                display_value = f"{ratio_value:.2f}억원"
            elif ratio_name.endswith('(%)'):
                display_value = f"{ratio_value:.2f}%"
            else:
                display_value = f"{ratio_value:.2f}점"
            
            income_statement.append({
                '구분': ratio_name,
                company_name: display_value,
                f'{company_name}_원시값': ratio_value
            })
        
        return pd.DataFrame(income_statement)

    def _calculate_derived_items(self, data):
        calculated = {}
        if '매출액' in data and '매출원가' in data:
            calculated['매출총이익'] = data['매출액'] - data['매출원가']
        elif '매출액' in data and '매출총이익' not in data:
            calculated['매출총이익'] = data['매출액'] * 0.3
            calculated['매출원가'] = data['매출액'] - calculated['매출총이익']
        
        if '판매비' in data and '관리비' in data:
            calculated['판관비'] = data['판매비'] + data['관리비']
        
        # 당기순이익 정확한 계산
        if '영업이익' in data and '영업외수익' in data and '영업외비용' in data:
            calculated['당기순이익'] = data['영업이익'] + data['영업외수익'] - data['영업외비용']
        elif '영업이익' in data:
            calculated['당기순이익'] = data['영업이익']
            
        # 디버깅: 당기순이익 계산 로깅
        if '당기순이익' in calculated:
            st.write(f"🔍 당기순이익 계산:")
            st.write(f"  영업이익: {data.get('영업이익', 0):,.0f}억원")
            st.write(f"  영업외수익: {data.get('영업외수익', 0):,.0f}억원")
            st.write(f"  영업외비용: {data.get('영업외비용', 0):,.0f}억원")
            st.write(f"  계산결과: {calculated['당기순이익']:,.0f}억원")
            
        return calculated

    def _calculate_enhanced_ratios(self, data):
        """정규화 지표 계산"""
        ratios = {}
        매출액 = data.get('매출액', 0)
        
        if 매출액 > 0:
            # 영업이익률
            if '영업이익' in data and data['영업이익'] is not None:
                ratios['영업이익률(%)'] = round((data['영업이익'] / 매출액) * 100, 2)
            
            # 순이익률
            if '당기순이익' in data and data['당기순이익'] is not None:
                ratios['순이익률(%)'] = round((data['당기순이익'] / 매출액) * 100, 2)
            
            # 매출원가율
            if '매출원가' in data and data['매출원가'] is not None:
                ratios['매출원가율(%)'] = round((data['매출원가'] / 매출액) * 100, 2)
            
            # 판관비율
            if '판관비' in data and data['판관비'] is not None:
                ratios['판관비율(%)'] = round((data['판관비'] / 매출액) * 100, 2)
            
            # 매출 1조원당 영업이익
            if '영업이익' in data and data['영업이익'] is not None:
                try:
                    ratios['매출 1조원당 영업이익(억원)'] = round((data['영업이익'] / 100_000_000) / (매출액 / 1_000_000_000_000), 2)
                except ZeroDivisionError:
                    ratios['매출 1조원당 영업이익(억원)'] = 0
                
            # 원가효율성지수
            if '매출원가율(%)' in ratios:
                ratios['원가효율성지수(점)'] = round(100 - ratios['매출원가율(%)'], 2)
            
            # 종합수익성점수
            operating_margin = ratios.get('영업이익률(%)', 0)
            net_margin = ratios.get('순이익률(%)', 0)
            ratios['종합수익성점수(점)'] = round((operating_margin * 2 + net_margin) / 3, 2)
            
            # 업계 평균 대비 (수정된 계산)
            industry_avg_margin = 3.5
            if operating_margin > 0:
                ratios['업계대비성과(%)'] = round((operating_margin / industry_avg_margin) * 100, 2)
            else:
                ratios['업계대비성과(%)'] = 0
                
            # 디버깅: 업계대비성과 계산 로깅
            st.write(f"🔍 업계대비성과 계산:")
            st.write(f"  영업이익률: {operating_margin:.2f}%")
            st.write(f"  업계평균: {industry_avg_margin}%")
            st.write(f"  계산결과: {ratios['업계대비성과(%)']:.2f}%")
                
        return ratios

    def _format_amount_with_loss_indicator(self, amount):
        """영업손실/당기순손실 명확 표시 함수"""
        # 디버깅: 입력값 크기 확인
        st.write(f"🔍 _format_amount_with_loss_indicator 입력값: {amount:,.0f}억원")
        
        if amount < 0:
            abs_amount = abs(amount)
            st.write(f"🔍 절댓값: {abs_amount:,.0f}억원")
            
            if abs_amount >= 1_000_000_000_000:
                result = f"▼ {abs_amount/1_000_000_000_000:.1f}조원 손실"
                st.write(f"🔍 조원 단위 변환 결과: {result}")
                return result
            elif abs_amount >= 100_000_000:
                result = f"▼ {abs_amount/100_000_000:.0f}억원 손실"
                st.write(f"🔍 억원 단위 변환 결과: {result}")
                return result
            elif abs_amount >= 10_000:
                result = f"▼ {abs_amount/10_000:.0f}만원 손실"
                st.write(f"🔍 만원 단위 변환 결과: {result}")
                return result
            else:
                result = f"▼ {abs_amount:,.0f}원 손실"
                st.write(f"🔍 원 단위 결과: {result}")
                return result
        else:
            return self._format_amount_profit(amount)

    def _format_amount_profit(self, amount):
        if abs(amount) >= 1_000_000_000_000:
            return f"{amount/1_000_000_000_000:.1f}조원"
        elif abs(amount) >= 100_000_000:
            return f"{amount/100_000_000:.0f}억원"
        elif abs(amount) >= 10_000:
            return f"{amount/10_000:.0f}만원"
        else:
            return f"{amount:,.0f}원"

    def merge_company_data(self, dataframes):
        if not dataframes:
            return pd.DataFrame()
        
        sk_df = None
        other_dfs = []
        
        for df in dataframes:
            if any(self.sk_company in col for col in df.columns):
                sk_df = df.copy()
            else:
                other_dfs.append(df)
        
        if sk_df is not None:
            merged = sk_df.copy()
            dataframes_to_merge = other_dfs
        else:
            merged = dataframes[0].copy()
            dataframes_to_merge = dataframes[1:]
        
        for df in dataframes_to_merge:
            company_cols = [col for col in df.columns if col != '구분' and not col.endswith('_원시값')]
            for company_col in company_cols:
                company_data = df.set_index('구분')[company_col]
                merged = merged.set_index('구분').join(company_data, how='outer').reset_index()
        
        merged = merged.fillna("-")
        
        cols = ['구분']
        sk_cols = [col for col in merged.columns if self.sk_company in col and not col.endswith('_원시값')]
        competitor_cols = [col for col in merged.columns if col not in cols + sk_cols and not col.endswith('_원시값')]
        final_cols = cols + sk_cols + competitor_cols
        
        raw_value_cols = [col for col in merged.columns if col.endswith('_원시값')]
        final_cols.extend(raw_value_cols)
        
        merged = merged[final_cols]
        return merged

# ==========================
# 구글시트 + RSS 통합 뉴스 수집 클래스 (개선)
# ==========================

# -*- coding: utf-8 -*-


import os
import re
import json
from datetime import datetime
from typing import Dict, List, Union

import pandas as pd
import feedparser

# 선택 의존성 – 설치돼 있지 않으면 Google Sheets 기능만 비활성화
try:
    import gspread
    from google.oauth2.service_account import Credentials
    _GSPREAD_AVAILABLE = True
except ImportError:  # 서버에 gspread 가 없을 수도 있음
    _GSPREAD_AVAILABLE = False

# Plotly 같은 시각화는 외부에서 쓰므로 이곳에선 필요 없음
# ---------------------------------------------------------------------
class SKNewsCollector:
    """
    SK 에너지 & 국내 정유업계 전용 뉴스 수집기
    사용법
    -----
    collector = SKNewsCollector(
        sheet_id="16g1G89x…",                         # 필수 X
        service_account_json="service_key.json"       # 또는 dict / ENV
    )
    df = collector.collect_news(max_items_per_feed=30)
    """

    # RSS 피드 -----------------
    DEFAULT_RSS: Dict[str, str] = {
        "연합뉴스_경제":   "https://www.yna.co.kr/rss/economy.xml",
        "조선일보_경제":   "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/",
        "한국경제":       "https://www.hankyung.com/feed/economy",
        "서울경제":       "https://www.sedaily.com/RSSFeed.xml",
        "매일경제":       "https://www.mk.co.kr/rss/30000001/",
        "이데일리":       "https://www.edaily.co.kr/rss/rss_economy.xml",
        "아시아경제":     "https://rss.asiae.co.kr/economy.xml",
        "파이낸셜뉴스":   "https://www.fnnews.com/rss/fn_realestate_all.xml",
    }

    # 키워드 -------------------
    OIL_KEYWORDS: List[str] = [
        # SK 계열
        "SK", "SK에너지", "SK이노베이션", "SK온", "SK그룹",
        # 경쟁사
        "GS칼텍스", "HD현대오일뱅크", "현대오일뱅크", "S-Oil", "에쓰오일",
        # 산업/시장
        "정유", "유가", "원유", "석유", "화학", "에너지", "나프타",
        "휘발유", "경유", "등유", "중유", "석유화학", "정제", "정제마진",
        "WTI", "두바이유", "브렌트유",
        # 재무/실적
        "영업이익", "순이익", "매출", "실적", "손실", "흑자", "적자",
        "수익성", "마진", "투자", "설비",
        # 정책·환경
        "탄소중립", "ESG", "친환경", "수소", "신재생에너지",
    ]

    # -----------------------------------------------------------------
    def __init__(
        self,
        sheet_id: str | None = None,
        service_account_json: Union[str, Dict, None] = None,
        rss_feeds: Dict[str, str] | None = None,
    ) -> None:
        self.sheet_id = sheet_id                # 없으면 Google Sheets 기능 생략
        self.service_account_json = service_account_json
        self.rss_feeds = rss_feeds or self.DEFAULT_RSS.copy()

    # =========================  PUBLIC API  =========================
    def collect_news(self, *, max_items_per_feed: int = 25) -> pd.DataFrame:
        """
        Google Sheets + RSS에서 뉴스를 모아 하나의 DataFrame으로 반환
        """
        df_sheets = self._fetch_sheet_news()           # 실패해도 빈 DF
        df_rss    = self._fetch_rss_news(max_items=max_items_per_feed)

        if df_sheets.empty and df_rss.empty:
            return pd.DataFrame()

        df_all = pd.concat([df_sheets, df_rss], ignore_index=True)
        df_all.drop_duplicates(subset="제목", inplace=True)
        df_all.sort_values(["SK관련도", "영향도"], ascending=[False, False], inplace=True)
        df_all.reset_index(drop=True, inplace=True)
        return df_all

    # =======================  GOOGLE SHEETS  ========================
    def _fetch_sheet_news(self) -> pd.DataFrame:
        """
        Google Sheets에서 기사 목록 가져오기
        - gspread 가 없거나 인증 실패 시 빈 DF 반환
        - service_account_json 우선 → 환경변수 JSON(NEWS_SVC_KEY) 대체 허용
        """
        if not _GSPREAD_AVAILABLE or not self.sheet_id:
            return pd.DataFrame()

        # ---- 인증 정보 확보 ---------------------------------------
        key_payload: Dict | None = None
        if isinstance(self.service_account_json, dict):
            key_payload = self.service_account_json
        elif isinstance(self.service_account_json, str):
            # 경로일 수도, JSON 문자열일 수도
            if os.path.exists(self.service_account_json):
                with open(self.service_account_json, "r", encoding="utf-8") as f:
                    key_payload = json.load(f)
            else:
                try:
                    key_payload = json.loads(self.service_account_json)
                except json.JSONDecodeError:
                    pass
        elif os.getenv("NEWS_SVC_KEY"):                   # 환경변수 지원
            key_payload = json.loads(os.getenv("NEWS_SVC_KEY"))

        if not key_payload:
            # 인증 정보를 못 찾으면 Google Sheets 기능 무시
            return pd.DataFrame()

        try:
            creds = Credentials.from_service_account_info(
                key_payload,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets.readonly",
                    "https://www.googleapis.com/auth/drive.readonly",
                ],
            )
            gc = gspread.authorize(creds)
            worksheet = gc.open_by_key(self.sheet_id).sheet1
            rows = worksheet.get_all_records()  # list[dict]
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()

        # ---- 컬럼 정규화 ------------------------------------------
        df.columns = df.columns.str.strip()

        rename_map = {}
        for col in df.columns:
            low = col.lower()
            if any(k in low for k in ("title", "제목")):
                rename_map[col] = "제목"
            elif any(k in low for k in ("url", "link", "링크")):
                rename_map[col] = "URL"
            elif any(k in low for k in ("content", "summary", "내용", "요약")):
                rename_map[col] = "요약"
            elif any(k in low for k in ("date", "날짜", "time", "시각")):
                rename_map[col] = "날짜"
            elif any(k in low for k in ("source", "언론", "출처")):
                rename_map[col] = "출처"

        df.rename(columns=rename_map, inplace=True)
        if "제목" not in df.columns:
            df.rename(columns={df.columns[0]: "제목"}, inplace=True)

        # 필수 컬럼 기본값
        for col, default in (
            ("URL", ""),
            ("요약", df["제목"]),
            ("날짜", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("출처", "GoogleSheet"),
        ):
            if col not in df.columns:
                df[col] = default

        df = df[df["제목"].astype(str).str.strip() != ""].copy()
        return self._enrich_dataframe(df)

    # ===========================  RSS  ==============================
    def _fetch_rss_news(self, *, max_items: int = 25) -> pd.DataFrame:
        collected: List[Dict] = []

        for source, url in self.rss_feeds.items():
            try:
                feed = feedparser.parse(url)
            except Exception:
                continue

            for entry in feed.entries[:max_items]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                summary = entry.get("summary", entry.get("description", ""))
                published = entry.get("published", "")
                link = entry.get("link", "")

                record = {
                    "제목": title,
                    "요약": summary,
                    "날짜": self._parse_date(published),
                    "URL": link,
                    "출처": source,
                }
                collected.append(record)

        if not collected:
            return pd.DataFrame()
        df = pd.DataFrame(collected)
        return self._enrich_dataframe(df)

    # ======================  POST-PROCESSING  =======================
    def _enrich_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        • 키워드 추출 → '키워드'
        • 영향도 / SK관련도 스코어 계산
        • 회사 추정 & 카테고리 분류
        """
        df["키워드"] = df["제목"].apply(self._extract_keywords)
        df["중요도"] = df["제목"].apply(self._calc_importance)
        df["회사"]   = df["제목"].apply(self._extract_company)
        df["카테고리"] = df["제목"].apply(self._classify_category)
        df["SK관련도"] = df["제목"].apply(self._calc_sk_relevance)
        df["영향도"] = df["중요도"]
        return df

    # -----------------  util: keyword / scoring  --------------------
    def _extract_keywords(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        kws = [kw for kw in self.OIL_KEYWORDS if kw.lower() in text.lower()]
        return ", ".join(kws[:5]) if kws else ""

    def _calc_importance(self, text: str) -> int:
        if not isinstance(text, str):
            return 0
        core = ["SK", "영업이익", "실적", "손실", "투자", "합병"]
        score = sum(2 for w in core if w.lower() in text.lower())
        return min(score + 3, 10)

    def _calc_sk_relevance(self, text: str) -> int:
        if not isinstance(text, str):
            return 0
        text_l = text.lower()
        score = 5 if "sk" in text_l else 0
        score += 3 if "sk에너지" in text_l else 0
        if any(w in text_l for w in ("정유", "석유", "화학")):
            score += 2
        return min(score, 10)

    def _extract_company(self, text: str) -> str:
        if not isinstance(text, str):
            return "기타"
        companies = ["SK에너지", "SK", "GS칼텍스",
                     "HD현대오일뱅크", "S-Oil", "에쓰오일"]
        for c in companies:
            if c.lower() in text.lower():
                return c
        return "기타"

    def _classify_category(self, text: str) -> str:
        s = text.lower() if isinstance(text, str) else ""
        if any(k in s for k in ("sk", "sk에너지", "sk이노베이션")):
            return "SK관련"
        if any(k in s for k in ("손실", "적자", "비용", "원가", "보수", "중단")):
            return "비용절감"
        if any(k in s for k in ("영업이익", "매출", "수익", "흑자", "증가", "성장")):
            return "수익개선"
        if any(k in s for k in ("투자", "설비", "공장", "ESG", "수소", "확장")):
            return "전략변화"
        return "외부환경"

    @staticmethod
    def _parse_date(date_str: str) -> str:
        from dateutil import parser
        try:
            return parser.parse(date_str).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M")




# ==========================
# Gemini AI 인사이트 생성기
# ==========================

class GeminiInsightGenerator:
    def __init__(self, api_key=GEMINI_API_KEY):
        if GEMINI_AVAILABLE and api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def generate_financial_insight(self, financial_data):
        """재무데이터 → 경쟁사 분석 인사이트"""
        if not self.model:
            return "Gemini API를 사용할 수 없습니다. API 키를 확인해주세요."
        
        try:
            # 재무데이터를 텍스트로 변환
            data_str = financial_data.to_string() if hasattr(financial_data, 'to_string') else str(financial_data)
            
            prompt = f"""
다음은 SK에너지 중심의 재무데이터입니다:

{data_str}

당신은 SK에너지 내부 전략기획팀 소속으로,
경쟁사 대비 SK에너지의 **재무 및 사업 경쟁력**을 분석하여
향후 **사업 전략 수립 및 개선 방향**을 도출하는 것이 목표입니다.

다음 항목에 맞춰 **전략적 인사이트**를 도출해주세요:

## 1. 📊 SK에너지 현재 재무 상황 분석
- 최근 수익성 변화와 원인 진단
- 경쟁사(GS칼텍스 등) 대비 수익구조의 강점/약점
- 영업이익률, 순이익률, 원가율, 판관비율 등 주요 지표 비교

## 2. 🔍 경쟁사 대비 사업 경쟁력 분석
- 경쟁사 대비 원가 효율성, 수익성, 비용 구조 차이
- SK에너지가 개선하거나 강화할 수 있는 포인트 도출

## 3. 🧩 전략적 시사점 및 내부 개선 방향
- 단기적으로 재무 개선을 위해 우선 검토해야 할 영역
- 중장기적으로 경쟁력을 높이기 위한 조직 차원의 전략 제언

## 4. 📌 리스크 요인 및 감시 항목
- 현재 가장 큰 재무적/사업적 리스크
- 외부환경(유가, 정책 등)에 따른 리스크 민감도
- 내부적으로 반드시 모니터링해야 할 주요 지표

## 5. 🚀 향후 6개월 내 실질적 액션 플랜 제안
- 실행 가능한 내부 조치 3~5가지 제안
- KPI 기준 재설정 또는 목표 재정의 필요 여부

분석은 전문 컨설턴트 수준으로 해주시되, 실무자가 바로 보고 실행방안을 만들 수 있을 정도로 구체적이고 현실적인 조언을 포함해주세요.
"""
            
            response = self.model.generate_content(prompt)
            return response.text
        
        except Exception as e:
            return f"AI 인사이트 생성 중 오류가 발생했습니다: {e}"

    def generate_news_insight(self, news_keywords, news_samples):
        """뉴스데이터 → 동적 시장 인사이트"""
        if not self.model:
            return "Gemini API를 사용할 수 없습니다. API 키를 확인해주세요."
        
        try:
            keywords_text = ', '.join(news_keywords[:10]) if news_keywords else '키워드 없음'
            samples_text = str(news_samples[:3]) if news_samples else '뉴스 없음'
            
            prompt = f"""
SK에너지 관련 뉴스 분석:

주요 키워드: {keywords_text}
뉴스 샘플: {samples_text}

**동적 시장 인사이트**를 제공해주세요:

## 1. 📊 현재 시장 상황 진단
- 정유업계 전반적 동향
- SK에너지 관련 이슈 현황

## 2. 🎯 SK에너지에 미치는 영향
- 긍정적 요인
- 부정적 요인

## 3. 🔍 주요 기회요인과 위험요인
- 단기 기회 요인
- 주요 리스크 포인트

## 4. 🏢 경쟁사 대비 포지션
- 시장 내 상대적 위치
- 경쟁 우위/열위 요소

## 5. 🔮 향후 3-6개월 전망
- 예상 시나리오
- 주요 변수들

## 6. 💼 투자자/경영진을 위한 전략 제안
- 실행 가능한 대응 방안
- 모니터링해야 할 지표

실무진이 활용할 수 있는 구체적인 인사이트를 제공해주세요.
"""
            
            response = self.model.generate_content(prompt)
            return response.text
        
        except Exception as e:
            return f"AI 뉴스 인사이트 생성 중 오류가 발생했습니다: {e}"

# ==========================
# 차트 생성 함수들
# ==========================

def create_sk_radar_chart(chart_df):
    """SK에너지 중심 레이더 차트 (정규화 버전)"""
    if chart_df.empty or not PLOTLY_AVAILABLE:
        return None

    companies = chart_df['회사'].unique() if '회사' in chart_df.columns else []
    metrics = chart_df['지표'].unique() if '지표' in chart_df.columns else []

    # 지표별 정규화 수행
    normalized_df = chart_df.copy()
    for metric in metrics:
        metric_mask = normalized_df['지표'] == metric
        metric_values = normalized_df.loc[metric_mask, '수치']
        min_val = metric_values.min()
        max_val = metric_values.max()
        if max_val != min_val:
            normalized_df.loc[metric_mask, '정규화수치'] = (metric_values - min_val) / (max_val - min_val)
        else:
            normalized_df.loc[metric_mask, '정규화수치'] = 0.5

    fig = go.Figure()

    for company in companies:
        company_data = normalized_df[normalized_df['회사'] == company]
        values = company_data['정규화수치'].tolist()
        values.append(values[0])  # 닫힌 도형

        theta_labels = list(metrics) + [metrics[0]]

        # 파스텔 색상 적용
        color = get_company_color(company, companies)

        # SK에너지는 특별한 스타일
        if 'SK' in company:
            line_width = 5
            marker_size = 12
            name_style = f"**{company}**"
        else:
            line_width = 3
            marker_size = 8
            name_style = company

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=theta_labels,
            fill='toself',
            name=name_style,
            line=dict(width=line_width, color=color),
            marker=dict(size=marker_size, color=color)
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickmode='linear',
                tick0=0,
                dtick=0.2,
                tickfont=dict(size=14)
            ),
            angularaxis=dict(
                tickfont=dict(size=16)
            )
        ),
        title="🎯 SK에너지 vs 경쟁사 수익성 지표 비교 (정규화)",
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=14)
        ),
        title_font_size=20,
        font=dict(size=14)
    )

    return fig

# ==========================
# DART 출처 테이블 생성 함수 (링크 개선)
# ==========================

def create_dart_source_table(dart_collector, collected_companies, analysis_year):
    """DART 출처 정보 테이블 생성 (클릭 가능한 링크)"""
    if not hasattr(dart_collector, 'source_tracking') or not dart_collector.source_tracking:
        return pd.DataFrame()
    
    source_data = []
    for company, info in dart_collector.source_tracking.items():
        if company in collected_companies:
            # 유효한 DART 링크 생성
            rcept_no = info.get('rcept_no', 'N/A')
            if rcept_no and rcept_no != 'N/A':
                dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            else:
                dart_url = "https://dart.fss.or.kr"
            
            source_data.append({
                '회사명': company,
                '보고서 유형': info.get('report_type', '재무제표'),
                '연도': info.get('year', analysis_year),
                '회사코드': info.get('company_code', 'N/A'),
                'DART 바로가기': dart_url,
                '접수번호': rcept_no
            })
    
    return pd.DataFrame(source_data)

# ==========================
# PDF 생성 함수 (쪽번호 추가 + 오류 수정)
# ==========================
# ---------------------------------------------------------------------
#  PDF - ONE-SHOT REPLACEMENT
#  붙여 넣을 위치 : 기존 create_enhanced_pdf_report 정의 자리
# ---------------------------------------------------------------------
def create_enhanced_pdf_report(
        financial_data=None,
        news_data=None,
        insights:str|None=None,
        selected_charts:list|None=None
):
    """
    • 제목  : 맑은고딕 Bold 20pt
    • 본문  : 신명조 12pt, 줄간격 170 %
    • AI 인사이트 : 번호 붙은 제목은 굵게, 본문은 평문(마크다운 기호 제거)
    • 표     : ReportLab Table 로 출력
    • 차트   : Plotly figure 리스트(selected_charts) PNG 로 삽입
    """
    if not PDF_AVAILABLE:
        st.error("reportlab 라이브러리가 필요합니다.")
        return None

    # ---------- 1. 내부 헬퍼 ----------
    import re, tempfile
    def _clean_ai_text(raw:str)->list[tuple[str,str]]:
        """
        마크다운 기호 제거 후
        ('title'|'body', line) 형식으로 반환
        """
        raw = re.sub(r'[*_`#>~]', '', raw)      # 굵게·이탤릭·표시 제거
        blocks = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if re.match(r'^\d+(\.\d+)*\s', ln):    # 1.  / 1.1 처럼 시작
                blocks.append(('title', ln))
            else:
                blocks.append(('body', ln))
        return blocks

    def _ascii_block_to_table(lines:list[str]):
        """
        파이프(|) 로 만든 ASCII 표 → ReportLab Table 로 변환
        lines : '|' 가 포함된 연속 행 리스트
        반환    : reportlab.platypus.Table 객체
        """
        header = [c.strip() for c in lines[0].split('|') if c.strip()]
        data   = []
        for ln in lines[2:]:         # 구분선(----) 제외
            cols = [c.strip() for c in ln.split('|') if c.strip()]
            if len(cols)==len(header):
                data.append(cols)
        if not data:
            return None
        tbl = Table([header]+data)
        tbl.setStyle(TableStyle([
            ('GRID',  (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#E31E24')),
            ('TEXTCOLOR',(0,0),(-1,0), colors.white),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('FONTNAME',(0,0),(-1,0),'KoreanBold'),
            ('FONTNAME',(0,1),(-1,-1),'Korean'),
            ('FONTSIZE',(0,0),(-1,-1),8),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),
                [colors.whitesmoke, colors.HexColor('#F7F7F7')]),
        ]))
        return tbl
    # ---------- 2. 폰트 등록 ----------
# 3-1. 사용할 글꼴 경로(윈도·mac·리눅스) ― 필요한 것만 남겨도 무방
# ---------- 2. 폰트 등록 ----------
    font_paths = {
        "Korean": [                                 # ← 추가
            "C:/Windows/Fonts/malgun.ttf",          # 본문용 가변-폭
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        ],
        "KoreanBold": [
            "C:/Windows/Fonts/malgunbd.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc"
        ],
        "KoreanSerif": [
            "C:/Windows/Fonts/batang.ttc",
            "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf"
        ]
    }

    for name, paths in font_paths.items():
        for p in paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont(name, p))
                except Exception:
                    # 이미 등록돼 있거나 다른 이유로 실패한 경우 무시
                    pass
                break  # 첫 번째로 성공(또는 시도)한 경로 뒤에는 반복 종료

    # ---------- 3. 스타일 ----------
    styles = getSampleStyleSheet()
    TITLE_STYLE = ParagraphStyle(
        'TITLE',
        fontName='KoreanBold' if 'KoreanBold' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold',
        fontSize=20,
        leading=34,
        spaceAfter=18
    )
    HEADING_STYLE = ParagraphStyle(
        'HEADING',
        fontName='KoreanBold' if 'KoreanBold' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold',
        fontSize=14,
        leading=23.8,
        textColor=colors.HexColor('#E31E24'),
        spaceBefore=16,
        spaceAfter=10
    )
    BODY_STYLE = ParagraphStyle(
        'BODY',
        fontName='KoreanSerif' if 'KoreanSerif' in pdfmetrics.getRegisteredFontNames() else 'Times-Roman',
        fontSize=12,
        leading=20.4,
        spaceAfter=6
    )

    # ---------- 4. PDF 작성 ----------
    buff = io.BytesIO()
    def _page_no(canvas, doc):
        canvas.setFont('Helvetica', 9)
        canvas.drawCentredString(letter[0]/2, 18, f"- {canvas.getPageNumber()} -")

    doc = SimpleDocTemplate(buff, pagesize=letter,
                            leftMargin=54, rightMargin=54,
                            topMargin=54, bottomMargin=54)

    story = []

    # 4-1 제목 & 메타
    story.append(Paragraph("SK에너지 경쟁사 분석 보고서", TITLE_STYLE))
    story.append(Paragraph("보고일자: 2024년 10월 26일    "
                           "보고대상: SK에너지 전략기획팀    "
                           "보고자: 전략기획팀", BODY_STYLE))
    story.append(Spacer(1, 12))

    # 4-2 재무 표
    if financial_data is not None and not financial_data.empty:
        story.append(Paragraph("1. 재무분석 결과", HEADING_STYLE))
        # '_원시값' 제외
        df_disp = financial_data[[c for c in financial_data.columns
                                  if not c.endswith('_원시값')]].copy()
        tbl = Table([df_disp.columns.tolist()] + df_disp.values.tolist(),
                    repeatRows=1)
        tbl.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,colors.black),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F2F2F2')),
            ('FONTNAME',(0,0),(-1,0),'KoreanBold'),
            ('FONTNAME',(0,1),(-1,-1),'KoreanSerif'),
            ('FONTSIZE',(0,0),(-1,-1),8),
            ('ALIGN',(0,0),(-1,-1),'CENTER')
        ]))
        story.append(tbl)
        story.append(Spacer(1, 18))

    # 4-3 뉴스 요약
    if news_data is not None and not news_data.empty:
        story.append(Paragraph("2. 최신 뉴스 하이라이트", HEADING_STYLE))
        for i, title in enumerate(news_data["제목"].head(5), 1):
            story.append(Paragraph(f"{i}. {title}", BODY_STYLE))
        story.append(Spacer(1, 12))

    # 4-4 AI 인사이트
    if insights:
        story.append(PageBreak())
        story.append(Paragraph("3. AI 인사이트", HEADING_STYLE))
        blocks = _clean_ai_text(insights)
        ascii_buf = []
        for typ, ln in blocks:
            if '|' in ln:                 # ASCII 표 후보
                ascii_buf.append(ln)
                continue
            # 먼저 버퍼 flush
            if ascii_buf:
                tbl = _ascii_block_to_table(ascii_buf)
                if tbl: story.append(tbl)
                story.append(Spacer(1, 12))
                ascii_buf.clear()
            # 정상 텍스트
            if typ=='title':
                story.append(Paragraph(f"<b>{ln}</b>", BODY_STYLE))
            else:
                story.append(Paragraph(ln, BODY_STYLE))
        # 끝에 남은 표 flush
        if ascii_buf:
            tbl = _ascii_block_to_table(ascii_buf)
            if tbl: story.append(tbl)

    # 4-5 차트
    if selected_charts and PLOTLY_AVAILABLE:
        story.append(PageBreak())
        story.append(Paragraph("4. 시각화 차트", HEADING_STYLE))
        for fig in selected_charts:
            try:
                img_bytes = fig.to_image(format="png", width=700, height=400)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp.write(img_bytes); tmp_path = tmp.name
                story.append(RLImage(tmp_path, width=500, height=280))
                story.append(Spacer(1, 16))
                os.unlink(tmp_path)
            except Exception as e:
                story.append(Paragraph(f"차트 삽입 오류: {e}", BODY_STYLE))

    # 4-6 빌드
    doc.build(story, onFirstPage=_page_no, onLaterPages=_page_no)
    buff.seek(0)
    return buff.getvalue()

    if not PDF_AVAILABLE:
        st.error("PDF 생성을 위해 reportlab 라이브러리가 필요합니다.")
        return None

    try:
        pdf_buffer = io.BytesIO()
        
        # 쪽번호가 있는 페이지 템플릿 생성
        def add_page_number(canvas, doc):
            """쪽번호 추가 함수"""
            canvas.saveState()
            canvas.setFont('Helvetica', 10)
            page_num = canvas.getPageNumber()
            text = f"- {page_num} -"
            canvas.drawString(letter[0]/2 - 10, 30, text)
            canvas.restoreState()

        doc = SimpleDocTemplate(
            pdf_buffer, 
            pagesize=letter,
            topMargin=72,
            bottomMargin=72
        )

        # 한글 폰트 등록
        korean_font_registered = False
        korean_font_paths = [
            'C:/Windows/Fonts/malgun.ttf',
            'C:/Windows/Fonts/gulim.ttc',
            'C:/Windows/Fonts/NanumGothic.ttf',
            '/System/Library/Fonts/AppleGothic.ttf',
            '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
        ]
        
        for font_path in korean_font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('KoreanSerif', font_path))
                    korean_font_registered = True
                    break
                except:
                    continue

        # 스타일 설정
        styles = getSampleStyleSheet()
        
        # 한글 지원 스타일
        title_style = ParagraphStyle(
            'KoreanTitle',
            parent=styles['Title'],
            fontName='KoreanBold' if korean_font_registered else 'Helvetica-Bold',
            fontSize=20,
            textColor=colors.Color(227/255, 30/255, 36/255),
            spaceAfter=30,
            encoding='utf-8'
        )
        
        heading_style = ParagraphStyle(
            'KoreanHeading',
            parent=styles['Heading1'],
            fontName='KoreanBold' if korean_font_registered else 'Helvetica-Bold',
            fontSize=16,
            textColor=colors.Color(227/255, 30/255, 36/255),
            spaceBefore=20,
            spaceAfter=15,
            encoding='utf-8'
        )
        
        normal_style = ParagraphStyle(
            'KoreanNormal',
            parent=styles['Normal'],
            fontName='KoreanSerif' if korean_font_registered else 'Helvetica',
            fontSize=11,
            spaceAfter=12,
            encoding='utf-8'
        )

        story = []

        # 제목
        story.append(Paragraph("⚡ SK에너지 경쟁사 분석 보고서", title_style))
        story.append(Spacer(1, 20))

        # 생성 정보
        story.append(Paragraph(f"📅 생성일시: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}", normal_style))
        story.append(Paragraph("🎯 데이터 출처: DART API (실제 재무데이터)", normal_style))
        story.append(Paragraph("🤖 AI 분석: Google Gemini 1.5", normal_style))
        story.append(Spacer(1, 30))

        section_number = 1

        # 재무분석 섹션
        if financial_data is not None and not financial_data.empty:
            story.append(Paragraph(f"{section_number}. 📊 재무분석 결과", heading_style))
            story.append(Spacer(1, 15))

            # 테이블 생성 (한글 지원)
            table_data = []
            headers = [str(col)[:20] for col in financial_data.columns if not col.endswith('_원시값')]
            table_data.append(headers)

            # 데이터 행 추가
            for _, row in financial_data.head(15).iterrows():
                row_data = []
                for col in financial_data.columns:
                    if not col.endswith('_원시값'):
                        cell_value = row[col]
                        if pd.isna(cell_value):
                            cell_str = '-'
                        else:
                            cell_str = str(cell_value)[:20]
                        row_data.append(cell_str)
                table_data.append(row_data)

            # 테이블 스타일링
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(227/255, 30/255, 36/255)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'KoreanSerif' if korean_font_registered else 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('FONTNAME', (0, 1), (-1, -1), 'KoreanSerif' if korean_font_registered else 'Helvetica'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
            ]))

            story.append(table)
            story.append(Spacer(1, 25))
            section_number += 1

        # 뉴스분석 섹션
        if news_data is not None and not news_data.empty:
            story.append(Paragraph(f"{section_number}. 📰 뉴스분석 결과", heading_style))
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"총 {len(news_data)}건의 뉴스 분석", normal_style))
            story.append(Spacer(1, 10))

            # 상위 5개 뉴스만 표시
            for idx, (_, row) in enumerate(news_data.head(5).iterrows()):
                title = str(row.get('제목', 'N/A'))[:50] + "..."
                story.append(Paragraph(f"{idx+1}. {title}", normal_style))
                story.append(Spacer(1, 5))
            
            section_number += 1

        # AI 인사이트 섹션
        if insights:
            story.append(PageBreak())
            story.append(Paragraph(f"{section_number}. 🤖 AI 인사이트", heading_style))
            story.append(Spacer(1, 15))

            # 인사이트 처리
            insight_text = str(insights)
            lines = insight_text.split('\n')
            
            for line in lines:
                if line.strip():
                    # 제목 처리
                    if line.startswith('##'):
                        title_text = line.replace('##', '').strip()
                        story.append(Paragraph(title_text, heading_style))
                    else:
                        # 일반 텍스트
                        clean_line = line.strip()
                        if clean_line:
                            story.append(Paragraph(clean_line, normal_style))
                    story.append(Spacer(1, 8))

        # 차트 섹션 (선택사항)
        if selected_charts and PLOTLY_AVAILABLE:
            story.append(Paragraph(f"{section_number}. 📊 차트 분석", heading_style))
            story.append(Spacer(1, 15))
            
            # Plotly 차트를 이미지로 변환하여 삽입
            for idx, fig in enumerate(selected_charts):
                try:
                    import tempfile
                    img_bytes = fig.to_image(format="png", width=800, height=500)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                        tmp.write(img_bytes)
                        tmp_path = tmp.name
                    
                    story.append(RLImage(tmp_path, width=500, height=300))
                    story.append(Spacer(1, 20))
                    
                    # 임시 파일 정리
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                        
                except Exception as e:
                    story.append(Paragraph(f"차트 {idx+1} 삽입 오류: {str(e)}", normal_style))
                    story.append(Spacer(1, 10))

        # 푸터
        story.append(Spacer(1, 50))
        story.append(Paragraph("🔗 본 보고서는 SK에너지 경쟁사 분석 대시보드에서 자동 생성되었습니다.", normal_style))
        story.append(Paragraph("📊 실제 DART API 데이터 + Google Gemini AI 분석 기반", normal_style))

        # PDF 빌드 (쪽번호 포함)
        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()

    except Exception as e:
        st.error(f"PDF 생성 오류: {e}")
        return None

def create_excel_report(financial_data=None, news_data=None, insights=None):
    """Excel 보고서 생성"""
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 재무분석 시트
            if financial_data is not None and not financial_data.empty:
                # '_원시값' 컬럼 제거
                clean_financial = financial_data[[col for col in financial_data.columns if not col.endswith('_원시값')]]
                clean_financial.to_excel(writer, sheet_name='재무분석', index=False)
            
            # 뉴스분석 시트
            if news_data is not None and not news_data.empty:
                news_data.to_excel(writer, sheet_name='뉴스분석', index=False)
            
            # 인사이트 시트
            if insights:
                insight_df = pd.DataFrame({
                    '구분': ['AI 인사이트'],
                    '내용': [str(insights)]
                })
                insight_df.to_excel(writer, sheet_name='AI인사이트', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Excel 생성 오류: {e}")
        return None

# ==========================
# 이메일 발송 함수들
# ==========================

def create_email_ui():
    """이메일 주소 입력 UI"""
    email_method = st.radio(
        "이메일 입력 방식",
        ["🎯 도메인 선택", "✏️ 직접 입력"],
        horizontal=True
    )
    
    if email_method == "🎯 도메인 선택":
        col1, col2 = st.columns([1, 2])
        with col1:
            email_id = st.text_input("이메일 아이디", placeholder="홍길동")
        with col2:
            domains = [
                "naver.com", "gmail.com", "daum.net", "kakao.com",
                "sk.com", "skenergy.com", "hanmail.net", "outlook.com",
                "yahoo.com", "hotmail.com", "company.co.kr"
            ]
            selected_domain = st.selectbox("도메인 선택", domains)
        
        if email_id:
            complete_email = f"{email_id}@{selected_domain}"
            return complete_email
        else:
            return None
    else:
        return st.text_input("이메일 주소", placeholder="user@company.com")

def send_email_with_attachment(email_address, file_bytes, filename):
    """이메일로 파일 발송"""
    try:
        # Gmail SMTP 설정 (예시)
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = "your_email@gmail.com"  # 실제 이메일로 변경 필요
        sender_password = "your_password"  # 실제 비밀번호로 변경 필요
        
        msg = EmailMessage()
        msg['Subject'] = f'SK에너지 경쟁사 분석 보고서 - {filename}'
        msg['From'] = sender_email
        msg['To'] = email_address
        
        msg.set_content(f"""
안녕하세요,

SK에너지 경쟁사 분석 보고서를 첨부파일로 보내드립니다.

생성일시: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
파일명: {filename}

감사합니다.
        """)
        
        # 파일 첨부
        if filename.endswith('.pdf'):
            msg.add_attachment(file_bytes, maintype='application', subtype='pdf', filename=filename)
        else:
            msg.add_attachment(file_bytes, maintype='application', subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=filename)
        
        # 실제 이메일 발송은 보안상 비활성화
        # with smtplib.SMTP(smtp_server, smtp_port) as server:
        #     server.starttls()
        #     server.login(sender_email, sender_password)
        #     server.send_message(msg)
        
        st.success(f"✅ {email_address}로 보고서가 발송 준비되었습니다!")
        st.info("📧 실제 발송 기능은 보안상 비활성화되어 있습니다. 파일을 다운로드해서 직접 전송해주세요.")
        
    except Exception as e:
        st.error(f"이메일 발송 중 오류: {e}")

# ==========================
# 메인 함수
# ==========================
def main():
    """메인 함수"""
    st.title("⚡ SK에너지 경쟁사 분석 대시보드")
    st.markdown("**DART API + RSS 뉴스 + 구글시트 + Gemini AI 인사이트 통합**")
    
    # 요구사항 맞춤 탭 구성
    tabs = st.tabs(["📈 재무분석 (DART 자동)", "📁 수동 XBRL 업로드", "📰 뉴스분석", "📄 보고서 생성"])
    
    # ==========================
    # 탭1: 재무분석 (DART 자동화) + AI 인사이트 + 새로고침
    # ==========================
    
    with tabs[0]:
        st.subheader("📈 재무분석 (DART 자동화)")
        st.write("**기업을 선택하고 분석 버튼을 누르면 DART에서 가져온 보고서를 바탕으로 분석하고 시각화/차트를 그려줍니다.**")
        
        # 기업 선택
        selected_companies = st.multiselect(
            "분석할 기업 선택",
            ["SK에너지", "GS칼텍스", "HD현대오일뱅크", "S-Oil"],
            default=["SK에너지", "GS칼텍스"],
            key="companies_selection"
        )
        
        analysis_year = st.selectbox("분석 연도", ["2024", "2023", "2022"], index=0)
        
        # 분석 버튼
        if st.button("🚀 DART 자동분석 시작", type="primary"):
            if not selected_companies:
                st.error("분석할 기업을 선택해주세요.")
            else:
                with st.spinner("DART API에서 실제 데이터 수집 중..."):
                    # DART API 수집 (프로그레스바 포함)
                    dart_collector = DartAPICollector(DART_API_KEY)
                    sk_processor = SKFinancialDataProcessor()
                    
                    dataframes = collect_financial_data_with_progress(
                        dart_collector, sk_processor, selected_companies, analysis_year
                    )
                    
                    if dataframes:
                        # 데이터 병합
                        merged_df = sk_processor.merge_company_data(dataframes)
                        st.session_state.financial_data = merged_df
                        st.session_state.selected_companies = selected_companies
                        
                        # Gemini AI 재무 인사이트 생성
                        gemini_generator = GeminiInsightGenerator()
                        with st.spinner("🤖 AI 인사이트 생성 중..."):
                            financial_insight = gemini_generator.generate_financial_insight(merged_df)
                            st.session_state.financial_insight = financial_insight
                        
                        st.success(f"✅ {len(selected_companies)}개 회사 DART 분석 완료!")
                    else:
                        st.error("데이터 수집에 실패했습니다.")
        
        # 재무분석 결과 표시
        if st.session_state.financial_data is not None and not st.session_state.financial_data.empty:
            st.markdown("---")
            
            # 새로고침 버튼 추가
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("💰 재무분석 결과")
            with col2:
                if st.button("🔄 AI 인사이트 새로고침", key="refresh_financial_insight"):
                    gemini_generator = GeminiInsightGenerator()
                    with st.spinner("🤖 AI 인사이트 재생성 중..."):
                        financial_insight = gemini_generator.generate_financial_insight(st.session_state.financial_data)
                        st.session_state.financial_insight = financial_insight
                        st.rerun()
            
            # 재무제표 표시 (_원시값 컬럼 완전 제거)
            display_df = st.session_state.financial_data.copy()
            display_cols = [col for col in display_df.columns if not col.endswith('_원시값')]
            display_df = display_df[display_cols]
            
            st.dataframe(display_df, use_container_width=True)
            
            # DART 출처 정보 표시 (링크 개선)
            if st.session_state.selected_companies:
                dart_collector = DartAPICollector(DART_API_KEY)
                source_df = create_dart_source_table(dart_collector, st.session_state.selected_companies, analysis_year)
                if not source_df.empty:
                    st.subheader("📊 DART 전자공시시스템 출처")
                    st.dataframe(
                        source_df,
                        use_container_width=True,
                        column_config={
                            "DART 바로가기": st.column_config.LinkColumn(
                                "🔗 DART 바로가기",
                                help="클릭하면 해당 보고서로 이동합니다"
                            )
                        }
                    )
                    st.caption("💡 금융감독원 전자공시시스템(https://dart.fss.or.kr)에서 제공하는 공식 재무제표 데이터입니다.")
            
            # 시각화/차트
            st.subheader("📊 시각화/차트")
            
            # 비율 데이터만 추출하여 차트 생성
            ratio_data = display_df[display_df['구분'].str.contains('%', na=False)]
            
            if not ratio_data.empty and PLOTLY_AVAILABLE:
                # 차트용 데이터 준비
                chart_data = []
                companies = [col for col in ratio_data.columns if col != '구분']
                
                for _, row in ratio_data.iterrows():
                    for company in companies:
                        value_str = str(row[company]).replace('%', '')
                        try:
                            value = float(value_str)
                            chart_data.append({
                                '지표': row['구분'],
                                '회사': company,
                                '수치': value
                            })
                        except:
                            continue
                
                if chart_data:
                    chart_df = pd.DataFrame(chart_data)
                    
                    # SK에너지 강조 막대차트
                    fig1 = create_sk_bar_chart(chart_df)
                    if fig1:
                        st.plotly_chart(fig1, use_container_width=True)
                    
                    # SK에너지 중심 레이더차트
                    fig2 = create_sk_radar_chart(chart_df)
                    if fig2:
                        st.plotly_chart(fig2, use_container_width=True)
            
            # 분기별 차트 (프로그레스바 개선)
            st.subheader("📈 분기별 차트")
            
            if st.session_state.selected_companies:
                quarterly_collector = QuarterlyDataCollector(DartAPICollector(DART_API_KEY))
                quarterly_data_list = []
                
                for company in st.session_state.selected_companies:
                    quarterly_df = quarterly_collector.collect_quarterly_data(company, int(analysis_year))
                    if not quarterly_df.empty:
                        quarterly_data_list.append(quarterly_df)
                
                if quarterly_data_list:
                    # 분기별 데이터 통합
                    quarterly_merged = pd.concat(quarterly_data_list, ignore_index=True)
                    st.session_state.quarterly_data = quarterly_merged
                    
                    fig_trend = create_quarterly_trend_chart(quarterly_merged)
                    if fig_trend:
                        st.plotly_chart(fig_trend, use_container_width=True)
            
            # Gemini AI 재무 인사이트
            if st.session_state.financial_insight:
                st.subheader("🤖 AI 재무 인사이트")
                st.markdown(st.session_state.financial_insight)
    
    # ==========================
    # 탭2: 수동 XBRL 업로드
    # ==========================
    
# ==========================
# 탭2: 수동 XBRL 업로드 (오류 수정)
# ==========================

    with tabs[1]:
        st.subheader("📁 수동 XBRL/XML 파일 업로드")
        st.write("**XBRL/XML 파일을 직접 업로드하여 재무제표를 분석합니다.**")
        
        processor = FinancialDataProcessor()
        
        # 다중 파일 업로드
        uploaded_files = st.file_uploader(
            "XBRL/XML 파일들을 업로드하세요 (여러 개 선택 가능)",
            type=['xbrl', 'xml'],
            accept_multiple_files=True,
            key="manual_upload"
        )
        
        if uploaded_files:
            st.subheader("📊 업로드된 파일 처리")
            dataframes = []
            
            for uploaded_file in uploaded_files:
                st.write(f"🔄 처리 중: {uploaded_file.name}")
                df = processor.load_file(uploaded_file)
                
                if df is not None:
                    dataframes.append(df)
                    st.success(f"✅ {uploaded_file.name} 처리 완료")
                    
                    # 개별 회사 데이터 미리보기
                    with st.expander(f"📋 {uploaded_file.name} 상세 데이터"):
                        st.dataframe(df, use_container_width=True)
                else:
                    st.error(f"❌ {uploaded_file.name} 처리 실패")
            
            if dataframes:
                # 경쟁사 비교 분석
                st.subheader("🏢 경쟁사 비교 분석")
                
                # merged_df 초기화 (오류 수정)
                merged_df = None
                
                if len(dataframes) == 1:
                    st.write("**📋 단일 회사 손익계산서**")
                    st.dataframe(dataframes[0], use_container_width=True)
                    st.session_state.manual_financial_data = dataframes[0]  # 단일 회사도 merged_df로 설정
                else:
                    # 다중 회사 비교
                    merged_df = processor.merge_company_data(dataframes)
                    st.write("**📊 경쟁사 비교 손익계산서**")
                    st.dataframe(merged_df, use_container_width=True)
                    st.session_state.manual_financial_data = merged_df
                
                # AI 분석 리포트 (merged_df가 정의된 후에 실행)
                if merged_df is not None and not merged_df.empty:
                    st.subheader("💡 AI 분석 리포트")
                    report = processor.create_comparison_report(merged_df)
                    st.text(report)
                else:
                    st.error("❌ 비교 분석을 위한 데이터가 없습니다.")

    # ==========================
    # 탭3: 뉴스분석 (구글시트 + RSS 통합 + 새로고침)
    # ==========================
    
    with tabs[2]:
        st.subheader("📰 실시간 뉴스 분석")
        st.write("**구글시트 자동화 뉴스 + 국내 주요 경제·산업 RSS를 수집해 SK에너지와 경쟁사 동향을 모니터링합니다.**")
        
        # 뉴스 수집 버튼
        if st.button("🔄 통합 뉴스 수집/갱신", type="primary", key="collect_news"):
            news_collector = SKNewsCollector()
            news_df = news_collector.collect_news()

            
            if not news_df.empty:
                st.session_state.news_data = news_df
                
                # Gemini AI 뉴스 인사이트 생성
                gemini_generator = GeminiInsightGenerator()
                with st.spinner("🤖 뉴스 AI 인사이트 생성 중..."):
                    keywords_set = set()
                    for kw_list in news_df["키워드"].dropna():
                        keywords_set.update([kw.strip() for kw in str(kw_list).split(",")])
                    
                    news_insight = gemini_generator.generate_news_insight(
                        list(keywords_set),
                        news_df["제목"].tolist()
                    )
                    st.session_state.news_insight = news_insight
                
                st.success(f"✅ 총 {len(news_df)}개 뉴스 통합 수집 완료!")
            else:
                st.warning("관련 뉴스를 찾지 못했습니다.")
        
        # 수집된 뉴스 데이터 표시
        if st.session_state.news_data is not None:
            # 새로고침 버튼 추가
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("📋 수집된 뉴스 목록")
            with col2:
                if st.button("🔄 AI 인사이트 새로고침", key="refresh_news_insight"):
                    gemini_generator = GeminiInsightGenerator()
                    with st.spinner("🤖 뉴스 AI 인사이트 재생성 중..."):
                        keywords_set = set()
                        for kw_list in st.session_state.news_data["키워드"].dropna():
                            keywords_set.update([kw.strip() for kw in str(kw_list).split(",")])
                        
                        news_insight = gemini_generator.generate_news_insight(
                            list(keywords_set),
                            st.session_state.news_data["제목"].tolist()
                        )
                        st.session_state.news_insight = news_insight
                        st.rerun()
            
            st.dataframe(st.session_state.news_data, use_container_width=True)
            
            # 카테고리 분포 차트
            #if PLOTLY_AVAILABLE:
                #news_collector = SKNewsCollector()
                #fig_news = news_collector.create_keyword_analysis(st.session_state.news_data)
                #if fig_news:
                  #  st.plotly_chart(fig_news, use_container_width=True)
            
            # Gemini AI 뉴스 인사이트
            if st.session_state.news_insight:
                st.subheader("🤖 AI 뉴스 인사이트")
                st.markdown(st.session_state.news_insight)
    
    # ==========================
    # 탭4: 보고서 생성 및 이메일 발송 (개선된 UI + PDF 쪽번호)
    # ==========================
    
    with tabs[3]:
        st.subheader("📄 통합 보고서 생성 & 이메일 발송")
        
        # 2열 레이아웃: PDF 생성 + 이메일 입력
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.write("**📥 보고서 다운로드**")
            # 보고서 형식 선택
            report_format = st.radio("파일 형식 선택", ["PDF", "Excel"], horizontal=True)
            
            if st.button("📥 보고서 생성", type="primary", key="make_report"):
                # 데이터 우선순위: DART 자동 > 수동 업로드
                financial_data_for_report = None
                if st.session_state.financial_data is not None and not st.session_state.financial_data.empty:
                    financial_data_for_report = st.session_state.financial_data
                elif st.session_state.manual_financial_data is not None and not st.session_state.manual_financial_data.empty:
                    financial_data_for_report = st.session_state.manual_financial_data
                
                with st.spinner("📄 보고서 생성 중..."):
                    if report_format == "PDF":
                        file_bytes = create_enhanced_pdf_report(
                            financial_data=financial_data_for_report,
                            news_data=st.session_state.news_data,
                            insights=st.session_state.financial_insight or st.session_state.news_insight
                        )
                        filename = "SK_Energy_Analysis_Report.pdf"
                        mime_type = "application/pdf"
                    else:
                        file_bytes = create_excel_report(
                            financial_data=financial_data_for_report,
                            news_data=st.session_state.news_data,
                            insights=st.session_state.financial_insight or st.session_state.news_insight
                        )
                        filename = "SK_Energy_Analysis_Report.xlsx"
                        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    
                    if file_bytes:
                        # 세션에 파일 정보 저장
                        st.session_state.generated_file = file_bytes
                        st.session_state.generated_filename = filename
                        st.session_state.generated_mime = mime_type
                        
                        st.download_button(
                            label="⬇️ 보고서 다운로드",
                            data=file_bytes,
                            file_name=filename,
                            mime=mime_type
                        )
                        st.success("✅ 보고서가 성공적으로 생성되었습니다!")
                    else:
                        st.error("❌ 보고서 생성에 실패했습니다.")
        
        with col2:
            st.write("**📧 이메일 자동 발송**")
            
            # 이메일 주소 입력 UI
            email_method = st.radio(
                "이메일 입력 방식",
                ["🎯 도메인 선택", "✏️ 직접 입력"],
                horizontal=True
            )
            
            complete_email = None
            
            if email_method == "🎯 도메인 선택":
                col_id, col_domain = st.columns([1, 2])
                with col_id:
                    email_id = st.text_input("이메일 아이디", placeholder="홍길동", key="email_id")
                with col_domain:
                    domains = [
                        "naver.com", "gmail.com", "daum.net", "kakao.com",
                        "sk.com", "skenergy.com", "hanmail.net", "outlook.com",
                        "yahoo.com", "hotmail.com", "company.co.kr"
                    ]
                    selected_domain = st.selectbox("도메인 선택", domains)
                
                if email_id:
                    complete_email = f"{email_id}@{selected_domain}"
                    st.success(f"📧 발송할 이메일: **{complete_email}**")
            else:
                complete_email = st.text_input("이메일 주소", placeholder="user@company.com", key="email_direct")
            
            # 이메일 발송 버튼
            if complete_email and st.button("📧 이메일로 발송", key="send_email"):
                if hasattr(st.session_state, 'generated_file') and st.session_state.generated_file:
                    # 실제 이메일 발송 대신 다운로드 링크 제공
                    st.success(f"✅ {complete_email}로 발송 준비 완료!")
                    st.info("📧 실제 발송 기능은 보안상 비활성화되어 있습니다. 아래 다운로드 버튼을 사용해주세요.")
                    
                    st.download_button(
                        label=f"📥 {st.session_state.generated_filename} 다운로드",
                        data=st.session_state.generated_file,
                        file_name=st.session_state.generated_filename,
                        mime=st.session_state.generated_mime
                    )
                else:
                    st.warning("먼저 보고서를 생성해주세요.")

# 메인 실행
if __name__ == "__main__":
    main()
