from datetime import datetime, timezone
import os
from html import escape
from pathlib import Path
import base64
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from vulture.storage import DB, ROOT, MARKETS, connect

ART = ROOT / "assets" / "vulture-capital.png"
ICON = ART if ART.exists() else ROOT / "assets" / "vulture.svg"
st.set_page_config(page_title="Vulture Capital",page_icon=str(ICON),layout="wide")
st.markdown('''<style>
.stApp {background:radial-gradient(ellipse at 95% 0%,#f7ebd6 0,transparent 36%),#f7f8fa}
.block-container {max-width:1600px;padding-top:2.3rem}
[data-testid="stSidebar"] {background:#eef1f4;border-right:1px solid #dde3ea}
h1,h2,h3 {letter-spacing:-.035em;color:#172636}
[data-testid="stMetric"] {background:#fff;border:1px solid #e1e5eb;border-radius:16px;padding:18px}
.eyebrow {color:#9a692b;font-size:12px;letter-spacing:3px;font-weight:700}
.hero {background:#172636;border-radius:22px;padding:26px 32px;margin-bottom:24px;color:#f5f1e8;display:flex;align-items:center;gap:24px;overflow:hidden}
.hero-art {width:165px;height:165px;object-fit:cover;border-radius:16px;flex-shrink:0}
@media(max-width:650px){.hero{padding:22px;gap:12px}.hero-art{width:80px;height:80px}.hero h1{font-size:27px!important}}
.hero h1 {color:#f5f1e8;font-size:42px;margin:3px 0 6px}
.hero p {color:#bdc9d5;margin:0;max-width:800px}
.status {background:#fff;border:1px solid #e1e5eb;border-radius:12px;padding:14px 18px;margin:14px 0;color:#526273}
button[data-baseweb="tab"] {font-weight:600;font-size:15px}
</style>''',unsafe_allow_html=True)


@st.cache_data(ttl=120)
def query(sql, params=(), revision=0):
    with connect(readonly=True) as con:
        return pd.read_sql_query(sql,con,params=params)


@st.cache_data(ttl=300)
def sync_snapshot(url, token):
    from vulture.snapshots import download
    download(url,token)


manifest_url=os.environ.get("VULTURE_SNAPSHOT_MANIFEST_URL", "")
token=os.environ.get("VULTURE_SNAPSHOT_TOKEN", "")
if not manifest_url and any(p.exists() for p in [ROOT/".streamlit"/"secrets.toml",Path.home()/".streamlit"/"secrets.toml"]):
    try:
        manifest_url=st.secrets.get("VULTURE_SNAPSHOT_MANIFEST_URL", "")
        token=st.secrets.get("VULTURE_SNAPSHOT_TOKEN", "")
    except FileNotFoundError:
        pass
if manifest_url:
    try:
        sync_snapshot(manifest_url,token)
    except Exception:
        st.warning("Yayımlanan veri kopyası alınamadı. Varsa son sağlam yerel kopya gösteriliyor.")


if not DB.exists():
    st.title("Vulture Capital")
    st.info("Henüz veri yüklenmedi. Günlük veri akışı veya mevcut StockWizard verilerinin aktarımı bekleniyor.")
    st.stop()
revision = int(DB.stat().st_mtime // 60)
logo = base64.b64encode(ICON.read_bytes()).decode()
logo_mime = "image/png" if ICON.suffix==".png" else "image/svg+xml"
with st.sidebar:
    st.markdown(f'<img src="data:{logo_mime};base64,{logo}" width="100" style="border-radius:18px" alt="Vulture Capital akbaba logosu">',unsafe_allow_html=True)
    st.title("Vulture Capital")
    st.caption("SABIRLA BEKLE. DERİNLİĞİ OKU.")
    market_label = st.radio("Piyasa",["BIST · Türkiye","NASDAQ / NYSE · ABD"])
    market = "BIST" if market_label.startswith("BIST") else "US"
    currency = "₺" if market=="BIST" else "$"
    page = st.radio("Çalışma alanı",["Fırsat radarı","Piyasa radarı","Hisse inceleme","Karşılaştırma","Veri durumu"])
    st.divider()
    st.caption("Günlük veri • İstanbul 02.30")
    st.caption("Uygulamayı açmak veri indirmeyi tetiklemez.")
    if st.button("Görünümü yenile",use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown(f'''<div class="hero"><div><div class="eyebrow">VULTURE CAPITAL / THE PATIENT OPPORTUNIST</div>
<h1>{'Borsa İstanbul' if market=='BIST' else 'NASDAQ & NYSE'}</h1>
<p>Zirvede kalabalık, dipte sessizlik.<br>Biz sessizliği izleriz. Derin düşüşleri, dip bölgelerini ve dönüş izlerini araştırırız.</p></div>
<img class="hero-art" src="data:{logo_mime};base64,{logo}" alt="Sabırla fırsat kollayan akbaba"></div>''',unsafe_allow_html=True)
data = query("SELECT * FROM snapshot WHERE market=?",(market,),revision)
if data.empty:
    st.info("Bu piyasa için henüz kullanılabilir veri yok.")
    st.stop()
asof = data["asof"].max()
oldest = data["asof"].min()
st.markdown(f'<div class="status">VERİ TARİHİ <b>{escape(str(asof))}</b> &nbsp; / &nbsp; {len(data):,} hisse &nbsp; / &nbsp; {currency} &nbsp; / &nbsp; Gün sonu verileri</div>',unsafe_allow_html=True)
stale = (pd.Timestamp.now(tz="UTC").date()-pd.Timestamp(asof).date()).days
if stale > 4:
    st.warning(f"Görüntülenen veriler {stale} gün önceye ait. Güncel fiyat olarak değerlendirmeyin; Veri durumu bölümünü kontrol edin.")
if oldest != asof:
    st.caption(f"Hisse bazında veri tarihleri {oldest} – {asof} arasında değişiyor. Tablo her hissenin kendi tarihini gösterir.")

RETURNS = {"1 gün":"r_1d","1 hafta":"r_1w","1 ay":"r_1m","3 ay":"r_3m","6 ay":"r_6m","1 yıl":"r_1y"}


def price_history(symbol):
    frame = query("SELECT date,close,adj_close,volume FROM prices WHERE market=? AND symbol=? ORDER BY date",
                  (market,symbol),revision)
    frame["date"] = pd.to_datetime(frame.date)
    return frame


def table(frame):
    display = frame.copy()
    for col in RETURNS.values():
        display[col] *= 100
    display.pct_from_hi *= 100
    labels = {"symbol":"Sembol","name":"Şirket","asof":"Veri tarihi","last_price":f"Son fiyat ({currency})",
              **{v:f"{k} (%)" for k,v in RETURNS.items()},"vol_z":"Hacim Z","pct_from_hi":"Zirveye uzaklık (%)"}
    cols = list(labels)
    st.dataframe(display[cols],hide_index=True,use_container_width=True,height=540,
                 column_config={k:st.column_config.NumberColumn(v,format="%.2f") if k not in ("symbol","name","asof") else v for k,v in labels.items()})
    st.download_button("CSV indir",display[cols].rename(columns=labels).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"vulture_{market.lower()}_{asof}.csv",mime="text/csv")


if page == "Fırsat radarı":
    st.subheader("Dipte iz sür")
    st.write("Fiyatın geride bıraktığı zirve, yaklaştığı dip ve hacimdeki hareket: fırsat araştırmasına üç farklı açıdan bak.")
    c1,c2,c3 = st.columns(3)
    max_low = c1.slider("Yıllık kapanış dibine en fazla uzaklık (%)",0,100,20)
    min_fall = c2.slider("Yıllık kapanış zirvesinden en az düşüş (%)",0,95,25)
    max_age = c3.slider("Veri yaşı en fazla (gün)",1,30,7)
    screen = data.copy()
    adjusted_latest = screen.hi_52w * (1 + screen.pct_from_hi)
    screen["dip_uzaklik"] = (adjusted_latest / screen.lo_52w.where(screen.lo_52w>0)-1)*100
    screen["veri_yasi"] = (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()-pd.to_datetime(screen["asof"])).dt.days
    candidates = screen[(screen.dip_uzaklik<=max_low)&(screen.pct_from_hi*100<=-min_fall)&(screen.veri_yasi<=max_age)]
    candidates = candidates.sort_values("dip_uzaklik")
    x,y,z = st.columns(3)
    x.metric("Radara giren",len(candidates))
    y.metric("İzlenen evren",len(data))
    z.metric("Yaklaşım","Sabırlı / Seçici")
    st.caption("Bu filtre değerleme veya alım sinyali değildir. Düşmüş bir fiyat daha da düşebilir; şirket temelleri ve likidite ayrıca incelenmelidir.")
    if candidates.empty:
        st.info("Seçilen koşullara uyan güncel hisse yok. Filtreleri değiştirerek araştırma alanını genişletebilirsin.")
    else:
        opportunity=candidates[["symbol","name","asof","last_price","dip_uzaklik","pct_from_hi","vol_z"]].copy()
        opportunity.pct_from_hi*=100
        st.dataframe(opportunity,hide_index=True,use_container_width=True,height=430,column_config={
            "symbol":"Sembol","name":"Şirket","asof":"Veri tarihi",
            "last_price":st.column_config.NumberColumn(f"Son fiyat ({currency})",format="%.2f"),
            "dip_uzaklik":st.column_config.NumberColumn("Yıllık dibe uzaklık (%)",format="%.2f"),
            "pct_from_hi":st.column_config.NumberColumn("Zirveye göre (%)",format="%.2f"),
            "vol_z":st.column_config.NumberColumn("Hacim Z",format="%.2f")})
        fig=go.Figure(go.Scatter(x=candidates.dip_uzaklik,y=candidates.pct_from_hi*100,
            mode="markers",text=candidates.symbol,marker={"size":10,"color":"#b87922","opacity":.75},
            hovertemplate="%{text}<br>Dibe uzaklık: %{x:.1f}%<br>Zirveye göre: %{y:.1f}%<extra></extra>"))
        fig.update_layout(height=340,xaxis_title="Yıllık dibe uzaklık (%)",yaxis_title="Zirveye göre değişim (%)",
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",margin={"l":15,"r":15,"t":15,"b":15})
        st.plotly_chart(fig,use_container_width=True)

elif page == "Piyasa radarı":
    cols = st.columns(4)
    latest = data[data["asof"]==asof]
    rising = int((latest.r_1d>0).sum())
    falling = int((latest.r_1d<0).sum())
    cols[0].metric("Takip edilen hisse",f"{len(data):,}")
    cols[1].metric("Yükselen · son veri günü",rising)
    cols[2].metric("Düşen · son veri günü",falling)
    median = latest.r_1d.median()*100
    cols[3].metric("Medyan günlük getiri",f"{median:+.2f}%" if pd.notna(median) else "—")
    st.subheader("Piyasa radarı")
    c1,c2,c3,c4 = st.columns([3,2,2,1])
    search = c1.text_input("Sembol veya şirket ara",placeholder="THYAO, AAPL, teknoloji…")
    period = c2.selectbox("Getiri dönemi",list(RETURNS),index=2)
    direction = c3.selectbox("Görünüm",["En çok yükselen","En çok düşen","Zirveden uzaklaşan","Yüksek hacim"])
    count = c4.selectbox("Satır",[25,50,100,500],index=1)
    filtered = data
    if search:
        filtered = filtered[filtered.symbol.str.contains(search,case=False,regex=False)|filtered.name.fillna("").str.contains(search,case=False,regex=False)]
    sort = "pct_from_hi" if direction=="Zirveden uzaklaşan" else "vol_z" if direction=="Yüksek hacim" else RETURNS[period]
    filtered = filtered.sort_values(sort,ascending=direction in ("En çok düşen","Zirveden uzaklaşan"),na_position="last")
    t1,t2 = st.tabs(["Hisse listesi","Piyasa genişliği"])
    with t1:
        table(filtered.head(count))
    with t2:
        st.caption("Aynı veri tarihine sahip hisseler kullanılır. Endeks getirisi değildir.")
        breadth = pd.DataFrame({"Durum":["Yükselen","Düşen","Değişmeyen"],"Hisse":[rising,falling,int((latest.r_1d==0).sum())]})
        st.bar_chart(breadth.set_index("Durum"),color="#b87922")
        st.subheader("Dönem bazında medyan getiri (%)")
        st.bar_chart(pd.DataFrame({"Dönem":list(RETURNS),"Getiri":[latest[v].median()*100 for v in RETURNS.values()]}).set_index("Dönem"),color="#277f89")

elif page == "Hisse inceleme":
    symbol = st.selectbox("Hisse",sorted(data.symbol),index=0)
    row = data[data.symbol==symbol].iloc[0]
    st.subheader(f"{symbol} · {row['name']}")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(f"Son kapanış ({currency})",f"{row.last_price:,.2f}")
    for col,label,key in [(c2,"1 gün","r_1d"),(c3,"1 ay","r_1m"),(c4,"1 yıl","r_1y")]:
        col.metric(label,f"{row[key]*100:+.2f}%" if pd.notna(row[key]) else "Yetersiz geçmiş")
    window = st.select_slider("Grafik dönemi",options=["1 ay","3 ay","6 ay","1 yıl","Tümü"],value="1 yıl")
    frame = price_history(symbol)
    if window!="Tümü" and not frame.empty:
        months = {"1 ay":1,"3 ay":3,"6 ay":6,"1 yıl":12}[window]
        frame=frame[frame.date>=frame.date.max()-pd.DateOffset(months=months)]
    fig=go.Figure(go.Scatter(x=frame.date,y=frame.adj_close,mode="lines",fill="tozeroy",line={"color":"#b87922","width":2},fillcolor="rgba(184,121,34,.10)",name="Düzeltilmiş kapanış"))
    fig.update_layout(height=430,margin={"l":15,"r":15,"t":20,"b":10},paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",yaxis_title=f"Düzeltilmiş fiyat ({currency})",hovermode="x unified")
    st.plotly_chart(fig,use_container_width=True)
    st.caption("Grafik ve getiriler bölünme/temettü için düzeltilmiş fiyatı kullanır. Son kapanış kartı işlem fiyatını gösterir.")
    st.bar_chart(frame.set_index("date")[["volume"]],color="#277f89",height=180)
    with st.expander("Veriye dayalı kısa değerlendirme",expanded=True):
        distance = f"%{abs(row.pct_from_hi)*100:.1f}" if pd.notna(row.pct_from_hi) else "bilinmeyen oran"
        st.write(f"{row['asof']} verilerine göre {symbol}, son bir yıllık düzeltilmiş kapanış zirvesinin {distance} altında. Bu bölüm hesaplanan istatistikleri özetler; bir dil modeli veya fiyat tahmini kullanmaz.")

elif page == "Karşılaştırma":
    st.subheader("Aynı başlangıçtan karşılaştır")
    selected = st.multiselect("En fazla 6 hisse",sorted(data.symbol),default=sorted(data.symbol)[:2],max_selections=6)
    if selected:
        frames=[price_history(s).set_index("date").adj_close.rename(s) for s in selected]
        joined=pd.concat(frames,axis=1).dropna()
        if len(joined)>1:
            joined=joined.tail(252)
            st.line_chart(joined.div(joined.iloc[0]).mul(100),height=450)
            st.caption("İlk ortak işlem günü = 100. Son 252 ortak gözlem; düzeltilmiş kapanışlar.")
            table(data[data.symbol.isin(selected)])
        else:
            st.info("Seçilen hisselerin yeterli ortak tarihli verisi yok.")

else:
    st.subheader("Veri akışının durumu")
    runs=query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 15",revision=revision)
    if runs.empty:
        st.info("Mevcut StockWizard verileri aktarılmış. Henüz yeni bir günlük güncelleme tamamlanmadı.")
    else:
        st.dataframe(runs,hide_index=True,use_container_width=True)
        failures=query("SELECT market,symbol,error FROM fetch_log WHERE run_date=? AND status='failed'",(runs.iloc[0].run_date,),revision)
        if not failures.empty:
            st.warning("Bazı semboller güncellenemedi; önceki verileri korunuyor.")
            st.dataframe(failures,hide_index=True,use_container_width=True)
    st.write("**Plan:** Her gün 02.30 · Europe/Istanbul. BIST ve ABD sembolleri tek Airflow DAG içinde işlenir.")
    st.write("Başarılı semboller aynı gün tekrar indirilmez. Hatalı semboller Airflow yeniden denemesinde tekrar işlenir.")
    st.caption("VM kapalıyken görev çalışmaz. Tatil günlerinde son işlem günü gösterilir. NASDAQ/NYSE listesi mevcut ABD projesinden alınır; otomatik borsa üyeliği doğrulaması yapılmaz.")

st.divider()
st.caption("VULTURE CAPITAL · Gün sonu piyasa araştırması · Veriler gecikebilir. Yatırım tavsiyesi değildir.")
