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

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            budget REAL DEFAULT 0,
            color TEXT
        )
    ''')
    
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

def get_categories():
    conn = sqlite3.connect('expenses.db')
    categories = pd.read_sql_query('SELECT * FROM categories', conn)
    conn.close()
    return categories

def analyze_spending(df, categories_df):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    budget_analysis = []
    for _, cat in categories_df.iterrows():
        spent = df[df['category_id'] == cat['id']]['amount'].sum()
        budget_analysis.append({
            '카테고리': cat['name'],
            '예산': cat['budget'],
            '지출': spent,
            '사용률': (spent / cat['budget'] * 100) if cat['budget'] > 0 else 0
        })
    
    budget_df = pd.DataFrame(budget_analysis)
    
    prompt = f"""
    현재 가계부 데이터 분석:
    
    지출 현황:
    {budget_df.to_string()}
    
    다음 항목들을 분석해주세요:
    1. 전반적인 지출 패턴
    2. 예산 초과 항목과 위험도
    3. 개선이 필요한 부분
    4. 다음 달을 위한 구체적인 조언
    
    실용적이고 구체적인 조언을 부탁드립니다.
    """
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content

def main():
    init_db()
    categories_df = get_categories()
    
    st.title('💰 스마트 가계부')
    
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
                    st.success('저장 완료!')
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
                        conn = sqlite3.connect('expenses.db')
                        c = conn.cursor()
                        c.execute('UPDATE categories SET budget = ? WHERE id = ?',
                                (new_budget, cat['id']))
                        conn.commit()
                        conn.close()
                        st.experimental_rerun()
    
    # 메인 화면 - 탭
    tab1, tab2, tab3 = st.tabs(['📊 대시보드', '📈 상세 분석', '🤖 AI 분석'])
    
    # 데이터 로드
    conn = sqlite3.connect('expenses.db')
    df = pd.read_sql_query('''
        SELECT e.*, c.name as category, c.color, c.budget 
        FROM expenses e 
        JOIN categories c ON e.category_id = c.id
    ''', conn)
    conn.close()
    
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
    
    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
    filtered_df = df[mask].copy()
    
    with tab1:
        # 주요 지표
        col1, col2, col3 = st.columns(3)
        total_expense = filtered_df['amount'].sum()
        with col1:
            st.metric("총 지출", f"{total_expense:,.0f}원")
        with col2:
            avg_daily = total_expense / ((datetime.strptime(end_date, '%Y-%m-%d') - 
                                        datetime.strptime(start_date, '%Y-%m-%d')).days + 1)
            st.metric("일평균 지출", f"{avg_daily:,.0f}원")
        with col3:
            st.metric("거래 건수", f"{len(filtered_df):,}건")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 카테고리별 지출 도넛 차트
            fig1 = go.Figure(data=[go.Pie(
                labels=filtered_df['category'],
                values=filtered_df['amount'],
                hole=.4,
                marker_colors=filtered_df['color']
            )])
            fig1.update_layout(title='카테고리별 지출 비율')
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # 예산 대비 지출 현황
            category_spending = filtered_df.groupby('category')['amount'].sum()
            fig2 = go.Figure()
            for cat in categories_df.itertuples():
                spent = category_spending.get(cat.name, 0)
                budget = cat.budget
                fig2.add_trace(go.Bar(
                    name=cat.name,
                    x=[cat.name],
                    y=[spent],
                    marker_color=cat.color
                ))
                # 예산 선 추가
                if budget > 0:
                    fig2.add_shape(
                        type="line",
                        x0=cat.name,
                        x1=cat.name,
                        y0=0,
                        y1=budget,
                        line=dict(color="red", width=2, dash="dash")
                    )
            fig2.update_layout(title='카테고리별 예산 대비 지출', barmode='group')
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
                'date': '날짜',
                'category': '카테고리',
                'amount': st.column_config.NumberColumn(
                    '금액',
                    format='₩%d'
                ),
                'description': '설명',
                'payment_method': '결제수단'
            }
        )
        
        # 지출 패턴 분석
        st.subheader('지출 패턴 분석')
        col1, col2 = st.columns(2)
        
        with col1:
            # 요일별 지출
            df['weekday'] = pd.to_datetime(df['date']).dt.day_name()
            weekday_spending = df.groupby('weekday')['amount'].mean().reindex([
                'Monday', 'Tuesday', 'Wednesday', 'Thursday', 
                'Friday', 'Saturday', 'Sunday'
            ])
            fig3 = px.bar(weekday_spending, 
                         title='요일별 평균 지출',
                         labels={'value': '평균 지출액', 'index': '요일'})
            st.plotly_chart(fig3, use_container_width=True)
        
        with col2:
            # 시간대별 지출 (고정지출 vs 변동지출)
            fixed_vs_variable = filtered_df.groupby('is_fixed_expense')['amount'].sum()
            fig4 = px.pie(values=fixed_vs_variable.values,
                         names=['변동지출', '고정지출'],
                         title='고정지출 vs 변동지출 비율')
            st.plotly_chart(fig4, use_container_width=True)
    
    with tab3:
        st.header('AI 지출 분석')
        if st.button('분석 시작', use_container_width=True):
            with st.spinner('분석 중...'):
                analysis = analyze_spending(filtered_df, categories_df)
                st.markdown(analysis)

if __name__ == '__main__':
    main()
