"""BudgetFlow: private owner, read-only family budget dashboard.

Install dependencies, run supabase_setup.sql, and configure Streamlit secrets.
No API credentials are sent to the browser. No sample transactions are invented.
"""
from __future__ import annotations

import csv
import hmac
from datetime import date, datetime
from html import escape
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st
from supabase import Client, create_client

from budget_logic import as_money, filter_entries, format_inr, summarize, weekly_withdrawals

st.set_page_config(
    page_title="BudgetFlow • Family Credit Tracker",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STYLE_PATH = Path(__file__).with_name("styles.css")
st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


@st.cache_resource(show_spinner=False)
def get_database(url: str, secret_key: str) -> Client:
    # The elevated Supabase Secret key is only used in this Python server process.
    # Never put it in HTML, browser JavaScript, or the GitHub repository.
    return create_client(url, secret_key)


def load_config():
    names = ["SUPABASE_URL", "SUPABASE_SECRET_KEY", "OWNER_PASSWORD", "VIEWER_PASSWORD"]
    try:
        config = {name: str(st.secrets[name]).strip() for name in names}
    except (KeyError, FileNotFoundError):
        st.error("App setup is incomplete. Add SUPABASE_URL, SUPABASE_SECRET_KEY, OWNER_PASSWORD and VIEWER_PASSWORD in Streamlit Secrets.")
        st.stop()
    if not all(config.values()) or config["OWNER_PASSWORD"] == config["VIEWER_PASSWORD"]:
        st.error("Configure four non-empty secrets and use DIFFERENT owner and viewer passwords.")
        st.stop()
    if not config["SUPABASE_URL"].startswith("https://"):
        st.error("SUPABASE_URL must start with https://")
        st.stop()
    return config


CONFIG = load_config()


def login_gate():
    if st.session_state.get("budgetflow_role") in {"owner", "viewer"}:
        return st.session_state["budgetflow_role"]

    st.markdown(
        '<div class="bf-topline"><div class="bf-logo">B</div>'
        '<div class="bf-brand">budget<span>flow.</span></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="bf-hero"><h1>Your family budget, clearly tracked.</h1>'
        '<p>Enter your access password to open the private dashboard.</p></div>',
        unsafe_allow_html=True,
    )
    left, middle, right = st.columns([1, 1.25, 1])
    with middle:
        with st.form("access_form"):
            password = st.text_input("Access password", type="password", placeholder="Enter owner or viewer password")
            submitted = st.form_submit_button("Open dashboard", use_container_width=True, type="primary")
            if submitted:
                failures = st.session_state.get("failed_attempts", 0)
                if failures >= 10:
                    st.error("Too many attempts in this session. Close this tab and contact the owner.")
                elif hmac.compare_digest(password, CONFIG["OWNER_PASSWORD"]):
                    st.session_state["budgetflow_role"] = "owner"
                    st.session_state["failed_attempts"] = 0
                    st.rerun()
                elif hmac.compare_digest(password, CONFIG["VIEWER_PASSWORD"]):
                    st.session_state["budgetflow_role"] = "viewer"
                    st.session_state["failed_attempts"] = 0
                    st.rerun()
                else:
                    st.session_state["failed_attempts"] = failures + 1
                    st.error("Incorrect password.")
        st.caption("Owner can add, edit and delete entries. Viewer can only read and export.")
    st.stop()


ROLE = login_gate()
IS_OWNER = ROLE == "owner"
db = get_database(CONFIG["SUPABASE_URL"], CONFIG["SUPABASE_SECRET_KEY"])


def fetch_data():
    setting_response = db.table("budget_settings").select("id,total_credit,opening_used").eq("id", 1).single().execute()
    settings = setting_response.data
    if not settings:
        raise RuntimeError("Budget settings row missing: run supabase_setup.sql")

    entries = []
    page = 0
    while True:
        # PostgREST/Supabase has a default 1,000-row API limit; paginate for full totals.
        chunk = (
            db.table("usage_entries")
            .select("id,used_on,purpose,amount")
            .order("used_on", desc=True)
            .order("id", desc=True)
            .range(page * 1000, (page + 1) * 1000 - 1)
            .execute()
            .data
        ) or []
        entries.extend(chunk)
        if len(chunk) < 1000:
            break
        page += 1
    return settings, entries


def notify_and_refresh(message):
    st.session_state["budgetflow_notice"] = message
    st.rerun()


def add_usage_form(summary):
    with st.form("add_usage", clear_on_submit=True):
        used_on = st.date_input("Date used", value=TODAY, max_value=TODAY)
        purpose = st.text_input("Used for", placeholder="e.g. Cab to college", max_chars=120)
        amount = st.number_input("Amount used (₹)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Save usage", type="primary", use_container_width=True):
            if not purpose.strip() or amount <= 0:
                st.error("Enter a purpose and an amount greater than ₹0.")
            else:
                try:
                    db.table("usage_entries").insert({
                        "used_on": used_on.isoformat(),
                        "purpose": purpose.strip(),
                        "amount": str(as_money(amount)),
                    }).execute()
                    notify_and_refresh("Usage entry saved successfully.")
                except Exception:
                    st.error("Could not save. Check your Supabase connection and table permissions.")
    if summary["remaining"] < 0:
        st.warning("The budget is already over its allocation.")


def edit_and_delete(entries):
    st.caption("Change or remove an existing record. Changes update the dashboard immediately.")
    if not entries:
        st.info("There are no dated usage entries to edit yet.")
        return
    lookup = {int(entry["id"]): entry for entry in entries}
    selected_id = st.selectbox(
        "Choose an entry",
        options=list(lookup),
        format_func=lambda key: f"{lookup[key]['used_on']} · {lookup[key]['purpose'][:43]} · {format_inr(lookup[key]['amount'])}",
        key="manage_selection",
    )
    entry = lookup[selected_id]
    with st.form(f"edit_entry_{selected_id}"):
        edited_date = st.date_input("Date used", value=date.fromisoformat(entry["used_on"]), max_value=TODAY)
        edited_purpose = st.text_input("Used for", value=entry["purpose"], max_chars=120)
        edited_amount = st.number_input(
            "Amount used (₹)", min_value=0.0, value=float(entry["amount"]), step=100.0, format="%.2f"
        )
        if st.form_submit_button("Save changes", type="primary"):
            if not edited_purpose.strip() or edited_amount <= 0:
                st.error("Purpose and positive amount are required.")
            else:
                try:
                    db.table("usage_entries").update({
                        "used_on": edited_date.isoformat(),
                        "purpose": edited_purpose.strip(),
                        "amount": str(as_money(edited_amount)),
                    }).eq("id", selected_id).execute()
                    notify_and_refresh("Entry updated.")
                except Exception:
                    st.error("Unable to update entry. Check the Supabase setup.")

    with st.form(f"delete_entry_{selected_id}"):
        confirm = st.checkbox("I understand this permanently deletes the selected entry")
        if st.form_submit_button("Delete selected entry"):
            if not confirm:
                st.error("Tick the confirmation box first.")
            else:
                try:
                    db.table("usage_entries").delete().eq("id", selected_id).execute()
                    st.session_state.pop("manage_selection", None)
                    notify_and_refresh("Entry deleted.")
                except Exception:
                    st.error("Unable to delete entry. Check the Supabase setup.")


def settings_form(settings, entries):
    st.caption("Use these settings to adjust the family allocation and the amount already used before starting this tracker.")
    with st.form("budget_settings"):
        total = st.number_input(
            "Total credit allocation (₹)", min_value=0.0, value=float(settings["total_credit"]), step=1000.0, format="%.2f"
        )
        opening = st.number_input(
            "Opening amount already used (₹)", min_value=0.0, value=float(settings["opening_used"]), step=1000.0, format="%.2f",
            help="Initially ₹20,000. If you later log old transactions, reduce this by the same amount to avoid counting them twice."
        )
        if st.form_submit_button("Update credit settings", type="primary"):
            if total < 0 or opening < 0:
                st.error("Amounts cannot be negative.")
            else:
                try:
                    db.table("budget_settings").update({
                        "total_credit": str(as_money(total)),
                        "opening_used": str(as_money(opening)),
                        "updated_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                    }).eq("id", 1).execute()
                    notify_and_refresh("Budget settings updated.")
                except Exception:
                    st.error("Unable to update settings. Check Supabase permissions.")
    if entries:
        st.info("Already-logged entries total " + format_inr(sum((as_money(e["amount"]) for e in entries), as_money(0))) + ". Opening usage is added on top of that.")


def metric_card(label, value, subtitle, icon, kind="blue"):
    return (
        f'<div class="bf-card bf-card--{kind}">'
        f'<div class="bf-card-head"><span>{escape(label)}</span><span class="bf-card-icon">{icon}</span></div>'
        f'<div class="bf-card-value">{escape(format_inr(value))}</div>'
        f'<div class="bf-card-desc">{escape(subtitle)}</div></div>'
    )


def show_chart(entries, summary):
    weekly = weekly_withdrawals(entries, today=TODAY, weeks=8)
    total_this_week = weekly[-1]["amount"]
    st.markdown(
        '<div class="bf-panel-heading"><div><div class="bf-panel-title">Weekly money taken</div>'
        '<div class="bf-panel-subtitle">Amount recorded each Monday–Sunday · last 8 weeks</div></div>'
        '<span class="bf-chip">Weekly view</span></div>',
        unsafe_allow_html=True,
    )
    labels = [week["label"] for week in weekly]
    values = [float(week["amount"]) for week in weekly]
    colors = ["#405680"] * 7 + ["#7E93FF"]
    fig = go.Figure()
    fig.add_bar(
        x=labels, y=values, marker_color=colors, marker_line_width=0,
        hovertemplate="Week of %{x}<br>Used: ₹%{y:,.2f}<extra></extra>",
    )
    fig.update_layout(
        height=305, margin=dict(l=0, r=9, t=15, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(color="#92a3bd", size=11), fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor="#263149", zeroline=False,
                   tickfont=dict(color="#92a3bd", size=11), tickprefix="₹", tickformat=",~s", fixedrange=True),
        bargap=0.42,
        hoverlabel=dict(bgcolor="#202e48", font_color="#f3f6ff"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        '<div class="bf-mini-stats">'
        '<div class="bf-mini"><div class="bf-mini-label">Taken this week</div>'
        f'<div class="bf-mini-value">{format_inr(total_this_week)}</div></div>'
        '<div class="bf-mini"><div class="bf-mini-label">Dated entries total</div>'
        f'<div class="bf-mini-value green">{format_inr(summary["logged_used"])}</div></div></div>',
        unsafe_allow_html=True,
    )
    if summary["opening_used"] > 0:
        st.markdown(
            '<div class="bf-note" style="margin-top:13px">'
            f'<strong>{format_inr(summary["opening_used"])}</strong> was used before tracking began. '
            'It counts toward your balance but has no date, so it is not included in the weekly bars.'
            '</div>',
            unsafe_allow_html=True,
        )


def history_csv(entries):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Used for", "Amount used (INR)"])
    for entry in entries:
        writer.writerow([entry["used_on"], entry["purpose"], str(as_money(entry["amount"]))])
    return output.getvalue().encode("utf-8-sig")


def show_history(entries):
    st.markdown(
        '<div class="bf-panel-heading"><div><div class="bf-panel-title">Usage history</div>'
        '<div class="bf-panel-subtitle">Every dated transaction, with a clear purpose and amount</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    search_col, period_col = st.columns([1.25, 1])
    with search_col:
        query = st.text_input("Search", placeholder="Search purpose...", label_visibility="collapsed")
    with period_col:
        period = st.selectbox("Period", ["All time", "This month", "Last 30 days"], label_visibility="collapsed")
    filtered = filter_entries(entries, period, query, today=TODAY)
    if not filtered:
        if entries:
            st.markdown('<div class="bf-empty">No transactions match these filters.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="bf-empty">No dated transactions yet.<br>New usage will appear here once you log it.</div>', unsafe_allow_html=True)
    else:
        rows = "".join(
            '<tr>'
            f'<td class="bf-date">{escape(date.fromisoformat(e["used_on"]).strftime("%d %b %Y"))}</td>'
            f'<td>{escape(e["purpose"])}</td>'
            f'<td class="bf-amount">{escape(format_inr(e["amount"]))}</td>'
            '</tr>' for e in filtered
        )
        html = (
            '<div class="bf-table-wrap"><table class="bf-table"><thead><tr>'
            '<th>Date</th><th>Used for</th><th>Amount used</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
        )
        st.markdown(html, unsafe_allow_html=True)
    controls_left, controls_right = st.columns([1, 1])
    with controls_left:
        st.caption(f"{len(filtered)} transaction(s) shown")
    with controls_right:
        st.download_button(
            "↓ Export CSV", data=history_csv(filtered),
            file_name="budgetflow_usage_history.csv", mime="text/csv",
            use_container_width=True,
            disabled=not filtered,
        )


# --- Authenticated dashboard ---
head_left, head_right = st.columns([7, 1.6], vertical_alignment="center")
with head_left:
    st.markdown(
        '<div class="bf-topline"><div class="bf-logo">B</div>'
        '<div class="bf-brand">budget<span>flow.</span></div></div>'
        '<div class="bf-eyebrow">FAMILY CREDIT DASHBOARD</div>',
        unsafe_allow_html=True,
    )
with head_right:
    st.markdown(
        f'<div class="bf-role"><span class="bf-role-dot"></span><b>{"Owner" if IS_OWNER else "Read-only viewer"}</b><br>'
        'Secure dashboard</div>',
        unsafe_allow_html=True,
    )
    if st.button("Log out", key="logout", use_container_width=True):
        st.session_state["budgetflow_role"] = None
        st.rerun()

try:
    SETTINGS, ENTRIES = fetch_data()
except Exception:
    st.error("Unable to load budget data. Check that supabase_setup.sql has been run and your Supabase URL / Secret key are correct.")
    st.stop()

SUMMARY = summarize(SETTINGS["total_credit"], SETTINGS["opening_used"], ENTRIES)

intro_col, add_col = st.columns([5.5, 1.5], vertical_alignment="bottom")
with intro_col:
    st.markdown(
        '<div class="bf-hero"><h1>Budget overview</h1>'
        '<p>Your available credit, usage, and weekly drawdowns — in one place.</p></div>',
        unsafe_allow_html=True,
    )
with add_col:
    if IS_OWNER:
        with st.popover("＋ Log new usage", use_container_width=True):
            add_usage_form(SUMMARY)

notice = st.session_state.pop("budgetflow_notice", None)
if notice:
    st.success(notice)

metrics = st.columns(3, gap="medium")
with metrics[0]:
    st.markdown(metric_card("Total credit", SUMMARY["total_credit"], "Allocated by Dad", "↗", "blue"), unsafe_allow_html=True)
with metrics[1]:
    st.markdown(metric_card("Credit used", SUMMARY["used"], "Opening usage + logged entries", "↘", "amber"), unsafe_allow_html=True)
with metrics[2]:
    st.markdown(metric_card(
        "Credit remaining", SUMMARY["remaining"],
        "Available to use" if SUMMARY["remaining"] >= 0 else "Over the allocated budget",
        "✓" if SUMMARY["remaining"] >= 0 else "!",
        "green" if SUMMARY["remaining"] >= 0 else "amber",
    ), unsafe_allow_html=True)

percent_used = SUMMARY["pct_used"]
st.markdown(
    '<div class="bf-progress-card">'
    '<div class="bf-progress-head"><strong>Credit utilization</strong>'
    f'<span>{percent_used:.1f}% used &nbsp;·&nbsp; {max(100 - percent_used, 0):.1f}% remaining</span></div>'
    '<div class="bf-progress-rail">'
    f'<div class="bf-progress-fill" style="width:{max(0, min(percent_used, 100)):.2f}%"></div></div>'
    '<div class="bf-progress-note">Balances reflect all logged transactions plus the opening used amount.</div>'
    '</div>',
    unsafe_allow_html=True,
)

left, right = st.columns([0.92, 1.08], gap="large")
with left:
    with st.container(border=True):
        show_chart(ENTRIES, SUMMARY)
with right:
    with st.container(border=True):
        show_history(ENTRIES)

if IS_OWNER:
    st.markdown("### Owner controls")
    with st.expander("Edit / delete transactions or change the budget", expanded=False):
        tab_transactions, tab_settings = st.tabs(["Edit or delete an entry", "Credit settings"])
        with tab_transactions:
            edit_and_delete(ENTRIES)
        with tab_settings:
            settings_form(SETTINGS, ENTRIES)
else:
    st.caption("Read-only access: records and budget settings can only be changed by the owner.")

st.markdown(
    '<div class="bf-foot">BudgetFlow · Family-only ledger · Values in Indian Rupees · Times shown in IST</div>',
    unsafe_allow_html=True,
)
