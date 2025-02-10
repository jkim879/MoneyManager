import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import plotly.express as px
from openai import OpenAI
import os

# SQLite 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# LLM 분석 함수
def analyze_expenses(df):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    # 데이터프레임을 문자열로 변환
    df_str = df.to_string()
    
    prompt = f"""
    다음은 가계부 데이터입니다:
    {df_str}
    
    이 데이터를 분석하여 다음 정보를 제공해주세요:
    1. 지출 패턴 분석
    2. 과다 지출 카테고리 식별
    3. 개선을 위한 제안사항
    
    한국어로 응답해주세요.
    """
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.choices[0].message.content

# 메인 애플리케이션
def main():
    st.title('💰 스마트 가계부 분석기')
    
    # 데이터베이스 초기화
    init_db()
    
    # 사이드바 - 데이터 입력
    with st.sidebar:
        st.header('새로운 지출 입력')
        date = st.date_input('날짜', datetime.now())
        category = st.selectbox('카테고리', 
            ['식비', '교통', '주거', '통신', '의료', '교육', '여가', '기타'])
        amount = st.number_input('금액', min_value=0)
        description = st.text_input('설명')
        
        if st.button('저장'):
            conn = sqlite3.connect('expenses.db')
            c = conn.cursor()
            c.execute('INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)',
                    (date.strftime('%Y-%m-%d'), category, amount, description))
            conn.commit()
            conn.close()
            st.success('저장되었습니다!')

    # 메인 화면 - 데이터 표시 및 분석
    tab1, tab2, tab3 = st.tabs(['📊 지출 현황', '📈 시각화', '🤖 AI 분석'])
    
    # 데이터 로드
    conn = sqlite3.connect('expenses.db')
    df = pd.read_sql_query('SELECT * FROM expenses', conn)
    conn.close()
    
    # 날짜 형식 변환
    df['date'] = pd.to_datetime(df['date'])
    
    with tab1:
        st.header('지출 내역')
        st.dataframe(df)
        
        # 기본 통계
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric('총 지출', f"{df['amount'].sum():,.0f}원")
        with col2:
            st.metric('평균 지출', f"{df['amount'].mean():,.0f}원")
        with col3:
            st.metric('거래 건수', f"{len(df):,}건")
    
    with tab2:
        st.header('지출 분석 차트')
        
        # 카테고리별 지출
        fig1 = px.pie(df, values='amount', names='category',
                     title='카테고리별 지출 비율')
        st.plotly_chart(fig1)
        
        # 시간별 지출 트렌드
        fig2 = px.line(df.groupby('date')['amount'].sum().reset_index(),
                      x='date', y='amount',
                      title='일별 지출 트렌드')
        st.plotly_chart(fig2)
        
        # 카테고리별 월간 지출
        monthly_cat = df.pivot_table(
            values='amount',
            index=df['date'].dt.strftime('%Y-%m'),
            columns='category',
            aggfunc='sum'
        ).fillna(0)
        
        fig3 = px.bar(monthly_cat,
                     title='카테고리별 월간 지출',
                     barmode='group')
        st.plotly_chart(fig3)
    
    with tab3:
        st.header('AI 지출 분석')
        if st.button('AI 분석 시작'):
            with st.spinner('분석 중...'):
                analysis = analyze_expenses(df)
                st.write(analysis)

if __name__ == '__main__':
    main()
