from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from Analytics import (
    prepare_reviews,
    summarize_reviews,
    analyze_product,
    build_product_roadmap,
)


st.set_page_config(
    page_title="Flipkart Review Intelligence",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root { --ink:#17251f; --muted:#718078; --green:#146b50; --mint:#e8f4ed; }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
    .stApp { background:#f5f7f4; color:var(--ink); }
    [data-testid="stSidebar"] { background:#fff; border-right:1px solid #e8ece8; }
    [data-testid="stSidebar"] h1 { font-family:'Manrope',sans-serif; font-size:1.2rem; }
    .hero { padding:2rem 2.2rem; border-radius:22px; color:#fff; background:linear-gradient(115deg,#123e31,#176b50 68%,#39865d); margin:0.5rem 0 1.35rem; }
    .eyebrow { text-transform:uppercase; letter-spacing:.14em; font-size:.72rem; font-weight:700; opacity:.76; }
    .hero h1 { font:800 2.05rem 'Manrope',sans-serif; margin:.45rem 0 .4rem; color:#fff; }
    .hero p { color:#e1eee7; margin:0; font-size:1rem; }
    .metric { background:#fff; border:1px solid #e7ece7; border-radius:16px; padding:1.1rem 1.2rem; min-height:112px; }
    .metric-label { color:#718078; font-size:.8rem; font-weight:600; }
    .metric-value { color:#17251f; font:700 1.75rem 'Manrope',sans-serif; margin-top:.35rem; }
    .metric-note { color:#89958e; font-size:.76rem; margin-top:.2rem; }
    .section-title { font:700 1.12rem 'Manrope',sans-serif; margin:1.5rem 0 .15rem; }
    .section-sub { color:#718078; font-size:.86rem; margin-bottom:.85rem; }
    div[data-testid="stDataFrame"] { background:white; border-radius:14px; }
    .empty { background:#fff; border:1px solid #e7ece7; border-radius:18px; padding:2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_PATH = Path(__file__).with_name("flipkart_reviews_200.csv.xlsx")


@st.cache_data(show_spinner="Loading review data…")
def load_data(path: str, modified: float) -> pd.DataFrame:
    del modified  # Used as a cache key so replacing the workbook refreshes the data.
    return pd.read_excel(path)


with st.sidebar:
    st.markdown("# 🛍️ ReviewLens")
    st.caption("Flipkart customer feedback, made clear.")
    st.divider()
    st.markdown("**Explore**")
    st.markdown("📊 &nbsp; Review overview")
    st.markdown("🧾 &nbsp; Customer reviews")
    st.divider()
    st.caption("Source: Flipkart review workbook")

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Customer feedback intelligence</div>
      <h1>Know what customers really think.</h1>
      <p>Explore ratings, spot recurring feedback, and find the reviews that need attention.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not DATA_PATH.exists():
    st.error(f"Review data file not found: {DATA_PATH.name}")
    st.info("Place the Flipkart review workbook next to app.py, then refresh this page.")
    st.stop()

try:
    raw = load_data(str(DATA_PATH), DATA_PATH.stat().st_mtime)
    reviews = prepare_reviews(raw)
except Exception as exc:
    st.error("The review workbook could not be opened.")
    st.caption(f"Details: {exc}")
    st.info("Check that the file is a valid .xlsx workbook and refresh the page.")
    st.stop()

with st.expander("View source Excel data", expanded=False):
    st.caption(f"Showing {len(raw):,} rows loaded from {DATA_PATH.name}.")
    st.dataframe(raw, use_container_width=True, hide_index=True)

if "extra_reviews" not in st.session_state:
    st.session_state.extra_reviews = pd.DataFrame(columns=reviews.columns)
if "loaded_uploads" not in st.session_state:
    st.session_state.loaded_uploads = set()

st.markdown('<div class="section-title">Add customer reviews</div>', unsafe_allow_html=True)
st.markdown('<div class="section-sub">Add reviews one at a time or upload a CSV/Excel file with the same review columns. Added reviews stay in this browser session.</div>', unsafe_allow_html=True)
with st.expander("Enter a review or upload a review file", expanded=False):
    upload = st.file_uploader("Upload reviews (.csv or .xlsx)", type=["csv", "xlsx"], key="review_upload")
    if upload is not None:
        payload = upload.getvalue()
        signature = sha256(payload).hexdigest()
        if signature not in st.session_state.loaded_uploads:
            try:
                incoming = pd.read_csv(upload) if upload.name.lower().endswith(".csv") else pd.read_excel(upload)
                prepared = prepare_reviews(incoming)
                if prepared.empty:
                    st.warning("No usable rows found. Include ProductName, Rating, and review text columns.")
                else:
                    st.session_state.extra_reviews = pd.concat([st.session_state.extra_reviews, prepared], ignore_index=True)
                    st.session_state.loaded_uploads.add(signature)
                    st.success(f"Added {len(prepared)} reviews from {upload.name}.")
            except Exception as exc:
                st.error(f"Could not read that file: {exc}")
    with st.form("add_single_review", clear_on_submit=True):
        product = st.text_input("Product name", placeholder="e.g. Wireless headphones")
        title = st.text_input("Review title", placeholder="Short summary")
        review_text = st.text_area("Review", placeholder="What did the customer say?")
        rating = st.select_slider("Rating", options=[1, 2, 3, 4, 5], value=5)
        price = st.number_input("Price (₹), optional", min_value=0.0, value=0.0, step=100.0)
        submitted = st.form_submit_button("Add review", type="primary")
    if submitted:
        if not product.strip() or not review_text.strip():
            st.warning("Enter a product name and review text first.")
        else:
            new_review = pd.DataFrame([{
                "ReviewID": "CUSTOM-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
                "ProductName": product.strip(), "Price_INR": price or pd.NA,
                "Rating": rating, "ReviewTitle": title.strip(), "ReviewText": review_text.strip(),
            }])
            st.session_state.extra_reviews = pd.concat(
                [st.session_state.extra_reviews, prepare_reviews(new_review)], ignore_index=True
            )
            st.success("Review added to this session.")

reviews = pd.concat([reviews, st.session_state.extra_reviews], ignore_index=True)

if reviews.empty:
    st.markdown('<div class="empty">', unsafe_allow_html=True)
    st.subheader("No reviews found")
    st.write("The workbook opened, but it does not contain any usable review rows.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

with st.sidebar:
    rating_values = sorted(reviews["Rating"].dropna().unique().tolist())
    chosen_ratings = st.multiselect("Filter by rating", rating_values, default=rating_values)
    search = st.text_input("Search reviews", placeholder="Try ‘battery’ or ‘quality’")

st.markdown('<div class="section-title">Product analysis</div>', unsafe_allow_html=True)
st.markdown('<div class="section-sub">Select a product for its rating profile, recurring words, and representative customer feedback.</div>', unsafe_allow_html=True)
products = sorted(name for name in reviews["ProductName"].dropna().unique().tolist() if str(name).strip())
if products:
    priority_rows = []
    for product in products:
        product_data = reviews[reviews["ProductName"] == product]
        summary = summarize_reviews(product_data)
        if summary["attention_count"] > 0:
            priority = "High"
        elif summary["average_rating"] < 4:
            priority = "Medium"
        else:
            priority = "Low"
        priority_rows.append({
            "Product": product,
            "Reviews": summary["count"],
            "Average rating": round(summary["average_rating"], 1),
            "1–2 star reviews": summary["attention_count"],
            "Priority": priority,
        })

    priority_table = pd.DataFrame(priority_rows)
    priority_order = ("High", "Medium", "Low")
    priority_tabs = st.tabs([
        f"{priority} priority ({(priority_table['Priority'] == priority).sum()})"
        for priority in priority_order
    ])
    st.markdown("### Product priorities")
    st.caption(
        "High: at least one 1–2 star review. Medium: no 1–2 star reviews and "
        "average rating below 4. Low: no 1–2 star reviews and average rating of 4 or higher."
    )
    for tab, priority in zip(priority_tabs, priority_order):
        with tab:
            products_in_priority = priority_table[
                priority_table["Priority"] == priority
            ].drop(columns="Priority")
            if products_in_priority.empty:
                st.info(f"No {priority.lower()} priority products.")
            else:
                st.dataframe(
                    products_in_priority,
                    use_container_width=True,
                    hide_index=True,
                )

    selected_product = st.selectbox("Choose a product", products, key="product_analysis_selector")
    product_reviews = reviews[reviews["ProductName"] == selected_product]
    product_summary = analyze_product(product_reviews)
    p1, p2, p3 = st.columns(3)
    p1.metric("Product reviews", product_summary["count"])
    p2.metric("Average rating", f"{product_summary['average_rating']:.1f} / 5")
    p3.metric("1–2 star reviews", product_summary["attention_count"])
    pa, pb = st.columns([1, 1])
    with pa:
        st.markdown("**Rating breakdown**")
        st.bar_chart(product_summary["rating_counts"].rename_axis("Stars"), color="#27815e", height=210)
        if product_summary["themes"]:
            st.markdown("**Common words in reviews**")
            st.write(" · ".join(f"{word} ({count})" for word, count in product_summary["themes"]))
        else:
            st.caption("Add review text to surface recurring words.")
    with pb:
        st.markdown("**What customers liked**")
        if product_summary["positive_examples"]:
            for example in product_summary["positive_examples"]:
                st.success(example)
        else:
            st.caption("No 4–5 star reviews yet.")
        st.markdown("**What needs attention**")
        if product_summary["negative_examples"]:
            for example in product_summary["negative_examples"]:
                st.warning(example)
        else:
            st.caption("No 1–2 star reviews yet.")
    st.caption("This product analysis is generated from ratings and review text using simple, transparent rules.")
    st.markdown("**Recommended roadmap**")
    roadmap = build_product_roadmap(product_reviews)
    roadmap_cols = st.columns(3)
    for column, (priority, actions) in zip(roadmap_cols, roadmap.items()):
        with column:
            st.markdown(f"**{priority}**")
            for item in actions:
                st.markdown(f"- {item['action']}")
                st.caption(item["evidence"])
else:
    st.info("Add reviews with product names to see product analysis.")
