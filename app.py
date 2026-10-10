import io
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Volby Kolín 2026', page_icon='🗳️', layout='centered')
st.markdown('''<style>.block-container{padding-top:1.3rem;max-width:850px}h1{color:#06387e}div[data-testid="stMetricValue"]{font-size:1.9rem}</style>''', unsafe_allow_html=True)
ROOT='https://volby.gov.cz/appdata'
CITY=f'{ROOT}/kv2026/20261009/odata/vysledky_obec_533165.xml'
SENATE=f'{ROOT}/senat/20261009/odata/vysledky.xml'

@st.cache_data(ttl=60, show_spinner=False)
def fetch(url):
    r=requests.get(url,timeout=18,headers={'User-Agent':'KolinResultsDashboard/1.0 (public election data)'})
    r.raise_for_status()
    if not r.content.lstrip().startswith(b'<'):
        raise ValueError('Zdroj nevrátil XML data.')
    return r.content, datetime.now(ZoneInfo('Europe/Prague')).strftime('%H:%M:%S')

def tag(el):return el.tag.split('}')[-1].upper()
def fields(el):
    d={k.upper():v for k,v in el.attrib.items()}
    for child in el:
        if len(child)==0 and child.text and child.text.strip():
            d[tag(child)]=child.text.strip()
    return d

def num(x):
    try:return float(str(x).replace(' ','').replace(',','.').replace('%',''))
    except (TypeError,ValueError):return None

def val(d,*keys):
    for k in keys:
        if k in d and d[k] not in ('',None):return d[k]
    return None

def format_pct(v):
    n=num(v)
    return f'{n:.2f} %'.replace('.',',') if n is not None else '—'

def candidates(root):
    rows=[]
    for e in root.iter():
        t=tag(e)
        if t in ('KANDIDAT','KAND','HLAS','VOLEBNI_STRANA','STRANA','VS'):
            d=fields(e)
            name=val(d,'NAZEV_STRANY','NAZEV_VS','NAZEV','JMENO','JMENO_KAND','JMENO_PRIJMENI','PRIJMENI')
            votes=val(d,'HLASY','HLASY_CELK','POC_HLASU','HLASY_1KOLO','HLASY_1K','HLASY_PROC_1KOLO','PROC_HLASU','HLASY_PROC')
            if name and votes is not None:
                rows.append({'Název':name,'Hlasy':num(votes),'Procenta':num(val(d,'HLASY_PROC','PROC_HLASU','HLASY_PROC_1KOLO','PROC_HLASU_1KOLO')),'Mandáty':val(d,'MANDATY','POC_MANDATU'),'tag':t})
    return rows

def find_area(root, desired, keys):
    for el in root.iter():
        d=fields(el)
        if any(str(d.get(k,''))==str(desired) for k in keys):return el
    return None

def progress(area):
    d=fields(area)
    done=val(d,'OKRSKY_ZPRAC','OKRSKY_ZPRACOVANE','OKRSKY_ZPRAC_PROC','OKRSKY_ZPRAC_PCT','ZPRAC_OKRSKY','OKRSKY_ZPRACOVANO')
    total=val(d,'OKRSKY_CELK','OKRSKY_CELKEM','OKRSKY')
    turnout=val(d,'UCAST_PROC','UCAST','VOLEBNI_UCAST','UCAST_PCT')
    a,b,c=st.columns(3)
    a.metric('Zpracované okrsky', f'{done} / {total}' if done and total else (str(done) if done else '—'))
    b.metric('Účast',format_pct(turnout))
    b.caption('Podle dostupných údajů ČSÚ')
    c.metric('Mandáty',val(d,'MANDATY_CELK','POC_MANDATU') or '—')

def show_table(rows, label):
    if not rows:
        st.info('Zdroj byl načten, ale tabulku zatím nelze bezpečně sestavit z dostupných položek XML. Použij odkaz na oficiální výsledky níže.')
        return
    df=pd.DataFrame(rows).drop(columns=['tag']).drop_duplicates()
    if df['Procenta'].notna().any():
        df=df.sort_values('Procenta',ascending=False,na_position='last')
        st.bar_chart(df.set_index('Název')['Procenta'],horizontal=True)
    elif df['Hlasy'].notna().any():
        df=df.sort_values('Hlasy',ascending=False,na_position='last')
        st.bar_chart(df.set_index('Název')['Hlasy'],horizontal=True)
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.caption(label)

st.title('🗳️ Volby Kolín 2026')
st.caption('Neoficiální přehled • oficiální zdroj dat: Český statistický úřad')
if st.button('🔄 Načíst aktuální data',use_container_width=True):st.cache_data.clear();st.rerun()
st.caption('Obnovování dat: maximálně jednou za 60 sekund při opětovném načtení stránky. Pro trvalé automatické obnovení lze použít volitelnou komponentu níže.')
section=st.radio('Volby',['Kolín – zastupitelstvo','Senát – obvod 42'],horizontal=True)
url=CITY if section.startswith('Kolín') else SENATE
try:
    raw,at=fetch(url)
    root=ET.fromstring(raw)
    st.success(f'Data načtena z ČSÚ v {at}')
    if section.startswith('Kolín'):
        area=find_area(root,533165,['KODZASTUP','KOD_OBEC','CIS_OBEC','OBEC']) or root
    else:
        area=find_area(root,42,['CIS_OBVOD','OBVOD','CISLO_OBVODU','KOD_OBVODU'])
        if area is None:
            # Senát: pouze obvod 42, nikdy nezobrazovat směs všech obvodů
            for el in root.iter():
                if tag(el) in ('OBVOD','SENATNI_OBVOD') and any(str(v)=='42' for v in el.attrib.values()):
                    area=el;break
    if area is None:
        st.warning('Obvod 42 nebyl v aktuálním souboru nalezen. Zobrazení výsledků je pozastaveno, aby nedošlo k záměně obvodů.')
    else:
        progress(area)
        rows=candidates(area)
        show_table(rows,'Průběžné výsledky se mohou měnit; mandáty se potvrzují až po dokončení sčítání.')
    with st.expander('Technické informace'):
        st.code(url)
        st.write('Kořenový element:',tag(root))
        st.write('Položky prvního záznamu:',list(fields(next(iter(root),root)).keys()))
except Exception as exc:
    st.error('Oficiální data se nyní nepodařilo načíst. Žádné náhradní ani smyšlené výsledky nezobrazujeme.')
    st.caption(f'Technický detail: {type(exc).__name__}: {exc}')

st.divider()
st.link_button('Oficiální výsledky ČSÚ', 'https://volby.gov.cz/',use_container_width=True)
st.caption('Dashboard není oficiální aplikací ČSÚ. Před publikací výsledků ověřte čísla přímo u ČSÚ.')
