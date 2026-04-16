import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="Life Expectancy Explorer", layout="wide")
st.title("Life Expectancy Explorer")

conn = st.connection("snowflake")
session = conn.session()

GENDER_COLS = {
    "Total": "LIFE_EXPECTANCY_TOTAL",
    "Female": "LIFE_EXPECTANCY_FEMALE",
    "Male": "LIFE_EXPECTANCY_MALE",
}

@st.cache_data
def get_countries():
    return session.sql(
        "SELECT GEO_NAME FROM HEALTHDB.DW.DIM_GEOGRAPHY WHERE LEVEL = 'Country' ORDER BY GEO_NAME"
    ).to_pandas()["GEO_NAME"].tolist()

@st.cache_data
def get_regions():
    return session.sql(
        "SELECT GEO_NAME FROM HEALTHDB.DW.DIM_GEOGRAPHY WHERE LEVEL = 'CountryGroup' ORDER BY GEO_NAME"
    ).to_pandas()["GEO_NAME"].tolist()

countries = get_countries()
regions = get_regions()

col1, col2 = st.columns(2)
with col1:
    year_range = st.slider("Year range", 1960, 2024, (1990, 2024))
with col2:
    gender = st.selectbox("Gender", list(GENDER_COLS.keys()))

compare_countries = st.multiselect(
    "Select countries to compare with New Zealand",
    [c for c in countries if c != "New Zealand"],
    default=["Australia", "Japan"],
)

selected_region = st.selectbox("Compare with region (optional)", ["All"] + regions)

le_col = GENDER_COLS[gender]
all_countries = ["New Zealand"] + compare_countries

placeholders = ", ".join([f"'{c}'" for c in all_countries])
query = f"""
    SELECT g.GEO_NAME AS COUNTRY, d.YEAR, f.{le_col} AS LIFE_EXPECTANCY
    FROM HEALTHDB.DW.FACT_HEALTH_MEASURES f
    JOIN HEALTHDB.DW.DIM_DATE d ON f.DATE_KEY = d.DATE_KEY
    JOIN HEALTHDB.DW.DIM_GEOGRAPHY g ON f.GEO_KEY = g.GEO_KEY
    WHERE g.LEVEL = 'Country'
      AND g.GEO_NAME IN ({placeholders})
      AND d.YEAR BETWEEN {year_range[0]} AND {year_range[1]}
      AND f.{le_col} IS NOT NULL
    ORDER BY d.YEAR, g.GEO_NAME
"""
df = session.sql(query).to_pandas()

if selected_region != "All":
    region_query = f"""
        SELECT g.GEO_NAME AS COUNTRY, d.YEAR, f.{le_col} AS LIFE_EXPECTANCY
        FROM HEALTHDB.DW.FACT_HEALTH_MEASURES f
        JOIN HEALTHDB.DW.DIM_DATE d ON f.DATE_KEY = d.DATE_KEY
        JOIN HEALTHDB.DW.DIM_GEOGRAPHY g ON f.GEO_KEY = g.GEO_KEY
        WHERE g.LEVEL = 'CountryGroup'
          AND g.GEO_NAME = '{selected_region}'
          AND d.YEAR BETWEEN {year_range[0]} AND {year_range[1]}
          AND f.{le_col} IS NOT NULL
        ORDER BY d.YEAR
    """
    region_df = session.sql(region_query).to_pandas()
    if not region_df.empty:
        df = pd.concat([df, region_df], ignore_index=True)

if df.empty:
    st.warning("No data found for the selected filters.")
    st.stop()

st.subheader(f"Life Expectancy ({gender}) — {year_range[0]} to {year_range[1]}")

chart = (
    alt.Chart(df)
    .mark_line(point=True)
    .encode(
        x=alt.X("YEAR:O", title="Year", axis=alt.Axis(labelAngle=-45, values=list(range(year_range[0], year_range[1] + 1, 5)))),
        y=alt.Y("LIFE_EXPECTANCY:Q", title="Life Expectancy (years)", scale=alt.Scale(zero=False)),
        color=alt.Color("COUNTRY:N", title="Country / Region"),
        strokeWidth=alt.condition(
            alt.datum.COUNTRY == "New Zealand",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=["COUNTRY", "YEAR", alt.Tooltip("LIFE_EXPECTANCY:Q", format=".1f")],
    )
    .properties(height=450)
    .interactive()
)
st.altair_chart(chart, width='stretch')

st.subheader("Data comparison")

pivot = df.pivot_table(index="YEAR", columns="COUNTRY", values="LIFE_EXPECTANCY").reset_index()
if "New Zealand" in pivot.columns:
    for c in [col for col in pivot.columns if col not in ("YEAR", "New Zealand")]:
        pivot[f"NZ vs {c}"] = (pivot["New Zealand"] - pivot[c]).round(2)
st.dataframe(pivot, width='stretch', hide_index=True)
