import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI
import calendar
import json

# 페이지 설정
st.set_page_config(
    page_title="스마트 가계부",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일 적용
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        height: 3em;
        margin-top: 1em;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1em;
        margin: 0.5em 0;
    }
    .main-header {
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2em;
    }
    </style>
""", unsafe_allow_html=True)

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    
    # 카테고리 테이블 생성
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            budget REAL DEFAULT 0,
            color TEXT
        )
    ''')
    
    # 지출 테이블 생성
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            payment_method TEXT,
            is_fixed_expense BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    # 기본 카테고리 추가
    default_categories = [
        ('식비', 500000, '#FF6B6B'),
        ('교통', 200000, '#4ECDC4'),
        ('주거', 800000, '#45B7D1'),
        ('통신', 100000, '#96CEB4'),
        ('의료', 200000, '#D4A5A5'),
        ('교육', 300000, '#9B89B3'),
        ('여가', 400000, '#FAD02E'),
        ('기타', 200000, '#95A5A6')
    ]
    
    for cat in default_categories:
        try:
            c.execute('INSERT INTO categories (name, budget, color) VALUES (?, ?, ?)', cat)
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()

# 카테고리 가져오기
def get_categories():
    conn = sqlite3.connect('expenses.db')
    categories = pd.read_sql_query('SELECT * FROM categories', conn)
    conn.close()
    return categories

# LLM 분석 함수 개선
def analyze_expenses(df, categories_df, period='이번 달'):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    # 예산 대비 지출 계산
    budget_analysis = []
    for _, cat in categories_df.iterrows():
        spent = df[df['category_id'] == cat['id']]['amount'].sum()
        budget_analysis.append({
            '카테고리': cat['name'],
            '예산': cat['budget'],
            '지출': spent,
            '달성률': (spent / cat['budget'] * 100) if cat['budget'] > 0 else 0
        })
    
    budget_df = pd.DataFrame(budget_analysis)
    
    prompt = f"""
    다음은 {period} 가계부 데이터입니다:
    
    지출 내역:
    {df.to_string()}
    
    예산 분석:
    {budget_df.to_string()}
    
    다음 항목들을 분석해주세요:
    1. 전반적인 지출 패턴 분석
    2. 예산 초과 카테고리와 그 심각성
    3. 특이사항이나 주목할 만한 지출
    4. 구체적인 개선 제안
    5. 다음 달을 위한 예산 조정 제안
    
    분석은 명확하고 구체적으로 해주시되, 실용적인 조언을 포함해주세요.
    응답은 마크다운 형식으로 해주세요.
    """
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content

# 대시보드 지표 계산
def calculate_metrics(df, categories_df, period_start, period_end):
    period_mask = (df['date'] >= period_start) & (df['date'] <= period_end)
    period_df = df[period_mask]
    
    # 이전 기간과 비교
    period_length = (datetime.strptime(period_end, '%Y-%m-%d') - 
                    datetime.strptime(period_start, '%Y-%m-%d')).days + 1
    previous_end = datetime.strptime(period_start, '%Y-%m-%d') - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_length-1)
    
    previous_mask = (df['date'] >= previous_start.strftime('%Y-%m-%d')) & \
                   (df['date'] <= previous_end.strftime('%Y-%m-%d'))
    previous_df = df[previous_mask]
    
    total_expense = period_df['amount'].sum()
    prev_total = previous_df['amount'].sum()
    expense_change = ((total_expense - prev_total) / prev_total * 100 
                     if prev_total > 0 else 0)
    
    # 예산 대비 지출
    total_budget = categories_df['budget'].sum()
    budget_used = (total_expense / total_budget * 100) if total_budget > 0 else 0
    
    # 카테고리별 예산 초과 현황
    over_budget_cats = []
    for _, cat in categories_df.iterrows():
        cat_expenses = period_df[period_df['category_id'] == cat['id']]['amount'].sum()
        if cat['budget'] > 0 and cat_expenses > cat['budget']:
            over_budget_cats.append({
                'name': cat['name'],
                'over_amount': cat_expenses - cat['budget'],
                'percentage': (cat_expenses / cat['budget'] - 1) * 100
            })
    
    return {
        'total_expense': total_expense,
        'expense_change': expense_change,
        'budget_used': budget_used,
        'over_budget': over_budget_cats,
        'daily_avg': total_expense / period_length,
        'transaction_count': len(period_df)
    }

def main():
    # 데이터베이스 초기화
    init_db()
    categories_df = get_categories()
    
    st.title('💰 스마트 가계부 분석기')
    
    # 사이드바 - 데이터 입력
    with st.sidebar:
        st.header('새로운 지출 입력')
        
        # 입력 폼
        with st.form('expense_form'):
            date = st.date_input('날짜', datetime.now())
            category = st.selectbox('카테고리', 
                options=categories_df['name'].tolist(),
                format_func=lambda x: f"{x}")
            
            amount = st.number_input('금액', min_value=0, step=1000)
            description = st.text_input('설명')
            payment_method = st.selectbox('결제 수단', 
                ['현금', '신용카드', '체크카드', '계좌이체', '기타'])
            is_fixed = st.checkbox('고정 지출')
            
            submit_button = st.form_submit_button('저장')
            
            if submit_button and amount > 0:
                conn = sqlite3.connect('expenses.db')
                c = conn.cursor()
                category_id = categories_df[categories_df['name'] == category]['id'].iloc[0]
                
                c.execute('''
                    INSERT INTO expenses 
                    (date, category_id, amount, description, payment_method, is_fixed_expense)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (date.strftime('%Y-%m-%d'), category_id, amount, 
                      description, payment_method, is_fixed))
                
                conn.commit()
                conn.close()
                st.success('저장되었습니다!')
        
        # 카테고리 관리
        with st.expander("카테고리 및 예산 관리"):
            for _, cat in categories_df.iterrows():
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.text(cat['name'])
                with col2:
                    new_budget = st.number_input(
                        f"{cat['name']} 예산",
                        value=float(cat['budget']),
                        key=f"budget_{cat['id']}",
                        step=10000.0
                    )
                    if new_budget != cat['budget']:
                        conn = sqlite3.connect('expenses.db')
                        c = conn.cursor()
                        c.execute('UPDATE categories SET budget = ? WHERE id = ?',
                                (new_budget, cat['id']))
                        conn.commit()
                        conn.close()
                        st.experimental_rerun()
    
    # 메인 화면
    tab1, tab2, tab3 = st.tabs(['📊 대시보드', '📈 상세 분석', '🤖 AI 인사이트'])
    
    # 데이터 로드
    conn = sqlite3.connect('expenses.db')
    df = pd.read_sql_query('''
        SELECT e.*, c.name as category, c.color 
        FROM expenses e 
        JOIN categories c ON e.category_id = c.id
    ''', conn)
    conn.close()
    
    # 기간 선택
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        period = st.selectbox('조회 기간', 
            ['이번 달', '지난 달', '최근 3개월', '최근 6개월', '올해', '전체'])
    
    # 기간에 따른 날짜 범위 설정
    today = datetime.now()
    if period == '이번 달':
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    elif period == '지난 달':
        last_month = today.replace(day=1) - timedelta(days=1)
        start_date = last_month.replace(day=1).strftime('%Y-%m-%d')
        end_date = last_month.strftime('%Y-%m-%d')
    elif period == '최근 3개월':
        start_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    elif period == '최근 6개월':
        start_date = (today - timedelta(days=180)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    elif period == '올해':
        start_date = today.replace(month=1, day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    else:  # 전체
        start_date = df['date'].min()
        end_date = df['date'].max()
    
    # 데이터 필터링
    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
    filtered_df = df[mask].copy()
    
    # 메트릭 계산
    metrics = calculate_metrics(df, categories_df, start_date, end_date)
    
    with tab1:
        # 주요 지표
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("총 지출", 
                     f"{metrics['total_expense']:,.0f}원",
                     f"{metrics['expense_change']:+.1f}% vs 이전")
        with col2:
            st.metric("예산 사용률", 
                     f"{metrics['budget_used']:.1f}%")
        with col3:
            st.metric("일평균 지출",
                     f"{metrics['daily_avg']:,.0f}원")
        with col4:
            st.metric("거래 건수",
                     f"{metrics['transaction_count']}건")
        
        # 예산 초과 경고
        if metrics['over_budget']:
            st.warning("⚠️ 예산 초과 카테고리가 있습니다!")
            for cat in metrics['over_budget']:
                st.markdown(f"- **{cat['name']}**: {cat['over_amount']:,.0f}원 초과 "
                          f"(예산 대비 {cat['percentage']:.1f}% 초과)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 카테고리별 지출 도넛 차트
            fig1 = go.Figure(data=[go.Pie(
                labels=filtered_df['category'],
                values=filtered_df['amount'],
                hole=.4,
                marker_colors=filtered_df['color'].unique()
            )])
            fig1.update_layout(title='카테고리별 지출 비율')
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # 일별 지출 트렌드
            daily_expenses = filtered_df.groupby('date')['amount'].sum().reset_index()
            fig2 = px.line(daily_expenses, x='date', y='amount',
                          title='일별 지출 트렌드')
            fig2.update_
