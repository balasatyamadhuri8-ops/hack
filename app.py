import itertools
import math
import time
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="ReliefQ | Emergency Resource Optimizer", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")

NAVY = "#16324F"
TEAL = "#16A6A1"
BLUE = "#4F86C6"
ORANGE = "#F4A261"
PALE = "#F3F7FB"

st.markdown("""
<style>
.block-container{padding-top:1.15rem;padding-bottom:2rem;max-width:1500px}
[data-testid="stSidebar"]{background:#16324F}
[data-testid="stSidebar"] *{color:#fff}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:#d9e7f3}
h1,h2,h3{color:#16324F}
.hero{background:linear-gradient(115deg,#16324F,#225578);padding:22px 26px;border-radius:18px;color:white;margin-bottom:18px}
.hero h1{color:white;margin:0;font-size:2rem}.hero p{color:#dbe8f3;margin:7px 0 0 0}
.kpi{background:#f3f7fb;border:1px solid #e1eaf2;border-radius:14px;padding:15px 17px;min-height:105px}
.kpi-label{color:#60758a;font-size:.84rem}.kpi-value{color:#16324F;font-size:1.75rem;font-weight:750;margin-top:5px}.kpi-sub{color:#728499;font-size:.78rem;margin-top:2px}
.section-note{color:#65788b;font-size:.88rem}
div[data-testid="stMetric"]{background:#f3f7fb;border:1px solid #e1eaf2;padding:12px 14px;border-radius:13px}
.stButton>button{border-radius:9px;font-weight:650}
hr{border-color:#e5edf4}
</style>
""", unsafe_allow_html=True)

DEFAULTS = [
    {"Village":"Tuni", "Latitude":17.35, "Longitude":82.55, "Food demand":6, "Water demand":8, "Urgency (1-10)":9},
    {"Village":"Visakhapatnam", "Latitude":17.69, "Longitude":83.22, "Food demand":5, "Water demand":7, "Urgency (1-10)":7},
    {"Village":"Srikakulam", "Latitude":18.30, "Longitude":83.90, "Food demand":4, "Water demand":5, "Urgency (1-10)":8},
]

if "villages" not in st.session_state:
    st.session_state.villages = DEFAULTS.copy()
if "page" not in st.session_state:
    st.session_state.page = "Operational Overview"
if "last_results" not in st.session_state:
    st.session_state.last_results = None

with st.sidebar:
    st.markdown("# ◈ ReliefQ")
    st.caption("QUANTUM-ASSISTED EMERGENCY RELIEF")
    st.divider()
    page = st.radio("NAVIGATION", ["Operational Overview", "Scenario Builder", "Resource Allocation", "Quantum vs Classical", "Analytics & Map", "About ReliefQ"], key="page")
    st.divider()
    st.markdown("**SYSTEM STATUS**")
    st.markdown("🟢 Interactive scenario builder")
    st.markdown("🔵 Exact classical baseline")
    st.markdown("🟡 QAOA simulator runs on CPU")
    st.caption("Educational prototype · Not for live emergency decisions")

st.markdown(f"""<div class="hero"><h1>ReliefQ</h1><p>Quantum-Assisted Emergency Relief Resource Optimization</p><p>Prioritize affected communities, allocate limited supplies, and compare an exact classical baseline with a Qiskit QAOA candidate.</p></div>""", unsafe_allow_html=True)

# Scenario controls are always available in an expander so any page can use the same live scenario.
with st.expander("⚙️ Configure emergency scenario", expanded=(page == "Scenario Builder")):
    top1, top2, top3, top4 = st.columns([1,1,1,1.2])
    with top1:
        food_supply = st.number_input("Available food kits", min_value=0, value=int(st.session_state.get("food_supply", 10)), step=1, key="food_supply")
    with top2:
        water_supply = st.number_input("Available water packs", min_value=0, value=int(st.session_state.get("water_supply", 12)), step=1, key="water_supply")
    with top3:
        village_count = st.number_input("Number of villages", min_value=1, value=len(st.session_state.villages), step=1, key="village_count")
    with top4:
        st.caption("Choose as many villages as your scenario requires. Very large scenarios may be limited by browser or cloud resources.")
    current = st.session_state.villages[:int(village_count)]
    while len(current) < int(village_count):
        i = len(current) + 1
        current.append({"Village":f"Village {i}","Latitude":17.0 + i*0.18,"Longitude":82.0 + i*0.16,"Food demand":3,"Water demand":3,"Urgency (1-10)":5})
    edit_df = pd.DataFrame(current, columns=["Village","Latitude","Longitude","Food demand","Water demand","Urgency (1-10)"])
    st.markdown("**Village demand and location editor**")
    st.caption("Coordinates are decimal degrees. Example: Tuni ≈ 17.35 latitude, 82.55 longitude.")
    try:
        edited = st.data_editor(edit_df, use_container_width=True, hide_index=True, num_rows="fixed", key="village_editor", column_config={
            "Village": st.column_config.TextColumn("Village name", required=True),
            "Latitude": st.column_config.NumberColumn("Latitude", min_value=-90.0, max_value=90.0, format="%.4f", required=True),
            "Longitude": st.column_config.NumberColumn("Longitude", min_value=-180.0, max_value=180.0, format="%.4f", required=True),
            "Food demand": st.column_config.NumberColumn("Food kits needed", min_value=0, step=1, required=True),
            "Water demand": st.column_config.NumberColumn("Water packs needed", min_value=0, step=1, required=True),
            "Urgency (1-10)": st.column_config.NumberColumn("Urgency (1–10)", min_value=1, max_value=10, step=1, required=True),
        })
    except Exception:
        edited = st.dataframe(edit_df, use_container_width=True, hide_index=True)
        edited = edit_df
    st.session_state.villages = edited.to_dict("records") if isinstance(edited, pd.DataFrame) else current
    st.caption("Use the sidebar to switch sections. Your current scenario feeds the overview, charts, map, and allocation model.")

villages = pd.DataFrame(st.session_state.villages)
for col in ["Food demand", "Water demand", "Urgency (1-10)"]:
    villages[col] = pd.to_numeric(villages[col], errors="coerce").fillna(0).astype(int).clip(lower=0)
villages["Urgency (1-10)"] = villages["Urgency (1-10)"].clip(1,10)
villages["Latitude"] = pd.to_numeric(villages["Latitude"], errors="coerce").fillna(0.0).clip(-90,90)
villages["Longitude"] = pd.to_numeric(villages["Longitude"], errors="coerce").fillna(0.0).clip(-180,180)
villages["Village"] = villages["Village"].astype(str).replace("", "Unnamed village")
food_demand = int(villages["Food demand"].sum())
water_demand = int(villages["Water demand"].sum())
food_allocatable = min(int(food_supply), food_demand)
water_allocatable = min(int(water_supply), water_demand)

# The discrete exact baseline chooses individual kits, respecting demand and total supply.
def exact_allocate(demands, urgency, supply):
    demands = [int(max(0,x)) for x in demands]
    urgency = [int(max(1,x)) for x in urgency]
    supply = int(max(0,supply))
    n_units = sum(demands)
    start = time.perf_counter()
    # Unit-based exact search is intentionally bounded for demo scale.
    if n_units > 20:
        # Exact dynamic programming over villages and supply; preserves optimal objective for this objective.
        dp = {0:(0.0, [])}
        for i, demand in enumerate(demands):
            nxt = {}
            for used,(score,alloc) in dp.items():
                for q in range(min(demand,supply-used)+1):
                    new_used = used+q
                    cand = (score+q*urgency[i], alloc+[q])
                    if new_used not in nxt or cand[0] > nxt[new_used][0]: nxt[new_used] = cand
            dp = nxt
        used = min(supply,n_units)
        best_score, best_alloc = dp.get(used,(0.0,[0]*len(demands)))
        return best_alloc, best_score, time.perf_counter()-start, "dynamic programming exact baseline"
    units = [i for i,d in enumerate(demands) for _ in range(d)]
    target = min(supply, len(units))
    best_score = -1
    best_bits = None
    for bits in itertools.product((0,1), repeat=len(units)):
        if sum(bits) != target: continue
        score = sum(urgency[units[j]]*bits[j] for j in range(len(units)))
        if score > best_score:
            best_score, best_bits = score, bits
    allocation = [0]*len(demands)
    if best_bits is not None:
        for j,bit in enumerate(best_bits):
            if bit: allocation[units[j]] += 1
    return allocation, max(best_score,0), time.perf_counter()-start, "exact exhaustive baseline"

food_classic, food_score, food_time, food_method = exact_allocate(villages["Food demand"].tolist(), villages["Urgency (1-10)"].tolist(), food_supply)
water_classic, water_score, water_time, water_method = exact_allocate(villages["Water demand"].tolist(), villages["Urgency (1-10)"].tolist(), water_supply)
base_df = villages.copy()
base_df["Food allocated"] = food_classic
base_df["Food unmet"] = base_df["Food demand"] - base_df["Food allocated"]
base_df["Water allocated"] = water_classic
base_df["Water unmet"] = base_df["Water demand"] - base_df["Water allocated"]
base_df["Urgency-weighted delivery"] = base_df["Urgency (1-10)"] * (base_df["Food allocated"] + base_df["Water allocated"])

if page == "Operational Overview":
    st.subheader("Operational Overview")
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Villages monitored", len(villages))
    k2.metric("Food kits allocated", f"{sum(food_classic):,} / {int(food_supply):,}", f"{food_demand} requested")
    k3.metric("Water packs allocated", f"{sum(water_classic):,} / {int(water_supply):,}", f"{water_demand} requested")
    k4.metric("Urgent villages", int((villages["Urgency (1-10)"] >= 8).sum()), "urgency ≥ 8")
    left,right = st.columns([1.55,1])
    with left:
        st.markdown("#### Resource allocation overview")
        chart_df = base_df.melt(id_vars="Village", value_vars=["Food demand","Food allocated","Water demand","Water allocated"], var_name="Measure", value_name="Packs")
        fig = px.bar(chart_df, x="Village", y="Packs", color="Measure", barmode="group", color_discrete_sequence=[NAVY,TEAL,BLUE,ORANGE])
        fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",legend_title_text="",margin=dict(l=10,r=10,t=20,b=10),xaxis_title="",yaxis_title="Packs")
        st.plotly_chart(fig,use_container_width=True)
    with right:
        st.markdown("#### Urgency profile")
        fig = px.bar(base_df.sort_values("Urgency (1-10)"), x="Urgency (1-10)", y="Village", orientation="h", color="Urgency (1-10)", color_continuous_scale=["#cfe8e6",TEAL, NAVY], range_x=[0,10])
        fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",coloraxis_showscale=False,margin=dict(l=5,r=5,t=20,b=10),xaxis_title="Urgency (1–10)",yaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
    low,mid,high = st.columns(3)
    low.metric("Food unmet demand", int(base_df["Food unmet"].sum()))
    mid.metric("Water unmet demand", int(base_df["Water unmet"].sum()))
    high.metric("Weighted delivery score", f"{food_score+water_score:.0f}")
    st.markdown("#### Current scenario snapshot")
    st.dataframe(base_df[["Village","Urgency (1-10)","Food demand","Food allocated","Food unmet","Water demand","Water allocated","Water unmet"]], use_container_width=True, hide_index=True)
    st.caption("The current classical recommendation maximizes urgency-weighted allocations while respecting each village's demand and total supply. This objective does not yet include travel time, budget, or minimum-fairness constraints.")

elif page == "Scenario Builder":
    st.subheader("Scenario Builder")
    st.write("Set the village count, edit village names and coordinates, then adjust food/water demand and urgency in the scenario editor above.")
    st.info("Changes in the editor are used by the dashboard, allocation results, map, and analytics. Village count and demand inputs have no fixed application-level maximum; practical limits depend on available memory and runtime.")
    st.dataframe(villages, use_container_width=True, hide_index=True)
    st.markdown("#### Scenario validation")
    issues=[]
    if (villages["Village"].str.strip()=="").any(): issues.append("One or more village names are blank.")
    if villages["Village"].duplicated().any(): issues.append("Village names should be unique for readable charts.")
    if not issues: st.success("Scenario inputs look valid.")
    else:
        for issue in issues: st.warning(issue)

elif page == "Resource Allocation":
    st.subheader("Resource Allocation")
    st.markdown("#### Recommended distribution · exact classical baseline")
    st.dataframe(base_df[["Village","Urgency (1-10)","Food demand","Food allocated","Food unmet","Water demand","Water allocated","Water unmet"]], use_container_width=True, hide_index=True)
    col1,col2=st.columns(2)
    with col1:
        fdf=base_df.melt(id_vars="Village",value_vars=["Food allocated","Food unmet"],var_name="Status",value_name="Kits")
        fig=px.bar(fdf,x="Village",y="Kits",color="Status",barmode="stack",color_discrete_map={"Food allocated":TEAL,"Food unmet":"#E7A35E"},title="Food: allocated vs unmet")
        fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",legend_title_text="",xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
    with col2:
        wdf=base_df.melt(id_vars="Village",value_vars=["Water allocated","Water unmet"],var_name="Status",value_name="Packs")
        fig=px.bar(wdf,x="Village",y="Packs",color="Status",barmode="stack",color_discrete_map={"Water allocated":BLUE,"Water unmet":"#E7A35E"},title="Water: allocated vs unmet")
        fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",legend_title_text="",xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
    st.markdown("#### Optimization objective")
    st.write("The prototype maximizes **urgency × delivered units** separately for food kits and water packs, subject to total supply and each village's stated demand.")
    st.caption(f"Food: {food_method} · {food_time:.6f} seconds. Water: {water_method} · {water_time:.6f} seconds. Times depend on the machine and current load.")
    csv=base_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download allocation report (CSV)", data=csv, file_name="reliefq_allocation_report.csv", mime="text/csv")

elif page == "Quantum vs Classical":
    st.subheader("Quantum vs Classical")
    st.write("Compare the classical allocation with a Qiskit QAOA candidate for a small food-kit instance. Village counts and demand inputs are not capped, but QAOA is computationally bounded because statevector simulation grows exponentially.")
    st.warning("QAOA below is a statevector simulation on a classical CPU, not execution on quantum hardware. No quantum advantage is claimed.")
    eligible = food_demand <= 20 and food_demand > 0
    if not eligible:
        st.info(f"QAOA simulation is enabled only for total food demand from 1 to 20 units because its statevector cost grows exponentially. Current food demand: {food_demand}. The classical allocation remains available for larger scenarios.")
    try:
        from qiskit import QuantumCircuit
        from qiskit.quantum_info import Statevector
        from qiskit.circuit.library import DiagonalGate
        from scipy.optimize import minimize
        qiskit_available=True
    except Exception as e:
        qiskit_available=False
        st.error("Qiskit or SciPy is unavailable in this deployment. Check requirements.txt and the Streamlit app logs.")
        st.code(str(e))
    depth = st.select_slider("QAOA depth (p)", options=[1,2,3], value=2)
    if st.button("Run QAOA comparison", type="primary", disabled=(not eligible or not qiskit_available)):
        demands=villages["Food demand"].tolist(); urgencies=villages["Urgency (1-10)"].tolist(); supply=int(food_supply)
        units=[i for i,d in enumerate(demands) for _ in range(int(d))]
        n=len(units); target=min(supply,n)
        benefits=np.array([urgencies[i] for i in units],dtype=float)
        def bits_idx(idx): return np.array([(idx>>i)&1 for i in range(n)],dtype=int)
        def utility(bits): return float(np.dot(benefits,np.asarray(bits,dtype=float)))
        def cost(bits): return -utility(bits)+30.0*(int(sum(bits))-target)**2
        costs=np.array([cost(bits_idx(i)) for i in range(2**n)])
        start=time.perf_counter()
        def circuit(params):
            gammas=params[:depth]; betas=params[depth:]
            qc=QuantumCircuit(n); qc.h(range(n))
            for layer in range(depth):
                qc.append(DiagonalGate(np.exp(-1j*gammas[layer]*costs)),range(n))
                for q in range(n): qc.rx(2*betas[layer],q)
            return qc
        def expected(params):
            sv=Statevector.from_instruction(circuit(params))
            return float(np.dot(np.asarray(sv.probabilities()),costs))
        rng=np.random.default_rng(21)
        x0=np.r_[rng.uniform(0,np.pi,depth),rng.uniform(0,np.pi/2,depth)]
        result=minimize(expected,x0,method="COBYLA",options={"maxiter":70,"rhobeg":0.7,"tol":1e-3})
        sv=Statevector.from_instruction(circuit(result.x)); probs=np.asarray(sv.probabilities())
        feasible=[]
        for idx,p in enumerate(probs):
            bits=bits_idx(idx)
            if int(sum(bits))==target: feasible.append((float(p),utility(bits),bits))
        q_runtime=time.perf_counter()-start
        if not feasible:
            st.error("No feasible bitstring was sampled from the final state. Try a different QAOA depth.")
        else:
            feasible.sort(key=lambda x:(x[1],x[0]),reverse=True)
            p, q_score, q_bits=feasible[0]
            q_alloc=[0]*len(demands)
            for j,bit in enumerate(q_bits):
                if bit: q_alloc[units[j]] += 1
            q_gap=0 if food_score==0 else max(0,100*(food_score-q_score)/food_score)
            q_feasible_prob=sum(item[0] for item in feasible)
            a,b,c,d=st.columns(4)
            a.metric("Exact classical score",f"{food_score:.1f}")
            b.metric("QAOA candidate score",f"{q_score:.1f}")
            c.metric("Objective gap",f"{q_gap:.1f}%")
            d.metric("Feasible-state probability",f"{q_feasible_prob:.1%}")
            compare=base_df[["Village","Food demand","Urgency (1-10)","Food allocated"]].copy()
            compare["QAOA candidate"] = q_alloc
            st.dataframe(compare,use_container_width=True,hide_index=True)
            chart=compare.melt(id_vars="Village",value_vars=["Food allocated","QAOA candidate"],var_name="Method",value_name="Kits")
            fig=px.bar(chart,x="Village",y="Kits",color="Method",barmode="group",color_discrete_sequence=[TEAL,BLUE],title="Food allocation comparison")
            fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",legend_title_text="",xaxis_title="")
            st.plotly_chart(fig,use_container_width=True)
            r1,r2=st.columns(2)
            r1.metric("Classical baseline runtime",f"{food_time:.6f} s")
            r2.metric("QAOA simulation runtime",f"{q_runtime:.4f} s")
            st.caption(f"Probability of the selected QAOA bitstring: {p:.3f}. The QAOA candidate is approximate; runtime is not a fair quantum-vs-classical hardware benchmark.")
            if abs(food_score-q_score)<1e-9: st.success("This QAOA candidate matches the exact classical objective for this run.")
            else: st.info("This QAOA candidate did not match the exact optimum in this run. That is a legitimate outcome of an approximate heuristic.")

elif page == "Analytics & Map":
    st.subheader("Analytics & Geographic View")
    st.markdown("#### Village locations")
    map_df=base_df.copy()
    map_df["Hover details"] = map_df.apply(lambda r: f"Urgency {r['Urgency (1-10)']} · Food {r['Food allocated']}/{r['Food demand']} · Water {r['Water allocated']}/{r['Water demand']}",axis=1)
    fig=px.scatter_geo(map_df,lat="Latitude",lon="Longitude",hover_name="Village",hover_data={"Latitude":":.4f","Longitude":":.4f","Urgency (1-10)":True,"Food allocated":True,"Food demand":True,"Water allocated":True,"Water demand":True},color="Urgency (1-10)",size="Urgency (1-10)",color_continuous_scale=["#b8e3df",TEAL,NAVY],projection="natural earth",title="Configured village locations and urgency")
    fig.update_geos(fitbounds="locations", visible=True, showcountries=True, showland=True, landcolor="#f1f5f9", countrycolor="#cbd5e1")
    fig.update_layout(height=500,margin=dict(l=0,r=0,t=45,b=0),paper_bgcolor="white",geo_bgcolor="white",coloraxis_colorbar_title="Urgency")
    st.plotly_chart(fig,use_container_width=True)
    left,right=st.columns(2)
    with left:
        fig=px.pie(base_df,names="Village",values="Food allocated",hole=.55,title="Share of food allocation")
        fig.update_layout(paper_bgcolor="white",legend_title_text="")
        st.plotly_chart(fig,use_container_width=True)
    with right:
        fig=px.bar(base_df,x="Village",y=["Food unmet","Water unmet"],barmode="group",title="Unmet demand by village",color_discrete_sequence=[ORANGE,BLUE])
        fig.update_layout(plot_bgcolor="white",paper_bgcolor="white",legend_title_text="",xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
    st.caption("Map positions are based on the latitude/longitude values in Scenario Builder. Enter realistic coordinates for your scenario; the map does not verify real-world incident reports.")

else:
    st.subheader("About ReliefQ")
    st.markdown("""
**Problem statement**  
Emergency response teams have limited food and water supplies, while affected villages have different demand levels and urgency. ReliefQ is a decision-support prototype that helps explore transparent, urgency-aware allocations.

**Classical optimization**  
For each resource, the exact baseline maximizes urgency-weighted units delivered subject to available supply and each village's demand. Small instances use exhaustive search; larger instances use exact dynamic programming for this simplified objective.

**Quantum component**  
The Quantum vs Classical section uses Qiskit QAOA with a statevector simulator for a small food-kit instance (up to 20 demand units). Village count, resource supply, and demand inputs have no fixed application-level maximum, but large scenarios may be constrained by available compute resources.

**Current prototype limitations**  
The demo uses user-entered scenario data, optimizes food and water separately, and does not yet model road distance, vehicle capacity, budgets, spoilage, or minimum-fairness guarantees. QAOA runs on a classical CPU; this is not quantum hardware and does not demonstrate quantum advantage. Validate real allocations with relief professionals before operational use.
""")
    st.markdown("#### Technology")
    tech1,tech2,tech3,tech4=st.columns(4)
    tech1.info("**UI & charts**\n\nStreamlit + Plotly")
    tech2.info("**Classical baseline**\n\nExact enumeration / DP")
    tech3.info("**Quantum algorithm**\n\nQiskit QAOA simulator")
    tech4.info("**Reporting**\n\nCSV export")

st.divider()
st.caption(f"ReliefQ prototype · Scenario updated {datetime.now().strftime('%d %b %Y, %H:%M')} · Educational decision-support only.")
