"""BaseGuard – web UI.   streamlit run app.py

Actions and verdicts shown here come only from the agent's assessments. Before the agent has run on a
frame, the UI shows the raw measurements its tools would return.
"""
from __future__ import annotations

import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agent import llm_client
from agent.chat import answer
from agent.runner import DEFAULT_EFFORT, _normalise, _valid, actions_by_id, assess, cached
import base64
import time

from agent.tools import ACTIONS, SCHEMAS, ToolBox, submit_schema
from core.data import images, zones
from core.render import annotate, to_rgb
from core.scene import Scene

st.set_page_config(page_title="BaseGuard · Üs Çevre Güvenliği", page_icon="🛡️", layout="wide")

HEX = {"hemen teyit/müdahale": "#e5484d", "izlemeye al": "#f76b15", "işlem gerekmez": "#8b8d98", None: "#3e63dd"}
ICON = {"hemen teyit/müdahale": "🔴", "izlemeye al": "🟠", "işlem gerekmez": "⚪", None: "🔵"}
SHORT = {"hemen teyit/müdahale": "MÜDAHALE", "izlemeye al": "İZLE", "işlem gerekmez": "İŞLEM YOK", None: "değerlendirilmedi"}
TOOL_ICON = {"get_image_info": "🖼️", "detect_vehicles": "🚗", "match_tracks": "🔗", "get_motion": "📈",
             "get_reports": "📝", "view_region": "🔍", "get_track_points": "📍", "search_reports": "🔎"}

st.markdown("""
<style>
.lvl {display:inline-block;padding:2px 10px;border-radius:6px;font-weight:700;color:#111;font-size:0.85rem}
.card {border:1px solid rgba(128,128,128,.3);border-radius:10px;padding:12px 14px;margin-bottom:10px}
.muted {opacity:.7;font-size:.85rem}
.headline {font-size:1.15rem;font-weight:600;margin:6px 0}
</style>""", unsafe_allow_html=True)


def badge(action: str | None, confidence: str | None = None) -> str:
    conf = f' · güven {confidence}' if confidence else ""
    return f'<span class="lvl" style="background:{HEX[action]}">{SHORT[action]}{conf}</span>'


@st.cache_resource(show_spinner=False)
def scene(image_id: str) -> Scene:
    return Scene(image_id)


def level_of(image_id: str) -> str | None:
    """The agent's overall action for a frame (None = not assessed yet)."""
    c = cached(image_id)
    return c["brief"].get("action") if c else None


def local_xy(lat, lon, lat0, lon0):
    return (lon - lon0) * math.cos(math.radians(lat0)) * 111_320, (lat - lat0) * 110_540


ids = sorted(images(), key=lambda k: images()[k].time)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🛡️ BaseGuard")
    st.caption("Drone karesi + hareket kayıtları + saha raporları → ajanın gerekçeli değerlendirmesi")
    if llm_client.available():
        st.success(f"Ajan hazır · {llm_client.MODEL}", icon="✅")
        if st.button("Bütçeyi kontrol et", width="stretch"):
            st.session_state["budget"] = llm_client.budget_info()
        if b := st.session_state.get("budget"):
            st.caption(f"Harcanan: ${b['spend']:.3f} / ${b['max_budget']}")
    else:
        st.warning("GLM_API_KEY yok · ajan çalıştırılamaz, yalnızca ölçümler gösteriliyor", icon="⚠️")
    st.divider()
    sel = st.radio("Kareler (çekim saatine göre)", ids,
                   format_func=lambda i: f"{ICON[level_of(i)]} {images()[i].time} · {i}",
                   index=ids.index(st.session_state.get("sel", ids[0])))
    st.session_state["sel"] = sel
    effort = st.select_slider("Ajanın düşünme seviyesi", ["low", "high", "max"], value=DEFAULT_EFFORT)

DEV = st.query_params.get("dev") == "1"   # development-only tool playground: open with ?dev=1
_tabs = st.tabs(["📍 Günlük durum", "🔎 Kare analizi", "💬 Ajana sor"] + (["🧪 Araç testi"] if DEV else []))
tab_day, tab_img, tab_chat = _tabs[:3]
tab_tools = _tabs[3] if DEV else None

# ---------------------------------------------------------------- day overview
with tab_day:
    base_ll, base_name, zs = zones()
    rows = []
    for i in ids:
        s, c = scene(i), cached(i)
        info = s.info()
        rows.append(dict(saat=info["capture_time"], kare=i, eylem=SHORT[level_of(i)],
                         bölge=info["nearest_zone"], üsse_km=round(info["dist_to_base_m"] / 1000, 1),
                         özet=c["brief"]["headline"] if c else "",
                         lat=info["center"][0], lon=info["center"][1], lv=level_of(i)))
    df = pd.DataFrame(rows)
    done = int(df.lv.notna().sum())

    k = st.columns(4)
    k[0].metric("Kare", len(df))
    k[1].metric("Ajan değerlendirdi", f"{done}/{len(df)}")
    k[2].metric("🔴 Müdahale önerilen", int((df.lv == ACTIONS[0]).sum()))
    k[3].metric("🟠 İzlemeye alınan", int((df.lv == ACTIONS[1]).sum()))

    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Scattermap(lat=[z.center[0] for z in zs], lon=[z.center[1] for z in zs], mode="markers+text",
                                    text=[z.name for z in zs], textposition="top center",
                                    marker=dict(size=9, color="#5b5bd6"), name="bölgeler", hoverinfo="text"))
        for lv in [None, *ACTIONS[::-1]]:
            d = df[df.lv.isna()] if lv is None else df[df.lv == lv]
            if len(d):
                fig.add_trace(go.Scattermap(lat=d.lat, lon=d.lon, mode="markers", name=SHORT[lv],
                                            marker=dict(size=16 if lv in ACTIONS[:2] else 11, color=HEX[lv]),
                                            text=d.saat + " " + d.kare + "<br>" + d.özet, hoverinfo="text"))
        fig.add_trace(go.Scattermap(lat=[base_ll[0]], lon=[base_ll[1]], mode="markers+text", text=[base_name],
                                    textposition="bottom center", marker=dict(size=22, color="#111"), name="üs"))
        fig.update_layout(map=dict(style="open-street-map", center=dict(lat=base_ll[0], lon=base_ll[1]), zoom=11.3),
                          height=520, margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig, width="stretch")
    with right:
        st.markdown("#### Ajanın öncelik sırası")
        order = {lv: n for n, lv in enumerate(ACTIONS)}
        rank = df.assign(o=df.lv.map(lambda x: order.get(x, 9))).sort_values(["o", "saat"])
        st.dataframe(rank[["saat", "kare", "eylem", "bölge", "üsse_km", "özet"]], hide_index=True, height=470, width="stretch")

    if llm_client.available() and done < len(df) and st.button(f"Kalan {len(df) - done} kareyi ajanla değerlendir"):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        prog, errs = st.progress(0.0), []
        todo = [i for i in ids if not cached(i)]
        with ThreadPoolExecutor(3) as ex:
            futs = {ex.submit(assess, i, None, effort): i for i in todo}
            for n, f in enumerate(as_completed(futs), 1):
                if f.exception():
                    errs.append(f"{futs[f]}: {f.exception()}")
                prog.progress(n / len(todo))
        for e in errs:
            st.error(e)
        if not errs:
            st.rerun()


# ---------------------------------------------------------------- single frame
def render_event(ev: dict):
    k, t, d = ev["kind"], ev["title"], ev["detail"]
    if k == "tool_call":
        st.markdown(f"{TOOL_ICON.get(t, '🛠️')} **{t}**" + (f" `{json.dumps(d, ensure_ascii=False)}`" if d else ""))
    elif k == "tool_result":
        with st.expander("sonuç", expanded=False):
            try:
                st.json(json.loads(d), expanded=1)
            except (json.JSONDecodeError, TypeError):
                st.code(str(d))
    elif k == "thought":
        with st.expander("🧠 düşünce"):
            st.caption(d)
    elif k == "say":
        st.markdown(f"💬 {d}")
    elif k == "warn":
        st.warning(f"{t}: {d}")
    elif k == "audit":
        (st.success if not d else st.info)(f"🔎 {t}" + "".join(f"\n- {x}" for x in d))


def render_brief(b: dict):
    st.markdown(f'{badge(b["action"])}<div class="headline">{b["headline"]}</div>', unsafe_allow_html=True)
    st.write(b["brief"])
    for a in b.get("audit") or []:
        st.warning(f"Denetim uyarısı: {a}")
    for v in b.get("vehicles", []):
        ev = " · ".join(v.get("evidence") or [])
        tid = f" ({v['track_id']})" if v.get("track_id") and v["track_id"] != v["id"] else ""
        st.markdown(f'<div class="card">{badge(v["action"], v["confidence"])} <b>{v["id"]}{tid}</b> — {v["reason"]}'
                    f'{"<br><span class=muted>dayanak: " + ev + "</span>" if ev else ""}</div>', unsafe_allow_html=True)
    if b.get("uncertainties"):
        st.markdown("**Belirsizlikler**\n" + "\n".join(f"- {u}" for u in b["uncertainties"]))


def track_figure(info: dict, m: dict, color: str) -> go.Figure:
    b = info["base"]
    pts = m["polyline"]
    xy = [local_xy(la, lo, b["lat"], b["lon"]) for _, la, lo in pts]
    fig = go.Figure()
    for r in (1000, 2000, 4000, 6000):
        th = [k * 2 * math.pi / 90 for k in range(91)]
        fig.add_trace(go.Scatter(x=[r * math.cos(a) for a in th], y=[r * math.sin(a) for a in th], mode="lines",
                                 line=dict(color="rgba(128,128,128,.3)", dash="dot", width=1), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="lines+markers",
                             line=dict(color=color, width=2), marker=dict(size=4), name=m["track_id"],
                             text=[f"{t} · üsse {math.hypot(*p) / 1000:.1f} km" for (t, _, _), p in zip(pts, xy)], hoverinfo="text"))
    for s in m["stops"]:
        i = next(k for k, (t, _, _) in enumerate(pts) if t == s["start"])
        fig.add_trace(go.Scatter(x=[xy[i][0]], y=[xy[i][1]], mode="markers+text", text=[f"{s['start']} · {s['minutes']} dk"],
                                 textposition="top right", marker=dict(size=10, symbol="circle-open", color="#888"),
                                 showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[xy[-1][0]], y=[xy[-1][1]], mode="markers", marker=dict(size=12, color=color),
                             name=f"çekim anı ({pts[-1][0]})"))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers+text", text=["ÜS"], textposition="bottom center",
                             marker=dict(size=16, symbol="diamond", color="#e5484d"), name="üs"))
    fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(scaleanchor="x", title="kuzey (m)"),
                      xaxis=dict(title="doğu (m)"), legend=dict(orientation="h", y=-0.2))
    return fig


with tab_img:
    s = scene(sel)
    info = s.info()
    st.markdown(f"### {sel} · {info['capture_time']} · {info['nearest_zone']} yakını "
                f"<span class='muted'>üssün {info['direction_from_base']}sunda {info['dist_to_base_m'] / 1000:.1f} km · "
                f"{info['footprint_m'][0]}×{info['footprint_m'][1]} m</span>", unsafe_allow_html=True)
    result = st.session_state.get(f"res_{sel}") or cached(sel)
    col_img, col_agent = st.columns([3, 2])
    with col_img:
        st.image(to_rgb(annotate(s, actions_by_id(result["brief"]) if result else None, max_w=1600)), width="stretch",
                 caption="Mavi = henüz değerlendirilmedi · kırmızı = müdahale, turuncu = izle, gri = işlem yok (ajanın kararı) · kesikli kutu = güven < 0.3 · "
                         "daire = tespiti olmayan hareket kaydı · pembe × = rapor noktası")
    with col_agent:
        c1, c2 = st.columns(2)
        can = llm_client.available()
        run = c1.button("▶ Ajanı çalıştır", type="primary", width="stretch", disabled=not can or bool(result))
        again = c2.button("↻ Yeniden değerlendir", width="stretch", disabled=not can or not result)
        if run or again:
            with st.status("Ajan çalışıyor…", expanded=True) as box:
                try:
                    out = assess(sel, cb=render_event, effort=effort, use_cache=False)
                    box.update(label=f"Tamamlandı · {out['usage']['calls']} LLM çağrısı · {out['usage']['seconds']} sn",
                               state="complete", expanded=False)
                    st.session_state[f"res_{sel}"] = result = out
                except Exception as ex:
                    box.update(label=f"Hata: {type(ex).__name__}: {ex}", state="error")
        if result:
            render_brief(result["brief"])
            with st.expander(f"Ajanın adımları ({sum(e['kind'] == 'tool_call' for e in result['trace'])} araç çağrısı)"):
                for ev in result["trace"]:
                    render_event(ev)
        elif not can:
            st.info("Ajanı çalıştırmak için .env dosyasına GLM_API_KEY ekleyin. Aşağıda ajanın araçlarının döndüreceği ölçümler var.")
        else:
            st.info("Ajanı çalıştırın. Aşağıda araçların döndürdüğü ölçümler var.")

    st.markdown("#### Araçların döndürdüğü ölçümler")
    st.caption("Bunlar ajana verilen ham ölçümlerdir; yorum ve karar ajana aittir.")
    tm = s.track_matches()
    by_det = {r["detection"]: r for r in tm["matches"]}
    det_rows = [dict(id=d["id"], sınıf=d["cls"], güven=d["conf"], enlem=d["lat"], boylam=d["lon"],
                     üsse_m=d["dist_to_base_m"], kayıt=by_det[d["id"]]["track_id"] or "—",
                     eşleşme_m=by_det[d["id"]]["dist_m"]) for d in s.detections()["detections"]]
    det_rows += [dict(id=t["track_id"], sınıf="(tespit yok)", güven=None, enlem=t["lat"], boylam=t["lon"],
                      üsse_m=None, kayıt=t["track_id"], eşleşme_m=None) for t in tm["tracks_in_frame_without_detection"]]
    st.dataframe(pd.DataFrame(det_rows), hide_index=True, width="stretch")

    tids = [r["track_id"] for r in tm["matches"] if r["track_id"]] + [t["track_id"] for t in tm["tracks_in_frame_without_detection"]]
    if tids:
        cv1, cv2 = st.columns([3, 2])
        pick = cv2.selectbox("Hareket kaydı", tids)
        m = s.motion(pick, with_polyline=True)
        lv = actions_by_id(result["brief"]).get(pick) if result else None
        cv1.plotly_chart(track_figure(info, m, HEX[lv]), width="stretch")
        with cv2:
            if lv:
                st.markdown(f"Ajanın kararı: {badge(lv)}", unsafe_allow_html=True)
            km = lambda x: f"{x / 1000:.2f} km"
            series = m["dist_to_base_series"]
            st.markdown("\n".join([
                "- üsse uzaklık: " + " → ".join(f"{t} {km(d)}" for t, d in series[::2] + ([series[-1]] if len(series) % 2 == 0 else [])),
                f"- en yakın geçiş: {km(m['min_dist_to_base_m'])} ({m['min_dist_time']})",
                f"- hız: son 10 dk {m['speed_last_10m_ms']} m/s · son 30 dk {m['speed_last_30m_ms']} m/s",
                f"- yaklaşma hızı (30 dk): {m['closing_rate_30m_ms']} m/s"
                + (f" · tahmini varış {m['eta_to_base_min']} dk" if m["eta_to_base_min"] else ""),
                f"- yön: {m['heading_compass'] or '—'} (üsse göre {m['heading_vs_base_deg']}°)",
                f"- üs etrafında süpürülen açı: {m['base_sweep_deg']:+d}° · toplam yol {km(m['path_len_m'])}",
                "- duraklamalar: " + (", ".join(f"{x['start']} ({x['minutes']} dk)" for x in m["stops"]) or "yok"),
                "- son 1 saatte yakın seyreden: "
                + (", ".join(f"{c['track_id']} (ort. {c['mean_sep_m']} m)" for c in m["moving_together_with"]) or "yok"),
            ]))

    st.markdown("#### Saha raporları")
    rep = s.reports()
    verdicts = {r["rid"]: r for r in (result["brief"].get("reports") or []) if r.get("rid")} if result else {}
    if not rep["reports"]:
        st.caption("Bu kareyle ilgili rapor yok.")
    for r in rep["reports"]:
        if r["scope"] == "koordinat":
            where = "nokta karenin içinde" if r["dist_point_to_frame_m"] == 0 else f"nokta karenin {r['dist_point_to_frame_m']} m dışında"
            near = r.get("within_60m_of_point") or []
            near_txt = ", ".join(f"{n['id']} {n['cls']}" + (f" {n['conf']:.2f}" if n["conf"] else "") + f" · {n['dist_m']} m"
                                 for n in near[:6])
        else:
            where, near_txt = f"bölge: {r.get('zone') or '—'}", ""
        v = verdicts.get(r["rid"])
        st.markdown(f'<div class="card"><b>{r["rid"]}</b> · {r["time"]} · {r["source"]} · {where} · '
                    f'çekimden {r["minutes_before_capture"]} dk önce<br>“{r["text"]}”'
                    + (f'<br><span class="muted">noktanın 60 m içinde: {near_txt}</span>' if near_txt else "")
                    + (f"<br><b>Ajan: {v['verdict']}</b> — {v['reason']}"
                       + "".join(f"<br><span class='muted'>· {c.get('claim')}: {c.get('finding')}</span>" for c in v.get("claims_checked") or [])
                       if v else "")
                    + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- chat
with tab_chat:
    st.markdown(f"#### {sel} hakkında ajana sorun")
    res = st.session_state.get(f"res_{sel}") or cached(sel)
    if not res:
        st.info("Önce 'Kare analizi' sekmesinde ajanı çalıştırın.")
    else:
        hist = st.session_state.setdefault(f"chat_{sel}", [])
        for h in hist:
            st.chat_message(h["role"]).write(h["content"])
        st.caption("Örnek: “D6 neden bu seviyede?” · “R125'e güvenebilir miyiz?” · “Bu karede ağır araç var mı?”")
        if q := st.chat_input("Sorunuz…"):
            st.chat_message("user").write(q)
            with st.chat_message("assistant"), st.spinner("Düşünüyor…"):
                a, used = answer(q, res, hist)
                st.write(a)
                if used:
                    st.caption("kullanılan araçlar: " + ", ".join(used))
            hist += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]

# ---------------------------------------------------------------- tool playground
def _show_tool_output(text: str, img: str | None):
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "error" in data:
            st.error(data["error"])
        st.json(data, expanded=2)
    except json.JSONDecodeError:
        st.code(text)
    if img:
        st.image(base64.b64decode(img.split(",", 1)[1]), caption="ajana gösterilen görüntü")
    st.caption(f"ajana giden metin: {len(text):,} karakter (~{len(text) // 3:,} token)")


if DEV:
    with tab_tools:
        st.markdown(f"#### Araçları elle çalıştır · {sel}")
        st.caption("Ajanın kullandığı ToolBox.call ile aynı yol: burada gördüğünüz JSON ve görüntü, ajana giden içeriğin kendisidir. LLM çağrılmaz.")
        tb = ToolBox(scene(sel))
        tools = {sc["function"]["name"]: sc["function"] for sc in SCHEMAS + [submit_schema(scene(sel))]}
        st.caption(f"Ajanın araçları ({len(tools)}): " + " · ".join(tools))

        with st.expander("Hızlı kontrol: tüm akışı sırayla çalıştır", expanded=False):
            if st.button("▶ Tüm araçları sırayla çalıştır (submit_assessment hariç: onu aşağıda test edin)"):
                steps = [("get_image_info", {}), ("detect_vehicles", {}), ("match_tracks", {})]
                steps += [("get_motion", {"track_id": r["track_id"]}) for r in scene(sel).track_matches()["matches"] if r["track_id"]]
                steps += [("get_motion", {"track_id": t["track_id"]}) for t in scene(sel).track_matches()["tracks_in_frame_without_detection"]]
                steps += [("get_reports", {"include_general": True})]
                first_det = next(iter(scene(sel).detections()["detections"]), None)
                first_trk = next((r["track_id"] for r in scene(sel).track_matches()["matches"] if r["track_id"]), None)
                if first_det:
                    steps.append(("view_region", {"target": first_det["id"]}))
                if first_trk:
                    steps.append(("get_track_points", {"track_id": first_trk}))
                c = scene(sel).info()["center"]
                steps.append(("search_reports", {"lat": c[0], "lon": c[1], "radius_m": 1000}))
                for name, args in steps:
                    t0 = time.time()
                    text, img = tb.call(name, args)
                    ok = "error" not in text[:40]
                    with st.expander(f"{'✅' if ok else '❌'} {name} {json.dumps(args) if args else ''} · {(time.time() - t0) * 1000:.0f} ms"):
                        _show_tool_output(text, img)

        left, right = st.columns([1, 2])
        with left:
            name = st.selectbox("Araç", list(tools))
            spec = tools[name]
            st.caption(spec["description"])
            props, req = spec["parameters"]["properties"], set(spec["parameters"].get("required", []))
            # suggestions for ids present in this frame
            tm = scene(sel).track_matches()
            track_ids = [r["track_id"] for r in tm["matches"] if r["track_id"]] + [t["track_id"] for t in tm["tracks_in_frame_without_detection"]]
            det_ids = [d["id"] for d in scene(sel).detections()["detections"]]
            args = {}
            if name == "submit_assessment":
                first = next(iter(det_ids), "D1")
                req_v, _ = scene(sel).subjects()
                coord = [r["rid"] for r in scene(sel).reports()["reports"] if r["scope"] == "koordinat"]
                template = {"action": "izlemeye al", "headline": "Örnek başlık", "brief": "Örnek değerlendirme metni.",
                            "vehicles": {v: {"action": "işlem gerekmez", "confidence": "yüksek", "reason": "örnek gerekçe"}
                                         for v in req_v},
                            "reports": {r: {"verdict": "doğrulanamaz", "claims_checked": [], "reason": "örnek"} for r in coord},
                            "uncertainties": []}
                raw = st.text_area("argümanlar (JSON)", json.dumps(template, ensure_ascii=False, indent=1), height=380,
                                   key=f"tool_{sel}_submit")
                props = {}
            for p, ps in props.items():
                label = f"{p}{' *' if p in req else ''}"
                key = f"tool_{sel}_{name}_{p}"
                if p == "track_id":
                    v = st.selectbox(label, track_ids + ["(elle gir)"], key=key)
                    if v == "(elle gir)":
                        v = st.text_input("track_id (ör. T0003)", key=key + "_free")
                elif p == "target":
                    v = st.selectbox(label, det_ids + track_ids + ["(elle gir)"], key=key)
                    if v == "(elle gir)":
                        v = st.text_input("target", key=key + "_free")
                elif ps["type"] == "boolean":
                    v = st.checkbox(label, key=key)
                elif ps["type"] in ("number", "integer"):
                    default = {"lat": scene(sel).info()["center"][0], "lon": scene(sel).info()["center"][1]}.get(p)
                    raw = st.text_input(label, value="" if default is None else str(default), key=key,
                                        help=ps.get("description"))
                    v = (int(raw) if ps["type"] == "integer" else float(raw)) if raw.strip() else None
                else:
                    v = st.text_input(label, key=key, help=ps.get("description")) or None
                if v not in (None, ""):
                    args[p] = v
            run_tool = st.button("Çalıştır", type="primary", width="stretch")
            st.code(f"{name}({json.dumps(args, ensure_ascii=False)})", language="python")
        with right:
            if run_tool and name == "submit_assessment":
                try:
                    sub = json.loads(raw)
                    err = _valid(sub)
                    from agent.audit import audit as _audit
                    issues = [] if err else _audit(sub, scene(sel), [])
                    if err:
                        st.error(f"Doğrulamadan geçmedi — ajana dönecek mesaj: Geçersiz: {err}. Düzeltip tekrar gönder.")
                    else:
                        st.success("Şema doğrulamasından geçti.")
                        if issues:
                            st.warning("Denetim bulguları (ajana düzeltme için geri dönerdi; bu testte araç çıktısı olmadığından sayı ve kimlik kontrolleri katıdır):\n- " + "\n- ".join(issues))
                        st.markdown("**Önizleme (Kare analizi sekmesindeki görünüm):**")
                        nb = _normalise(sub, scene(sel), issues)
                        render_brief(nb)
                        st.image(to_rgb(annotate(scene(sel), actions_by_id(nb), max_w=1200)), caption="ajanın kararlarıyla renklenmiş kare")
                except json.JSONDecodeError as ex:
                    st.error(f"JSON hatası: {ex}")
            elif run_tool:
                t0 = time.time()
                text, img = tb.call(name, args)
                st.caption(f"{(time.time() - t0) * 1000:.0f} ms")
                _show_tool_output(text, img)
            else:
                st.info("Soldan bir araç seçip çalıştırın.")
