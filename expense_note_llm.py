import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import os

# 페이지 설정
st.set_page_config(
    page_title="스마트 가계부",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 데이터베이스 경로 설정
DB_PATH = 'expenses.db'

# 기존 데이터베이스 삭제 (스키마 변경을 위해)
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# 데이터베이스 연결 및 초기화
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 카테고리 테이블 생성
        c.execute('''
            CREATE TABLE IF NOT EXISTS categories
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             name TEXT NOT NULL UNIQUE,
             budget REAL DEFAULT 0,
             color TEXT)
        ''')
        
        # 지출 테이블 생성 (payment_method 컬럼 추가)
        c.execute('''
            CREATE TABLE IF NOT EXISTS expenses
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             date TEXT NOT NULL,
             category_id INTEGER NOT NULL,
             amount REAL NOT NULL,
             description TEXT,
             payment_method TEXT DEFAULT '현금',
             is_fixed_expense BOOLEAN DEFAULT FALSE,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (category_id) REFERENCES categories (id))
        ''')
        
        # 기본 카테고리 추가
        categories = [
            ('식비', 500000, '#FF6B6B'),
            ('교통', 200000, '#4ECDC4'),
            ('주거', 800000, '#45B7D1'),
            ('통신', 100000, '#96CEB4'),
            ('의료', 200000, '#D4A5A5'),
            ('교육', 300000, '#9B89B3'),
            ('여가', 400000, '#FAD02E'),
            ('기타', 200000, '#95A5A6')
        ]
        
        for cat in categories:
            try:
                c.execute('INSERT INTO categories (name, budget, color) VALUES (?,?,?)', cat)
            except sqlite3.IntegrityError:
                pass
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f'데이터베이스 초기화 중 오류가 발생했습니다: {str(e)}')
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()

# 카테고리 데이터 가져오기
def get_categories():
    try:
        conn = sqlite3.connect(DB_PATH)
        query = 'SELECT * FROM categories ORDER BY name'
        categories = pd.read_sql_query(query, conn)
        return categories
    except Exception as e:
        st.error(f'카테고리 데이터를 가져오는 중 오류가 발생했습니다: {str(e)}')
        return pd.DataFrame(columns=['id', 'name', 'budget', 'color'])
    finally:
        if 'conn' in locals():
            conn.close()

# 지출 데이터 가져오기
def get_expenses():
    try:
        conn = sqlite3.connect(DB_PATH)
        query = '''
            SELECT 
                e.id,
                e.date,
                e.amount,
                e.description,
                e.payment_method,
                e.is_fixed_expense,
                c.name as category,
                c.color,
                c.budget
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            ORDER BY e.date DESC
        '''
        expenses = pd.read_sql_query(query, conn)
        return expenses
    except Exception as e:
        st.error(f'지출 데이터를 가져오는 중 오류가 발생했습니다: {str(e)}')
        return pd.DataFrame(columns=['id', 'date', 'amount', 'description', 'payment_method', 
                                   'is_fixed_expense', 'category', 'color', 'budget'])
    finally:
        if 'conn' in locals():
            conn.close()

# 지출 추가
def add_expense(date, category_id, amount, description, payment_method, is_fixed):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO expenses 
            (date, category_id, amount, description, payment_method, is_fixed_expense)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (date, category_id, amount, description, payment_method, is_fixed))
        conn.commit()
        return True
    except Exception as e:
        st.error(f'지출 추가 중 오류가 발생했습니다: {str(e)}')
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    st.title('💰 스마트 가계부')
    
    # 데이터베이스 초기화
    if not init_db():
        st.error('데이터베이스 초기화에 실패했습니다.')
        return
    
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
            
            submit = st.form_submit_button('저장', use_container_width=True)
            
            if submit:
                if amount <= 0:
                    st.error('금액을 입력해주세요!')
                else:
                    category_id = categories_df[categories_df['name'] == category]['id'].iloc[0]
                    if add_expense(date.strftime('%Y-%m-%d'), category_id, amount, 
                                 description, payment_method, is_fixed):
                        st.success('저장 완료!')
                        st.experimental_rerun()
    
    # 지출 데이터 로드
    expenses_df = get_expenses()
    
    if len(expenses_df) == 0:
        st.info('아직 지출 데이터가 없습니다. 왼쪽 사이드바에서 지출을 입력해주세요!')
        return
    
    # 메인 화면 - 탭
    tab1, tab2 = st.tabs(['📊 대시보드', '📈 상세 분석'])
    
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
        start_date = expenses_df['date'].min()
        end_date = expenses_df['date'].max()

    # 데이터 필터링
    expenses_df['date'] = pd.to_datetime(expenses_df['date'])
    filtered_df = expenses_df[
        (expenses_df['date'] >= start_date) & 
        (expenses_df['date'] <= end_date)
    ].copy()
    
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
