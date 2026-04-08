import streamlit as st
import pandas as pd
import urllib.parse
import calendar
from datetime import datetime, timezone, timedelta
from stellar_sdk import Server
from stellar_logic import (
    analyze_stellar_account, 
    resolve_username_to_id, 
    resolve_id_to_name
)

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# Custom CSS for table styling, grid lines, and navigation
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    
    /* Mimic table grid lines for column-based rows */
    .detail-row, .header-row {
        border-bottom: 1px solid rgba(128, 128, 128, 0.3);
        display: flex;
        align-items: center;
        min-height: 50px;
    }
    
    /* Vertical lines using column borders */
    [data-testid="column"] {
        border-right: 1px solid rgba(128, 128, 128, 0.3);
        padding: 5px 12px !important;
    }
    
    /* Remove last vertical line in a row */
    [data-testid="column"]:last-child {
        border-right: none;
    }

    .header-row {
        background-color: rgba(128, 128, 128, 0.05);
        border-top: 1px solid rgba(128, 128, 128, 0.3);
        font-weight: 600;
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
    }

    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    a.account-link:hover { text-decoration: underline; }
    
    .subtle-jump {
        font-size: 0.85rem;
        color: #1f77b4 !important;
        text-decoration: none;
        border-bottom: 1px dashed #1f77b4;
        display: inline-block;
        margin-top: 5px;
    }
    .back-top {
        font-size: 0.8rem;
        color: #aaa !important;
        text-decoration: none;
        float: right;
    }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
""", unsafe_allow_html=True)

# --- DIALOG FUNCTION ---
@st.dialog("Transaction Details", width="large")
def show_account_details(account_name, account_id, asset, df_context):
    st.write(f"Showing **{asset}** transactions for: **{account_name}**")
    st.caption(f"ID: {account_id}")
    
    detail_df = df_context[(df_context['other_account_id'] == account_id) & (df_context['asset'] == asset)].copy()
    detail_df = detail_df.sort_values('timestamp', ascending=False)
    
    detail_df['Date/Time'] = detail_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    detail_df['Amount'] = detail_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.table(detail_df[['Date/Time', 'direction', 'Amount', 'asset']].rename(columns={'direction': 'Direction', 'asset': 'Asset'}))
    
    if st.button("Close"):
        st.rerun()

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""
if 'target_id' not in st.session_state:  
    st.session_state.target_id = ""
if 'history' not in st.session_state:
    st.session_state.history = []  # Stack for backward navigation
if 'analysis_months' not in st.session_state:
    url_months = st.query_params.get("months")
    st.session_state.analysis_months = int(url_months) if (url_months and url_months.isdigit()) else 1

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cached_analysis(target_id, months):
    return analyze_stellar_account(target_id, months=months)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_balances(account_id):
    if not account_id: return 0.0, 0.0
    server = Server("https://horizon.stellar.org")
    try:
        account = server.accounts().account_id(account_id).call()
        balances = account.get('balances', [])
        dmmk, nusdt = 0.0, 0.0
        for b in balances:
            asset_code = b.get('asset_code')
            balance = float(b.get('balance', 0))
            if asset_code == 'DMMK': dmmk = balance * 1000.0  
            elif asset_code == 'nUSDT': nusdt = balance
        return dmmk, nusdt
    except Exception: return 0.0, 0.0

def load_account_data(identifier, months, save_to_history=True):
    # Save current state to history before loading new one
    if save_to_history and st.session_state.target_id:
        st.session_state.history.append({
            "id": st.session_state.target_id,
            "name": st.session_state.display_name
        })

    with st.spinner(f"Resolving identity and fetching history for {identifier}..."):
        target_id = None
        current_name = identifier
        if identifier.startswith("G") and len(identifier) == 56:
            target_id = identifier
            found_name = resolve_id_to_name(identifier)
            if found_name: current_name = found_name
        else:
            target_id = resolve_username_to_id(identifier)
        
        if target_id:
            data = fetch_cached_analysis(target_id, months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.display_name = current_name
                st.session_state.target_id = target_id 
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                st.query_params["months"] = str(months)
                return True
        st.error("Account details or transactions not found.")
        return False

# URL Check
target_from_url = st.query_params.get("target_account")
if target_from_url and st.session_state.target_id != target_from_url:
    load_account_data(target_from_url, st.session_state.analysis_months, save_to_history=False)

# 3. Sidebar Configuration
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])

if input_method == "Account Name":
    user_input = st.sidebar.text_input("Enter Name", value=st.session_state.display_name, placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Account ID", value=st.session_state.target_id, placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months 

col_side1, col_side2 = st.sidebar.columns(2)
if col_side1.button("Analyze Account", use_container_width=True) and user_input:
    load_account_data(user_input, analysis_months)
if col_side2.button("Clear Cache", use_container_width=True):
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.session_state.target_id = "" 
    st.session_state.history = []
    st.query_params.clear()
    fetch_cached_analysis.clear()
    st.rerun()

# 4. Main Dashboard
st.markdown("<div id='top-anchor'></div>", unsafe_allow_html=True)

# Backward Button Row
if st.session_state.history:
    if st.button(f"← Back to {st.session_state.history[-1]['name']}"):
        prev = st.session_state.history.pop()
        load_account_data(prev['id'], st.session_state.analysis_months, save_to_history=False)
        st.rerun()

if st.session_state.display_name:
    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
else:
    st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')
    df['day'] = df['timestamp'].dt.day

    # --- KPI SECTION ---
    st.subheader("Current Balance")
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{dmmk_bal:,.2f}")
    b2.metric("nUSDT", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    # --- INTERACTIVE FILTERS ---
    st.subheader("Interactive Filters")
    filter_mode = st.radio("Date Filter Mode", ["Standard (Month/Week)", "Custom Date Range"], horizontal=True)
    t1, t2, t3 = st.columns(3)
    start_date, end_date = None, None

    if filter_mode == "Standard (Month/Week)":
        with t1:
            available_months = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
            sel_month = st.selectbox("Filter by Month", ["All Months"] + available_months)
        with t2:
            if sel_month == "All Months":
                sel_week = st.selectbox("Filter by Week", ["All Weeks"], disabled=True)
            else:
                month_name, year_str = sel_month.split(" ")
                month_idx = list(calendar.month_name).index(month_name)
                _, last_day = calendar.monthrange(int(year_str), month_idx)
                dynamic_weeks = ["1 - 7 (First Week)", "8 - 14 (Second Week)", "15 - 21 (Third Week)", f"22 - {last_day} (Fourth Week)"]
                sel_week = st.selectbox("Filter by Week", ["All Weeks"] + dynamic_weeks)
    else:
        with t1:
            date_range = st.date_input("Select Range", value=(df['timestamp'].min().date(), df['timestamp'].max().date()))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range

    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)
        st.markdown('<a href="#summary-section" class="subtle-jump">Jump to Account Summary</a>', unsafe_allow_html=True)

    selected_assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    filtered_df = df.copy()
    if filter_mode == "Standard (Month/Week)":
        if sel_month != "All Months":
            filtered_df = filtered_df[filtered_df['month_year'] == sel_month]
            if sel_week != "All Weeks":
                bounds = sel_week.split(" (")[0].split(" - ")
                filtered_df = filtered_df[filtered_df['day'].between(int(bounds[0]), int(bounds[1]))]
    elif start_date and end_date:
        filtered_df = filtered_df[(filtered_df['timestamp'].dt.date >= start_date) & (filtered_df['timestamp'].dt.date <= end_date)]
    
    now = datetime.now(timezone.utc)
    if recency == "Last 7 Days": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(days=7))]
    elif recency == "Last 24 Hours": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(hours=24))]
    filtered_df = filtered_df[filtered_df['asset'].isin(selected_assets)]

    if filtered_df.empty:
        st.warning("No data found for this selection.")
    else:
        # --- TRANSACTION HISTORY ---
        st.write("**Transaction History**")
        st.markdown('<div class="header-row">', unsafe_allow_html=True)
        h1, h2, h3, h4, h5, h6 = st.columns([2, 1, 2, 1, 1, 1])
        h1.write("Date/Time")
        h2.write("Direction")
        h3.write("Other Account")
        h4.write("Amount")
        h5.write("Asset")
        h6.write("Details")
        st.markdown('</div>', unsafe_allow_html=True)

        for idx, row in filtered_df.iterrows():
            st.markdown('<div class="detail-row">', unsafe_allow_html=True)
            r1, r2, r3, r4, r5, r6 = st.columns([2, 1, 2, 1, 1, 1])
            r1.write(row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
            r2.write(row['direction'])
            
            # Clickable link triggers history save logic via URL check
            safe_name = urllib.parse.quote(str(row['other_account']))
            link_html = f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
            r3.markdown(link_html, unsafe_allow_html=True)
            
            amt_fmt = f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
            r4.write(amt_fmt)
            r5.write(row['asset'])
            if r6.button("View", key=f"hist_{idx}", use_container_width=True):
                show_account_details(row['other_account'], row['other_account_id'], row['asset'], df)
            st.markdown('</div>', unsafe_allow_html=True)

        # --- SUMMARY SECTION ---
        st.markdown("<div id='summary-section' style='padding-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Summary by Account")
        
        s1, s2 = st.columns([2, 1])
        sort_metric = s1.selectbox("Sort Summary By", options=["Tx_Count", "Total_Volume", "Net_Difference", "Incoming", "Outgoing"])
        sort_order = s2.radio("Order", ["Ascending", "Descending"], index=1, horizontal=True)
        
        summary_df = filtered_df.copy()
        summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
        summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

        account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
            Outgoing=('Outgoing', 'sum'), Incoming=('Incoming', 'sum'),
            Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
        ).reset_index()
        account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
        account_summary = account_summary.sort_values(sort_metric, ascending=(sort_order == "Ascending")).head(10)

        st.markdown('<div class="header-row">', unsafe_allow_html=True)
        hcol1, hcol2, hcol3, hcol4, hcol5, hcol6, hcol7, hcol8 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
        hcol1.write("Other Account")
        hcol2.write("Asset")
        hcol3.write("Total Volume")
        hcol4.write("Incoming")
        hcol5.write("Outgoing")
        hcol6.write("Net Balance")
        hcol7.write("Tx Count")
        hcol8.write("Details")
        st.markdown('</div>', unsafe_allow_html=True)

        for idx, row in account_summary.iterrows():
            st.markdown('<div class="detail-row">', unsafe_allow_html=True)
            rc1, rc2, rc3, rc4, rc5, rc6, rc7, rc8 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
            safe_name = urllib.parse.quote(str(row['other_account']))
            rc1.markdown(f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>', unsafe_allow_html=True)
            rc2.write(row['asset'])
            rc3.write(f"{row['Total_Volume']:,.2f}")
            rc4.write(f"{row['Incoming']:,.2f}")
            rc5.write(f"{row['Outgoing']:,.2f}")
            rc6.write(f"{row['Net_Difference']:,.2f}")
            rc7.write(str(row['Tx_Count']))
            if rc8.button("View", key=f"sum_{idx}", use_container_width=True):
                show_account_details(row['other_account'], row['other_account_id'], row['asset'], df)
            st.markdown('</div>', unsafe_allow_html=True)

        # --- EXPORT SECTION ---
        st.markdown("### Export Data")
        ex1, ex2 = st.columns(2)
        with ex1:
            st.download_button("⬇️ Export History (CSV)", filtered_df.to_csv(index=False).encode('utf-8'), f"{st.session_state.display_name}_history.csv", "text/csv", use_container_width=True)
        with ex2:
            st.download_button("⬇️ Export Summary (CSV)", account_summary.to_csv(index=False).encode('utf-8'), f"{st.session_state.display_name}_summary.csv", "text/csv", use_container_width=True)

        st.markdown('---')
        st.markdown('<a href="#top-anchor" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)
else:
    st.info("Enter an Account Name or Account ID in the sidebar to begin.")
