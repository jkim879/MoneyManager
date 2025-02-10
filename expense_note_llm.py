import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI
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
        
        # 지출 테이블 생성
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
        
        # 기본 카테고리가 없을 경우에만 추가
        c.execute('SELECT COUNT(*) FROM categories')
        if c.fetchone()[0] == 0:
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

# LLM 분석 함수
def analyze_expenses_with_llm(df, period='이번 달'):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        
        # 카테고리별 지출 분석
        category_spending = df.groupby('category')['amount'].agg(['sum', 'count']).reset_index()
        category_spending['percentage'] = (category_spending['sum'] / category_spending['sum'].sum() * 100).round(2)
        
        # 일별 패턴 분석
        df['date'] = pd.to_datetime(df['date'])
        daily_pattern = df.groupby(df['date'].dt.day_name())['amount'].mean()
        
        analysis_text = f"""
        분석 기간: {period}
        
        총 지출: {df['amount'].sum():,.0f}원
        거래 건수: {len(df)}건
        
        카테고리별 지출:
        {category_spending.to_string()}
        
        일별 평균 지출:
        {daily_pattern.to_string()}
        """
        
        prompt = f"""
다음은 가계부 데이터 분석 결과입니다:

{analysis_text}

이 데이터를 바탕으로 다음 항목들을 분석해주세요:
1. 전반적인 지출 패턴과 특징
2. 가장 많은 지출이 발생한 카테고리와 그 적정성
3. 지출 습관 개선을 위한 구체적인 제안
4. 예산 관리 및 절약을 위한 실질적인 조언

한국어로 명확하고 실용적인 분석을 제공해주세요.
"""
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"분석 중 오류가 발생했습니다: {str(e)}"

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
            
            # 금액 입력 UI 개선
            amount_str = st.text_input('금액', value='', placeholder='금액을 입력하세요')
            try:
                amount = int(amount_str.replace(',', '')) if amount_str else 0
            except ValueError:
                amount = 0
                
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
    tab1, tab2, tab3 = st.tabs(['📊 대시보드', '📈 상세 분석', '🤖 AI 분석'])
    
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
            if not cat_spending.empty:
                fig1 = go.Figure(data=[go.Pie(
                    labels=cat_spending.index,
                    values=cat_spending.values,
                    hole=.4,
                    marker_colors=filtered_df.groupby('category')['color'].first()
                )])
                fig1.update_layout(title='카테고리별 지출 비율')
                st.plotly_chart(fig1, use_container_width=True)
            
            # 예산 대비 지출 현황
            budget_vs_spending = pd.DataFrame({
                'category': cat_spending.index,
                'spent': cat_spending.values,
                'budget': [categories_df[categories_df['name'] == cat]['budget'].iloc[0] 
                          for cat in cat_spending.index]
            })
            
            budget_vs_spending['usage_rate'] = (
                budget_vs_spending['spent'] / budget_vs_spending['budget'] * 100
            ).round(2)
            
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                name='지출',
                x=budget_vs_spending['category'],
                y=budget_vs_spending['spent'],
                marker_color='#4CAF50'
            ))
            fig3.add_trace(go.Bar(
                name='예산',
                x=budget_vs_spending['category'],
                y=budget_vs_spending['budget'],
                marker_color='rgba(156, 156, 156, 0.5)'
            ))
            fig3.update_layout(
                title='카테고리별 예산 대비 지출',
                barmode='overlay'
            )
            st.plotly_chart(fig3, use_container_width=True)
        
        with col2:
            # 일별 지출 트렌드
            daily_spending = filtered_df.groupby('date')['amount'].sum().reset_index()
            if not daily_spending.empty:
                fig2 = px.line(daily_spending, x='date', y='amount',
                              title='일별 지출 트렌드')
                fig2.update_traces(line_color='#4CAF50')
                st.plotly_chart(fig2, use_container_width=True)
            
            # 결제 수단별 지출 비율
            payment_spending = filtered_df.groupby('payment_method')['amount'].sum()
            fig4 = px.pie(
                values=payment_spending.values,
                names=payment_spending.index,
                title='결제 수단별 지출 비율'
            )
            st.plotly_chart(fig4, use_container_width=True)
    
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
    
    with tab3:
        st.header('🤖 AI 지출 분석')
        if st.button('분석 시작', use_container_width=True):
            with st.spinner('분석 중...'):
                analysis = analyze_expenses_with_llm(filtered_df, period)
                st.markdown(analysis)
                
                # 카테고리별 분석 테이블
                st.subheader('카테고리별 상세 분석')
                cat_analysis = filtered_df.groupby('category').agg({
                    'amount': ['sum', 'mean', 'count'],
                    'date': 'nunique'
                }).round(0)
                
                cat_analysis.columns = ['총 지출', '평균 지출', '거래 수', '지출 일수']
                cat_analysis = cat_analysis.reset_index()
                
                # 예산 정보 추가
                cat_analysis['예산'] = cat_analysis['category'].map(
                    categories_df.set_index('name')['budget']
                )
                cat_analysis['예산 대비 사용률'] = (
                    cat_analysis['총 지출'] / cat_analysis['예산'] * 100
                ).round(1)
                
                st.dataframe(
                    cat_analysis,
                    hide_index=True,
                    column_config={
                        'category': '카테고리',
                        '총 지출': st.column_config.NumberColumn(
                            '총 지출',
                            format='₩%d',
                        ),
                        '평균 지출': st.column_config.NumberColumn(
                            '평균 지출',
                            format='₩%d',
                        ),
                        '예산': st.column_config.NumberColumn(
                            '예산',
                            format='₩%d',
                        ),
                        '예산 대비 사용률': st.column_config.NumberColumn(
                            '예산 대비 사용률',
                            format='%.1f%%',
                        ),
                    }
                )

if __name__ == '__main__':
    # 세션 상태 초기화
    if 'reload_data' not in st.session_state:
        st.session_state.reload_data = True
    
    main()
