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
DB_PATH = os.path.abspath('expenses.db')

# ------------------------------------------------------------------
# 데이터베이스 초기화 (메인 카테고리, 세부 카테고리, 지출 테이블 생성 및 기본 데이터 삽입)
def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # 메인 카테고리 테이블 생성
            c.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    budget REAL DEFAULT 0,
                    color TEXT
                )
            ''')
            # 세부 카테고리 테이블 생성
            c.execute('''
                CREATE TABLE IF NOT EXISTS subcategories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                )
            ''')
            # 지출 테이블 생성 (세부 카테고리 컬럼 포함)
            c.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    subcategory_id INTEGER,
                    amount REAL NOT NULL,
                    description TEXT,
                    payment_method TEXT DEFAULT '현금',
                    is_fixed_expense BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (category_id) REFERENCES categories (id),
                    FOREIGN KEY (subcategory_id) REFERENCES subcategories (id)
                )
            ''')
            # 만약 기존 테이블에 subcategory_id 컬럼이 없다면 추가 (ALTER TABLE)
            c.execute("PRAGMA table_info(expenses)")
            columns = [row[1] for row in c.fetchall()]
            if "subcategory_id" not in columns:
                c.execute("ALTER TABLE expenses ADD COLUMN subcategory_id INTEGER;")
                conn.commit()
            # 메인 카테고리 기본 데이터 삽입
            c.execute('SELECT COUNT(*) FROM categories')
            if c.fetchone()[0] == 0:
                default_categories = [
                    ('주거비', 500000, '#FF6B6B'),
                    ('대출이자', 200000, '#4ECDC4'),
                    ('통신비', 800000, '#45B7D1'),
                    ('교통비', 100000, '#96CEB4'),
                    ('보험료', 200000, '#D4A5A5'),
                    ('주택청약', 300000, '#9B89B3'),
                    ('적금', 400000, '#FAD02E'),
                    ('생활비', 200000, '#95A5A6'),
                    ('구독료', 150000, '#E59866'),
                    ('회비', 50000, '#A29BFE'),
                    ('투자', 700000, '#6C5B7B'),
                    ('기타', 100000, '#B8B8B8')
                ]
                for cat in default_categories:
                    try:
                        c.execute('INSERT INTO categories (name, budget, color) VALUES (?,?,?)', cat)
                    except sqlite3.IntegrityError:
                        pass
                conn.commit()
            # 기본 세부 카테고리 삽입 (메인 카테고리별 서로 다른 하위 항목)
            c.execute('SELECT COUNT(*) FROM subcategories')
            if c.fetchone()[0] == 0:
                default_subcategories = {
                    '주거비': ['관리비', '전기세', '수도세', '난방비'],
                    '대출이자': ['전세대출', '기타대출'],
                    '통신비': ['인터넷', '핸드폰', 'TV'],
                    '교통비': ['지하철', '버스', '렌트카', '택시', '주유'],
                    '보험료': ['지성 보험료', '승미 보험료'],
                    '주택청약': ['청약통장'],
                    '적금': ['은행적금', '개인연금'],
                    '생활비': ['식비', '식료품 구매', '외식', '기타 생활비'],
                    '구독료': ['넷플릭스', '유튜브 프리미엄', '음악 서비스', '기타 구독료'],
                    '회비': ['동호회 회비', '가족 회비', '기타 회비'],
                    '투자': ['주식', '가상자산', '펀드', '기타 투자'],
                    '기타': ['기타']
                }
                for cat_name, subcats in default_subcategories.items():
                    c.execute('SELECT id FROM categories WHERE name = ?', (cat_name,))
                    row = c.fetchone()
                    if row:
                        cat_id = row[0]
                        for sub in subcats:
                            c.execute('INSERT INTO subcategories (category_id, name) VALUES (?, ?)', (cat_id, sub))
                conn.commit()
        return True
    except Exception as e:
        st.error(f"DB 초기화 오류: {e}")
        return False

# ------------------------------------------------------------------
# LLM 기반 AI 분석 함수
def analyze_expenses_with_llm(df, period='이번 달'):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        category_spending = df.groupby('category')['amount'].agg(['sum', 'count']).reset_index()
        category_spending['percentage'] = (category_spending['sum'] / category_spending['sum'].sum() * 100).round(2)
        df['date'] = pd.to_datetime(df['date'])
        daily_pattern = df.groupby(df['date'].dt.day_name())['amount'].mean()
        analysis_text = f"""
분석 기간: {period}
총 지출: {df['amount'].sum():,.0f}원
거래 건수: {len(df)}건
카테고리별 지출:
{category_spending.to_string(index=False)}
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
        return f"분석 중 오류: {e}"

# ------------------------------------------------------------------
# DB에서 메인 카테고리 데이터를 가져오기
def get_categories():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT * FROM categories ORDER BY name"
            categories = pd.read_sql_query(query, conn)
        return categories
    except Exception as e:
        st.error(f"카테고리 불러오기 오류: {e}")
        return pd.DataFrame(columns=['id', 'name', 'budget', 'color'])

# DB에서 세부 카테고리 데이터를 가져오기 (특정 메인 카테고리)
def get_subcategories(category_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT * FROM subcategories WHERE category_id = ? ORDER BY name"
            subcategories = pd.read_sql_query(query, conn, params=(category_id,))
        return subcategories
    except Exception as e:
        st.error(f"세부 카테고리 불러오기 오류: {e}")
        return pd.DataFrame(columns=['id', 'category_id', 'name'])

# DB에서 지출 데이터를 가져오기 (세부 카테고리 포함)
def get_expenses():
    try:
        with sqlite3.connect(DB_PATH) as conn:
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
                    c.budget,
                    s.name as subcategory
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                LEFT JOIN subcategories s ON e.subcategory_id = s.id
                ORDER BY e.date DESC
            '''
            expenses = pd.read_sql_query(query, conn)
        return expenses
    except Exception as e:
        st.error(f"지출 불러오기 오류: {e}")
        return pd.DataFrame(columns=['id', 'date', 'amount', 'description', 'payment_method',
                                     'is_fixed_expense', 'category', 'color', 'budget', 'subcategory'])

# 지출 추가 (세부 카테고리 포함)
def add_expense(date, category_id, subcategory_id, amount, description, payment_method, is_fixed):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO expenses 
                (date, category_id, subcategory_id, amount, description, payment_method, is_fixed_expense)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (date, category_id, subcategory_id, amount, description, payment_method, is_fixed))
            conn.commit()
        return True
    except Exception as e:
        st.error(f"지출 추가 오류: {e}")
        return False

# 지출 삭제
def delete_expense(expense_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            conn.commit()
        st.success("선택한 지출 항목이 삭제되었습니다.")
    except Exception as e:
        st.error(f"지출 삭제 오류: {e}")

# ------------------------------------------------------------------
# 사용자 지정 기간 필터 함수
def get_date_range(period, expenses_df):
    today = datetime.now()
    if period == "이번 달":
        start_date = today.replace(day=1)
        end_date = today
    elif period == "지난 달":
        last_month_end = today.replace(day=1) - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end
    elif period == "최근 3개월":
        start_date = today - timedelta(days=90)
        end_date = today
    elif period == "최근 6개월":
        start_date = today - timedelta(days=180)
        end_date = today
    elif period == "올해":
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif period == "사용자 지정":
        start_date = st.date_input("시작 날짜", today - timedelta(days=30))
        end_date = st.date_input("종료 날짜", today)
        if start_date > end_date:
            st.error("시작 날짜는 종료 날짜보다 이전이어야 합니다.")
            start_date, end_date = today - timedelta(days=30), today
    else:  # "전체"
        start_date = pd.to_datetime(expenses_df["date"]).min() if not expenses_df.empty else today
        end_date = pd.to_datetime(expenses_df["date"]).max() if not expenses_df.empty else today
    return start_date, end_date

# CSV 내보내기 함수
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")

# ------------------------------------------------------------------
# 메인 함수
def main():
    st.title("💰 뚱미의 자산관리")

    if not init_db():
        st.error("DB 초기화에 실패했습니다.")
        return

    # ────────────── 사이드바 영역 ──────────────
    with st.sidebar:
        # 자산 정보 영역: 사용자가 현재 보유한 금액 입력 (예: 1,000,000원)
        st.header("자산 정보")
        if "current_balance" not in st.session_state:
            st.session_state["current_balance"] = 1000000
        current_balance = st.number_input("현재 보유 금액", value=st.session_state["current_balance"], step=10000, format="%d")
        st.session_state["current_balance"] = current_balance

        st.header("새로운 지출 입력")
        # 메인 카테고리 및 세부 카테고리 선택 (폼 외부에서 동적 반영)
        categories_df = get_categories()
        if categories_df.empty:
            st.error("카테고리를 불러올 수 없습니다.")
            return
        selected_category = st.selectbox("메인 카테고리", categories_df["name"].tolist(), key="main_cat")
        category_id = int(categories_df.loc[categories_df["name"] == selected_category, "id"].iloc[0])
        subcats_df = get_subcategories(category_id)
        if not subcats_df.empty:
            selected_subcategory = st.selectbox("세부 카테고리", subcats_df["name"].tolist(), key="sub_cat")
            subcategory_id = int(subcats_df.loc[subcats_df["name"] == selected_subcategory, "id"].iloc[0])
        else:
            selected_subcategory = None
            subcategory_id = None

        # 나머지 입력 필드는 폼 내부에 두어 한 번에 저장
        with st.form("expense_form"):
            expense_date = st.date_input("날짜", datetime.now())
            amount_str = st.text_input("금액", value="", placeholder="숫자만 입력 (예: 50000)")
            try:
                amount = int(amount_str.replace(",", "")) if amount_str else 0
            except ValueError:
                amount = 0
            description = st.text_input("설명", max_chars=100)
            payment_method = st.selectbox("결제 수단", ["현금", "신용카드", "체크카드", "계좌이체", "기타"])
            is_fixed = st.checkbox("고정 지출")
            submitted = st.form_submit_button("저장")
            if submitted:
                if amount <= 0:
                    st.error("금액을 정확히 입력하세요.")
                else:
                    if add_expense(expense_date.strftime("%Y-%m-%d"), category_id, subcategory_id, amount, description, payment_method, is_fixed):
                        st.success("지출이 저장되었습니다.")
        st.header("데이터 내보내기")
        expenses_df_all = get_expenses()
        if not expenses_df_all.empty:
            csv_data = convert_df_to_csv(expenses_df_all)
            st.download_button(
                label="CSV로 다운로드",
                data=csv_data,
                file_name="expenses.csv",
                mime="text/csv"
            )

    # ────────────── 메인 영역 ──────────────
    expenses_df = get_expenses()
    period_option = st.selectbox("조회 기간", ["전체", "이번 달", "지난 달", "최근 3개월", "최근 6개월", "올해", "사용자 지정"])
    start_date, end_date = get_date_range(period_option, expenses_df)

    expenses_df["date"] = pd.to_datetime(expenses_df["date"], errors="coerce")
    filtered_df = expenses_df[(expenses_df["date"] >= pd.to_datetime(start_date)) & (expenses_df["date"] <= pd.to_datetime(end_date))]

    tab1, tab2, tab3 = st.tabs(["📊 대시보드", "📈 상세 분석", "🤖 AI 분석"])

    with tab1:
        st.subheader("주요 지표")
        # 전체 지출(모든 기록)을 기준으로 현재 잔액 계산
        expenses_all = get_expenses()
        overall_expense = expenses_all["amount"].sum() if not expenses_all.empty else 0
        current_balance = st.session_state.get("current_balance", 0)
        current_money = current_balance - overall_expense
        st.metric("현재 잔액", f"{current_money:,.0f}원")

        if filtered_df.empty:
            st.info("선택된 기간에 해당하는 지출 데이터가 없습니다.")
        else:
            col1, col2, col3, _ = st.columns(4)
            total_expense = filtered_df["amount"].sum()
            days_count = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
            avg_daily = total_expense / days_count if days_count > 0 else 0
            with col1:
                st.metric("총 지출", f"{total_expense:,.0f}원")
            with col2:
                st.metric("일평균 지출", f"{avg_daily:,.0f}원")
            with col3:
                st.metric("거래 건수", f"{len(filtered_df):,}건")
            # 네 번째 칼럼은 현재 잔액이 이미 상단에 표시됨

            st.markdown("---")
            col_left, col_right = st.columns(2)
            with col_left:
                cat_spending = filtered_df.groupby("category")["amount"].sum()
                if not cat_spending.empty:
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=cat_spending.index,
                        values=cat_spending.values,
                        hole=0.4,
                        marker_colors=filtered_df.groupby("category")["color"].first()
                    )])
                    fig_pie.update_layout(title="카테고리별 지출 비율")
                    st.plotly_chart(fig_pie, use_container_width=True)
                budget_vs_spending = pd.DataFrame({
                    "category": cat_spending.index,
                    "spent": cat_spending.values,
                    "budget": [get_categories().loc[get_categories()["name"] == cat, "budget"].iloc[0] for cat in cat_spending.index]
                })
                budget_vs_spending["usage_rate"] = (budget_vs_spending["spent"] / budget_vs_spending["budget"] * 100).round(2)
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    name="지출",
                    x=budget_vs_spending["category"],
                    y=budget_vs_spending["spent"],
                    marker_color="#4CAF50"
                ))
                fig_bar.add_trace(go.Bar(
                    name="예산",
                    x=budget_vs_spending["category"],
                    y=budget_vs_spending["budget"],
                    marker_color="rgba(156, 156, 156, 0.5)"
                ))
                fig_bar.update_layout(title="카테고리별 예산 대비 지출", barmode="overlay")
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_right:
                daily_trend = filtered_df.groupby("date")["amount"].sum().reset_index()
                if not daily_trend.empty:
                    fig_line = px.line(daily_trend, x="date", y="amount", title="일별 지출 트렌드")
                    fig_line.update_traces(line_color="#4CAF50")
                    st.plotly_chart(fig_line, use_container_width=True)
                payment_spending = filtered_df.groupby("payment_method")["amount"].sum()
                fig_payment = px.pie(values=payment_spending.values, names=payment_spending.index, title="결제 수단별 지출 비율")
                st.plotly_chart(fig_payment, use_container_width=True)

    with tab2:
        st.subheader("지출 상세 내역")
        if filtered_df.empty:
            st.info("선택된 기간에 해당하는 지출 데이터가 없습니다.")
        else:
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                selected_categories = st.multiselect(
                    "카테고리 선택",
                    options=filtered_df["category"].unique(),
                    default=filtered_df["category"].unique()
                )
            with col_filter2:
                min_amount = st.number_input("최소 금액", value=0, step=10000)
            display_df = filtered_df[(filtered_df["category"].isin(selected_categories)) & (filtered_df["amount"] >= min_amount)]
            st.experimental_data_editor(
                display_df[["id", "date", "category", "subcategory", "amount", "description", "payment_method"]],
                num_rows="dynamic",
                use_container_width=True,
                disabled=True
            )

    with tab3:
        st.subheader("🤖 AI 지출 분석")
        if filtered_df.empty:
            st.info("선택된 기간에 분석할 데이터가 없습니다.")
        else:
            if st.button("분석 시작", key="ai_analysis"):
                with st.spinner("분석 중..."):
                    analysis = analyze_expenses_with_llm(filtered_df.copy(), period_option)
                st.markdown(analysis)
                st.markdown("---")
                st.subheader("카테고리별 상세 분석")
                cat_analysis = filtered_df.groupby("category").agg({
                    "amount": ["sum", "mean", "count"],
                    "date": "nunique"
                }).round(0)
                cat_analysis.columns = ["총 지출", "평균 지출", "거래 수", "지출 일수"]
                cat_analysis = cat_analysis.reset_index()
                cat_analysis["예산"] = cat_analysis["category"].map(get_categories().set_index("name")["budget"])
                cat_analysis["예산 대비 사용률"] = (cat_analysis["총 지출"] / cat_analysis["예산"] * 100).round(1)
                st.dataframe(cat_analysis, use_container_width=True,
                             column_config={
                                 "category": "카테고리",
                                 "총 지출": st.column_config.NumberColumn("총 지출", format="₩%d"),
                                 "평균 지출": st.column_config.NumberColumn("평균 지출", format="₩%d"),
                                 "예산": st.column_config.NumberColumn("예산", format="₩%d"),
                                 "예산 대비 사용률": st.column_config.NumberColumn("예산 대비 사용률", format="%.1f%%")
                             })

    # ────────────── 지출 관리 영역 (전체 항목 표시 및 체크박스로 삭제) ──────────────
    st.markdown("---")
    st.subheader("지출 관리")
    st.write("전체 지출 항목과 함께, 아래 '삭제할 항목 선택' 영역에서 각 항목 옆의 체크박스를 선택한 후 삭제 버튼을 누르면 해당 항목이 삭제됩니다.")
    expenses_for_delete = get_expenses()
    if expenses_for_delete.empty:
        st.info("삭제할 지출 항목이 없습니다.")
    else:
        st.subheader("전체 지출 항목")
        st.dataframe(expenses_for_delete[["id", "date", "category", "subcategory", "amount", "description", "payment_method"]], use_container_width=True)
        with st.expander("삭제할 항목 선택"):
            st.markdown("아래에서 삭제할 항목의 체크박스를 선택하세요:")
            header_cols = st.columns([0.1, 0.9])
            header_cols[0].markdown("**삭제**")
            header_cols[1].markdown("**항목 정보**")
            delete_ids = []
            for _, row in expenses_for_delete.iterrows():
                cols = st.columns([0.1, 0.9])
                with cols[0]:
                    if st.checkbox("", key=f"del_{row['id']}"):
                        delete_ids.append(row["id"])
                with cols[1]:
                    st.write(f"{row['id']} - {row['date']} / {row['category']} - {row['subcategory'] if row['subcategory'] else ''} / {row['amount']:,}원")
            if st.button("선택 항목 삭제"):
                for eid in delete_ids:
                    delete_expense(eid)
                st.success("선택한 항목이 삭제되었습니다.")
                st.experimental_rerun()

if __name__ == "__main__":
    main()
