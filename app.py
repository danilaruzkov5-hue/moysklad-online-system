import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime

# --- ДАННЫЕ ИЗ ПЕРЕПИСКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

def load_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                stype = "ИП" if "ИП" in name.upper() else "ООО"
                rows.append({
                    "uuid": i.get('id'),
                    "Наименование": name,
                    "Артикул": i.get('article', '—'),
                    "Баркод": i.get('code', '—'),
                    "Кол-во": i.get('stock', 0),
                    "Тип": stype
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

# Инициализация состояний
if 'df' not in st.session_state: st.session_state.df = load_data()
if 'arch' not in st.session_state: 
    st.session_state.arch = pd.DataFrame(columns=["uuid", "Наименование", "Артикул", "Баркод", "Кол-во", "Тип"])

st.title("📦 Система управления складом")

# --- ВОЗВРАЩЕННАЯ КНОПКА (ТЕПЕРЬ ТУТ) ---
if st.button("🔄 Обновить остатки из МойСклад", use_container_width=True):
    fresh_df = load_data()
    if not st.session_state.arch.empty:
        archived_uuids = st.session_state.arch['uuid'].tolist()
        st.session_state.df = fresh_df[~fresh_df['uuid'].isin(archived_uuids)].reset_index(drop=True)
    else:
        st.session_state.df = fresh_df
    st.rerun()

search = st.text_input("🔍 Поиск (Баркод / Артикул / Название)")

t1, t2, t3, t4, t5 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив отгрузки", "💰 Хранение", "📊 Итого по Баркодам"])

def render_table(storage_type, key):
    df = st.session_state.df
    filt = df[df["Тип"] == storage_type]
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]

    if filt.empty:
        st.info(f"На складе {storage_type} пусто")
        return

    sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                       selection_mode="multi-row", on_select="rerun", key=f"table_{key}")
    
    selected_rows = sel.get("selection", {}).get("rows", [])
    if selected_rows and st.button(f"🚀 Завершить и отгрузить ({storage_type})", key=f"btn_{key}"):
        items_to_ship = filt.iloc[selected_rows].copy()
        st.session_state.arch = pd.concat([st.session_state.arch, items_to_ship], ignore_index=True)
        st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(items_to_ship['uuid'])]
        st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        sel_arch = st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True,
                                selection_mode="multi-row", on_select="rerun", key="arch_table")
        arch_selected = sel_arch.get("selection", {}).get("rows", [])
        
        c1, c2 = st.columns(2)
        with c1:
            csv = st.session_state.arch.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Скачать файл отгрузки", csv, "otgruzka.csv", "text/csv", use_container_width=True)
        with c2:
            if arch_selected and st.button("⏪ Вернуть выбранное на склад", use_container_width=True):
                items_to_restore = st.session_state.arch.iloc[arch_selected].copy()
                st.session_state.df = pd.concat([st.session_state.df, items_to_restore], ignore_index=True)
                st.session_state.arch = st.session_state.arch.drop(st.session_state.arch.index[arch_selected]).reset_index(drop=True)
                st.rerun()
    else: st.info("Архив пуст")

with t4:
    total_qty = int(st.session_state.df["Кол-во"].sum())
    pallets = math.ceil(total_qty / 16) if total_qty > 0 else 0
    st.metric("Коробов на складе", total_qty)
    st.metric("Итого паллет (16 кор = 1 паллет)", pallets)
    st.metric("Стоимость хранения", f"{pallets * 50} руб/сутки")

with t5:
    st.subheader("Сводка по баркодам (Общее количество)")
    if not st.session_state.df.empty:
        # Группировка для ТЗ: сколько единиц каждого баркода всего на складе
        summary = st.session_state.df.groupby("Баркод")["Кол-во"].sum().reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)


