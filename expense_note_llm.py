import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI

# 페이지 설정
st.set_page_config(
    page_title="스마트 가계부",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        height: 3em;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# 데이터베이스 연결 함수
def get_db_connection():
    return sqlite3.connect('expenses.db')

# 데이터베이스 초기화
def init_db():
    conn = get_db_connection()
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
    
    # 기본 카테고리 확인 및 추가
    c.execute('SELECT COUNT(*) FROM categories')
    if c.fetchone()[0] == 0:
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

# 카테고리 데이터 가져오기
@st.cache_data(ttl=60)
def get_categories():
    conn = get_db_connection()
    categories = pd.read_sql_query('SELECT * FROM categories', conn)
    conn.close()
    return categories

# 지출 데이터 가져오기
@st.cache_data(ttl=60)
def get_expenses():
    conn = get_db_connection()
    expenses = pd.read_sql_query('''
        SELECT e.*, c.name as category, c.color, c.budget 
        FROM expenses e 
        JOIN categories c ON e.category_id = c.id
    ''', conn)
    conn.close()
    return expenses

def main():
    # 데이터베이스 초기화
    init_db()
    
    st.title('💰 스마트 가계부')
    
    # 카테고리 데이터 로드
    categories_df = get_categories()
    
    # 사이드바 - 지출 입력
    with st.sidebar:
        st.header('새로운 지출 입력')
        with st.form('expense_form'):
            date = st.date_input('날짜', datetime.now())
            category = st.selectbox('카테고리', categories_df['name'].tolist())
            amount = st.number_input('금액', min_value=0, step=1000)
            description = st.text_input('설명')
            payment_method = st.selectbox('결제 수단', 
                ['현금', '신용카드', '체크카드', '계좌이체', '기타'])
            is_fixed = st.checkbox('고정 지출')
            
            if st.form_submit_button('저장', use_container_width=True):
                if amount > 0:
                    conn = get_db_connection()
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
                    st.success('저장 완료!')
                    st.cache_data.clear()  # 캐시 초기화
                else:
                    st.error('금액을 입력해주세요!')

        # 예산 관리
        with st.expander("💵 예산 관리"):
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
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute('UPDATE categories SET budget = ? WHERE id = ?',
                                (new_budget, cat['id']))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()  # 캐시 초기화
                        st.experimental_rerun()
    
    # 메인 화면 - 탭
    tab1, tab2 = st.tabs(['📊 대시보드', '📈 상세 분석'])
    
    # 지출 데이터 로드
    df = get_expenses()
    
    if len(df) == 0:
        st.info('아직 지출 데이터가 없습니다. 왼쪽 사이드바에서 지출을 입력해주세요!')
        return
    
    # 기간 선택
    period = st.selectbox('조회 기간', 
        ['이번 달', '지난 달', '최근 3개월', '최근 6개월', '올해', '전체'])
    
    # 기간에 따른 필터링
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
    else:
        start_date = df['date'].min()
        end_date = df['date'].max()
    
    # 데이터 필터링
    df['date'] = pd.to_datetime(df['date'])
    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
    filtered_df = df[mask].copy()
    
    with tab1:
        # 주요 지표
        col1, col2, col3 = st.columns(3)
        total_expense = filtered_df['amount'].sum()
        
        with col1:
            st.metric("총 지출", f"{total_expense:,.0f}원")
        with col2:
            days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
            avg_daily = total_expense / days
            st.metric("일평균 지출", f"{avg_daily:,.0f}원")
        with col3:
            st.metric("거래 건수", f"{len(filtered_df):,}건")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 카테고리별 지출 도넛 차트
            cat_spending = filtered_df.groupby('category')['amount'].sum()
            fig1 = go.Figure(data=[go.Pie(
                labels=cat_spending.index,
                values=cat_spending.values,
                hole=.4,
                marker_colors=filtered_df.groupby('category')['color'].first()
            )])
            fig1.update_layout(title='카테고리별 지출 비율')
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # 일별 지출 트렌드
            daily_spending = filtered_df.groupby('date')['amount'].sum().reset_index()
            fig2 = px.line(daily_spending, x='date', y='amount',
                          title='일별 지출 트렌드')
            fig2.update_traces(line_color='#4CAF50')
            st.plotly_chart(fig2, use_container_width=True)
    
    with tab2:
        # 상세 분석
        st.header('지출 상세 내역')
        
        # 필터
        col1, col2 = st.columns(2)
        with col1:
            selected_categories = st.multiselect(
                '카테고리 선택',
                options=filtered_df['category'].unique(),
                default=filtered_df['category'].unique()
            )
        with col2:
            min_amount = st.number_input('최소 금액', value=0, step=10000)
        
        # 필터링된 데이터
        display_df = filtered_df[
            (filtered_df['category'].isin(selected_categories)) &
            (filtered_df['amount'] >= min_amount)
        ].sort_values('date', ascending=False)
        
        # 데이터 테이블
        st.dataframe(
            display_df[['date', 'category', 'amount', 'description', 'payment_method']],
            hide_index=True,
            column_config={
                'date': st.column_config.DateColumn('날짜'),
                'category': '카테고리',
                'amount': st.column_config.NumberColumn(
                    '금액',
                    format='₩%d',
                ),
                'description': '설명',
                'payment_method': '결제수단'
            }
        )

if __name__ == '__main__':
    main()
