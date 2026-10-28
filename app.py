import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os

# Page setup
st.set_page_config(page_title=" Player Stat Visualizer", page_icon="🏏", layout="wide")

# ---- Load Data ----
# Get the folder where this script lives
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


@st.cache_data
def load_data():
    matches_path = os.path.join(SCRIPT_DIR, "matches.csv")
    deliveries_path = os.path.join(SCRIPT_DIR, "deliveries.csv")

    m = pd.read_csv(matches_path)
    d = pd.read_csv(deliveries_path)
    # make sure season is a number
    m["season"] = pd.to_numeric(m["season"], errors="coerce")
    d = d.merge(m[["id", "season"]], left_on="match_id", right_on="id", how="left")
    # keep last 3 seasons only
    recent = m["season"].dropna().drop_duplicates().nlargest(3).tolist()
    return m[m["season"].isin(recent)], d[d["season"].isin(recent)]


try:
    matches, dlv = load_data()
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.error(f"Looking in folder: {SCRIPT_DIR}")
    st.error(f"Files found: {os.listdir(SCRIPT_DIR)}")
    st.stop()

# ---- Sidebar ----
seasons = sorted([int(s) for s in matches["season"].unique()])
st.sidebar.title("🏏 Player Stat Visualizer")
st.sidebar.caption(f"Seasons: {', '.join(map(str, seasons))}")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigate", ["📊 Overview", "🆚 Player Comparison", "💰 Auction Rankings"])


# ---- Phase Classification ----
def get_phase(over):
    if over < 6:
        return "Powerplay"
    elif over < 16:
        return "Middle"
    return "Death"


PHASE_COLORS = {"Powerplay": "#2ecc71", "Middle": "#f39c12", "Death": "#e74c3c"}


def phase_selector():
    return st.radio("Select Match Phase", ["Overall", "Powerplay", "Middle", "Death"], horizontal=True)


# ---- Get stats for a player ----
def get_stats(player, phase="Overall"):
    df = dlv[dlv["batter"] == player].copy()
    if df.empty: return None
    if phase != "Overall":
        df["phase"] = df["over"].apply(get_phase)
        df = df[df["phase"] == phase]
    if df.empty: return None

    runs = df["batsman_runs"].sum()
    balls = len(df)
    fours = int((df["batsman_runs"] == 4).sum())
    sixes = int((df["batsman_runs"] == 6).sum())
    boundaries = fours + sixes
    dismissals = dlv[dlv["player_dismissed"] == player].copy()
    if phase != "Overall":
        dismissals["phase"] = dismissals["over"].apply(get_phase)
        dismissals = dismissals[dismissals["phase"] == phase]
    outs = dismissals.shape[0]
    avg = round(runs / outs, 1) if outs > 0 else round(runs, 1)
    sr = round(runs / balls * 100, 1) if balls > 0 else 0
    innings = df.groupby("match_id").ngroups
    return {"Runs": runs, "Balls": balls, "Boundaries": boundaries, "Avg": avg, "SR": sr, "Innings": innings,
            "4s": fours, "6s": sixes}


def get_eligible_players(min_runs=200):
    totals = dlv.groupby("batter")["batsman_runs"].sum()
    return sorted(totals[totals >= min_runs].index.tolist())


def get_all_stats(phase="Overall", min_runs=200):
    players = get_eligible_players(min_runs)
    rows = []
    for p in players:
        s = get_stats(p, phase)
        if s and s["Runs"] > 0:
            rows.append({"Player": p, **s})
    return pd.DataFrame(rows).sort_values("Runs", ascending=False)


def get_phase_distribution(player):
    df = dlv[dlv["batter"] == player].copy()
    if df.empty: return None
    df["phase"] = df["over"].apply(get_phase)
    dist = df.groupby("phase")["batsman_runs"].sum().reset_index()
    dist.columns = ["Phase", "Runs"]
    return dist

# PAGE 1: OVERVIEW
if page == "📊 Overview":
    st.title("🏏 Phase Based Player Stat Visualizer")
    st.caption(f"IPL {', '.join(map(str, seasons))} — 5 Metrics: Runs, Balls, Boundaries, Average, Strike Rate")
    st.markdown("---")
    phase = phase_selector()
    df = get_all_stats(phase)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Seasons", len(seasons))
    c2.metric("Matches", len(matches))
    c3.metric("Players", len(df))
    c4.metric("Phase", phase)
    st.markdown("---")

    st.subheader(f"🏆 Top Run Scorers : {phase}")
    top = df.head(15)
    fig_bar = px.bar(top, x="Runs", y="Player", orientation="h",
                     color="Runs", color_continuous_scale="Oranges",
                     hover_data=["Balls", "Boundaries", "Avg", "SR"])
    fig_bar.update_layout(yaxis=dict(autorange="reversed"), height=450)
    st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader(f"📊 Strike Rate vs Average : {phase}")
    st.caption("Top-right = best all-round performers. Bubble size = Runs scored.")
    fig_scatter = px.scatter(df.head(20), x="Avg", y="SR",
                             size="Runs", hover_name="Player",
                             color="Runs", color_continuous_scale="Plasma", size_max=40)
    fig_scatter.update_layout(xaxis_title="Average", yaxis_title="Strike Rate", height=450)
    st.plotly_chart(fig_scatter, use_container_width=True)

    if phase == "Overall":
        st.subheader("🍩 Where Do They Score? (Run Distribution by Phase)")
        top6 = df.head(6)["Player"].tolist()
        cols = st.columns(3)
        for i, player in enumerate(top6):
            dist = get_phase_distribution(player)
            if dist is not None:
                fig_pie = px.pie(dist, values="Runs", names="Phase",
                                 color="Phase", color_discrete_map=PHASE_COLORS,
                                 hole=0.45, title=player)
                fig_pie.update_layout(height=250, margin=dict(t=40, b=10, l=10, r=10),
                                      showlegend=True if i == 0 else False)
                cols[i % 3].plotly_chart(fig_pie, use_container_width=True)


# PAGE 2: PLAYER COMPARISON

elif page == "🆚 Player Comparison":
    st.title("🆚 Player Comparison")
    st.markdown("---")
    phase = phase_selector()

    eligible = get_eligible_players()
    c1, c2 = st.columns(2)
    p1 = c1.selectbox("Player 1", eligible,
                      index=eligible.index("V Kohli") if "V Kohli" in eligible else 0)
    p2 = c2.selectbox("Player 2", eligible,
                      index=eligible.index("RG Sharma") if "RG Sharma" in eligible else 1)

    s1 = get_stats(p1, phase)
    s2 = get_stats(p2, phase)

    if s1 and s2:
        c1, c2 = st.columns(2)
        for col, p, s in [(c1, p1, s1), (c2, p2, s2)]:
            col.subheader(p)
            mc = col.columns(5)
            display_stats = {k: v for k, v in s.items() if k in ["Runs", "Avg", "SR", "4s", "6s"]}
            for i, (label, val) in enumerate(display_stats.items()):
                mc[i].metric(label, val)

        st.markdown("---")

        st.subheader(f"📊 Radar Comparison — {phase}")
        cats = ["Runs", "Avg", "SR", "4s", "6s"]
        v1 = [s1[c] for c in cats]
        v2 = [s2[c] for c in cats]
        mx = [max(a, b) or 1 for a, b in zip(v1, v2)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=[v / m for v, m in zip(v1, mx)] + [v1[0] / mx[0]],
            theta=cats + [cats[0]], fill='toself', name=p1,
            fillcolor="rgba(255, 99, 71, 0.25)",
            line=dict(color="#FF6347", width=3),
            text=[str(v) for v in v1] + [str(v1[0])],
            hovertemplate="%{theta}: %{text}<extra>" + p1 + "</extra>"))
        fig_radar.add_trace(go.Scatterpolar(
            r=[v / m for v, m in zip(v2, mx)] + [v2[0] / mx[0]],
            theta=cats + [cats[0]], fill='toself', name=p2,
            fillcolor="rgba(30, 144, 255, 0.25)",
            line=dict(color="#1E90FF", width=3),
            text=[str(v) for v in v2] + [str(v2[0])],
            hovertemplate="%{theta}: %{text}<extra>" + p2 + "</extra>"))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            height=500, title=f"{p1} vs {p2} — {phase}")
        st.plotly_chart(fig_radar, use_container_width=True)
    else:
        st.warning("Not enough data for one or both players in this phase.")


# PAGE 3: AUCTION VALUE

elif page == "💰 Auction Rankings":
    st.title("💰 Auction Value Analysis")
    st.caption("Ranking players by role-specific value using custom formulas")
    st.markdown("---")

    # Calculate role-based scores for all eligible players
    eligible = get_eligible_players(min_runs=100)

    pp_rows = []
    mid_rows = []
    death_rows = []

    for p in eligible:
        pp = get_stats(p, "Powerplay")
        mid = get_stats(p, "Middle")
        death = get_stats(p, "Death")

        if pp and pp["Balls"] >= 30:
            # Powerplay: reward SR + Boundaries + 4s
            pp_score = round((pp["SR"] * 0.4) + (pp["Boundaries"] * 0.4) + (pp["Avg"] * 0.2), 1)
            pp_rows.append({"Player": p, "Runs": pp["Runs"], "Avg": pp["Avg"], "SR": pp["SR"],
                            "Boundaries": pp["Boundaries"], "4s": pp["4s"], "6s": pp["6s"],
                            "Value Score": pp_score})

        if mid and mid["Balls"] >= 30:
            # Middle: reward Avg + Runs + consistency
            mid_score = round((mid["Avg"] * 0.4) + (mid["Runs"] * 0.4) + (mid["SR"] * 0.2), 1)
            mid_rows.append({"Player": p, "Runs": mid["Runs"], "Avg": mid["Avg"], "SR": mid["SR"],
                             "Boundaries": mid["Boundaries"], "4s": mid["4s"], "6s": mid["6s"],
                             "Value Score": mid_score})

        if death and death["Balls"] >= 20:
            # Death: reward SR + 6s + Boundaries heavily
            death_score = round((death["SR"] * 0.4) + (death["6s"] * 0.4) + (death["Avg"] * 0.2), 1)
            death_rows.append({"Player": p, "Runs": death["Runs"], "Avg": death["Avg"], "SR": death["SR"],
                               "Boundaries": death["Boundaries"], "4s": death["4s"], "6s": death["6s"],
                               "Value Score": death_score})

    pp_df = pd.DataFrame(pp_rows).sort_values("Value Score", ascending=False) if pp_rows else pd.DataFrame()
    mid_df = pd.DataFrame(mid_rows).sort_values("Value Score", ascending=False) if mid_rows else pd.DataFrame()
    death_df = pd.DataFrame(death_rows).sort_values("Value Score", ascending=False) if death_rows else pd.DataFrame()

    # --- POWERPLAY ---
    st.subheader("⚡ Best Powerplay Batters")
    st.caption("Value Score = SR × 0.4 + Boundaries × 0.4 + Avg × 0.2")
    if not pp_df.empty:
        top_pp = pp_df.head(10)
        fig_pp = px.bar(top_pp, x="Value Score", y="Player", orientation="h",
            color="Value Score", color_continuous_scale="Greens",
            hover_data=["Runs", "SR", "Avg", "Boundaries"])
        fig_pp.update_layout(yaxis=dict(autorange="reversed"), height=400)
        st.plotly_chart(fig_pp, use_container_width=True)

    st.markdown("---")

    # --- MIDDLE OVERS ---
    st.subheader("🔄 Best Middle Overs Batters")
    st.caption("Value Score = Avg × 0.4 + Runs × 0.4 + SR × 0.2")
    if not mid_df.empty:
        top_mid = mid_df.head(10)
        fig_mid = px.bar(top_mid, x="Value Score", y="Player", orientation="h",
            color="Value Score", color_continuous_scale="Oranges",
            hover_data=["Runs", "SR", "Avg", "Boundaries"])
        fig_mid.update_layout(yaxis=dict(autorange="reversed"), height=400)
        st.plotly_chart(fig_mid, use_container_width=True)

    st.markdown("---")

    # --- DEATH OVERS ---
    st.subheader("🔥 Best Death Overs Finishers")
    st.caption("Value Score = SR × 0.4 + 6s × 0.4 + Avg × 0.2")
    if not death_df.empty:
        top_death = death_df.head(10)
        fig_death = px.bar(top_death, x="Value Score", y="Player", orientation="h",
            color="Value Score", color_continuous_scale="Reds",
            hover_data=["Runs", "SR", "Avg", "6s", "Boundaries"])
        fig_death.update_layout(yaxis=dict(autorange="reversed"), height=400)
        st.plotly_chart(fig_death, use_container_width=True)

# ---- Sidebar Footer ----
st.sidebar.markdown("---")
st.sidebar.markdown(
    "📦 [Kaggle IPL Dataset](https://www.kaggle.com/datasets/patrickb1912/ipl-complete-dataset-20082020)")
st.sidebar.markdown("🛠️ Python · Pandas · Plotly · Streamlit")
